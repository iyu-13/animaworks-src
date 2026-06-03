---
parent: 20260603_legacy-brain-memory-expansion-epic.md
supersedes_scope:
  - 20260522_legacy-entity-index-boost.md
depends_on:
  - 20260603_legacy-atomic-facts-mvp.md
blocks:
  - 20260603_legacy-unified-memory-search.md
  - 20260603_legacy-entity-aware-graph.md
---

# Legacy Entity Index Boost — production Legacy に entity registry と検索 boost を追加する

## Overview

Atomic facts から抽出された entities を Legacy の first-class retrieval signal にする。`state/entity_registry.json` を authoritative store、`{anima}_entities` Chroma collection を検索補助として管理し、production Legacy `scope=all` / `scope=facts` / `scope=episodes` の retrieval pipeline に entity overlap boost を接続する。

この Issue は LoCoMo 専用 entity boost 実験を production Legacy に移植するものではない。既存の deterministic helper は再利用するが、production では fact-derived registry と config-controlled boost を追加する。

## Problem / Background

### Current State

- `RetrievalPipeline.run()` は `entity_boost` 引数を受け取り、RRF後とrerank後に `apply_entity_boost()` を呼べる — `core/memory/retrieval/pipeline.py:40`、`core/memory/retrieval/pipeline.py:77`。
- `core/memory/retrieval/entity.py` は deterministic entity extraction と capped additive boost を実装済み — `core/memory/retrieval/entity.py:92`、`core/memory/retrieval/entity.py:126`。
- Production `RAGMemorySearch._search_scope_all_hybrid()` は `RetrievalPipeline.run()` に `entity_boost` を渡していない — `core/memory/rag_search.py:464`。
- `RAGConfig` には entity boost 用の production config がない — `core/config/schemas.py:200`。
- C1 Atomic Facts MVP 後、fact metadata は `entities` を持つが、registryやmention countの永続管理はまだない。

### Root Cause

1. **Entity registry がない** — Fact由来 entity の canonical名、aliases、mention_count、last_seen_at を保存する場所がない。
2. **Production boost config がない** — LoCoMo env flagではなく、通常 config で Legacy retrieval を制御できない。
3. **Pipeline wiring がない** — entity boost helper は存在するが、production `RAGMemorySearch` から呼ばれていない。
4. **Entity collection がない** — query entity の fuzzy/canonical match に使える `{anima}_entities` collection がない。

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/memory/entity_index.py` | Direct | New registry/collection manager が必要。 |
| `core/memory/fact_extraction.py` | Direct | Fact write後に entity registry upsert が必要。 |
| `core/memory/retrieval/entity.py` | Direct | registry-aware query/entity extraction を追加する。 |
| `core/memory/rag_search.py` | Direct | `RetrievalPipeline.run(entity_boost=...)` を production で呼ぶ。 |
| `core/config/schemas.py` | Direct | entity boost config fields が必要。 |
| `core/memory/backend/legacy.py` | Indirect | Backend経由の retrieve にも entity boost が乗る。 |

## Decided Approach / 確定方針

### Design Decision

**確定**: `state/entity_registry.json` を authoritative store として追加し、fact ingest時に canonical entity を upsertする。`{anima}_entities` Chroma collection は registryの検索補助として使い、document content は canonical name + aliases + short summary とする。Production boost は `RAGConfig` で default disabled から開始し、`RetrievalPipeline` の既存 `EntityBoostConfig` を拡張して registry-derived candidate entities と fact/chunk metadataを利用する。

### Registry Shape

```json
{
  "version": 1,
  "entities": {
    "caroline": {
      "canonical": "Caroline",
      "aliases": ["caroline"],
      "entity_type": "Person",
      "mention_count": 12,
      "first_seen_at": "2026-06-03T00:00:00+09:00",
      "last_seen_at": "2026-06-03T00:00:00+09:00",
      "source_fact_ids": ["..."]
    }
  }
}
```

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| spaCy/Stanza NER | Entity抽出精度が上がる可能性 | 追加依存と環境差が大きい | **Rejected**: 既存 deterministic helper と LLM-extracted fact entities を使う |
| Neo4j entity node を参照 | Graph構造を使える | runtime bridge になり Legacy-first から外れる | **Rejected**: Legacy JSON + Chroma に落とし込む |
| Chroma collection のみを authoritative store にする | 実装が少ない | mention_count/aliases/rewrite/backup が扱いにくい | **Rejected**: JSON registryを authoritative にする |
| 全 scope で常時強い boost | recall改善が期待できる | adversarial/noisy queryで退行しやすい | **Rejected**: config-controlled capped boost |
| **Registry JSON + Chroma helper collection (Adopted)** | durableでinspect可能、vector/fuzzy検索も可能 | 2つのstore同期が必要 | **Adopted**: Legacy運用に合う |

### Key Decisions from Discussion

1. **Existing helper を土台にする** — Reason: `core/memory/retrieval/entity.py` は既に実装済みで、追加依存がない。
2. **Productionでは category gating しない** — Reason: LoCoMo category は production query には存在しない。`category=None` で有効化できるようにする。
3. **Boost default は disabled** — Reason: LoCoMo/live regression を確認してから有効化する。
4. **Fact metadata entities を優先** — Reason: LLM-extracted fact entities は query/chunk本文からの heuristic より信頼できる。
5. **Entity registry は JSON authoritative** — Reason: Legacy memoryはファイル可視性とバックアップしやすさを重視する。

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/memory/entity_index.py` | New | Registry load/save/upsert、alias normalize、Chroma entity collection sync、query matching。 |
| `core/memory/fact_extraction.py` | Modify | Fact write成功後、`FactRecord.entities` と `source_fact_ids` で registry upsert。 |
| `core/memory/facts.py` | Modify | Entity registry updateに必要な source_fact_ids と entity fields を安定取得できる helper を追加。 |
| `core/memory/retrieval/entity.py` | Modify | `EntityBoostConfig` に registry/matcher input を追加し、candidate metadata `entities` を優先する。 |
| `core/memory/rag_search.py` | Modify | RAG configを読み、`EntityBoostConfig` を `RetrievalPipeline.run()` に渡す。 |
| `core/config/schemas.py` | Modify | `entity_boost_enabled`, `entity_boost`, `entity_boost_cap`, `entity_registry_enabled` を追加。 |
| `core/memory/rag/indexer.py` | Modify | Fact chunk metadataの `entities` を検索結果へ安定伝播することをテストで固定。 |
| `tests/unit/core/memory/test_entity_index.py` | New | Registry upsert, alias, mention count, Chroma sync mock。 |
| `tests/unit/core/memory/test_rag_entity_boost_production.py` | New | Production pipeline config/wiring tests。 |

### Edge Cases

| Case | Handling |
|------|----------|
| `FactRecord.entities` empty | Registry updateをskipし、retrieval boostは本文 heuristic のみ使う。 |
| Same entity different casing | Normalize key with lower/strip; preserve first or longest canonical display name. |
| Alias collision | Existing canonical wins; new alias is appended only if normalized alias is not already mapped to another canonical. |
| Registry JSON corrupt | Rename to `.corrupt.{timestamp}` and rebuild from facts JSONL immediately; retrieval boost is disabled only if rebuild fails. |
| Chroma entity sync fails | JSON registry remains authoritative; log warning and continue. |
| Query has no registry/entity match | No boost; preserve original ranking. |
| Candidate has JSON string `entities` metadata | Always attempt JSON list parsing first; fallback to content heuristic on parse failure. |
| Boost pushes expired fact | Expired facts must already be filtered by C1/C3; entity boost never resurrects filtered candidates. |

## Implementation Plan

### Phase 1: Entity Registry

| # | Task | Target |
|---|------|--------|
| 1-1 | Add registry model/load/save/upsert | `core/memory/entity_index.py` |
| 1-2 | Add canonical/alias normalization and collision handling | `core/memory/entity_index.py` |
| 1-3 | Add rebuild-from-facts helper | `core/memory/entity_index.py` |
| 1-4 | Add registry unit tests | `tests/unit/core/memory/test_entity_index.py` |

**Completion condition**: Fact entities can update `state/entity_registry.json` with stable mention counts and aliases.

### Phase 2: Entity Collection and Ingest Hook

| # | Task | Target |
|---|------|--------|
| 2-1 | Add `{anima}_entities` Chroma sync helper | `core/memory/entity_index.py` |
| 2-2 | Hook registry upsert after successful fact append | `core/memory/fact_extraction.py` |
| 2-3 | Add failure isolation for registry/collection sync | `core/memory/fact_extraction.py` |

**Completion condition**: Fact ingest creates or updates registry and best-effort entity collection without failing fact storage.

### Phase 3: Production Retrieval Boost

| # | Task | Target |
|---|------|--------|
| 3-1 | Add config fields with default disabled | `core/config/schemas.py` |
| 3-2 | Extend `EntityBoostConfig` for production registry-aware boost | `core/memory/retrieval/entity.py` |
| 3-3 | Wire entity boost into `RAGMemorySearch._search_scope_all_hybrid()` and the `facts`, `episodes`, `knowledge`, `procedures` vector paths | `core/memory/rag_search.py` |
| 3-4 | Add production boost tests | `tests/unit/core/memory/test_rag_entity_boost_production.py` |

**Completion condition**: With config enabled, query/candidate entity overlap adds capped score metadata; with config disabled, ranking is unchanged.

## Scope

### In Scope

- Entity registry for Legacy facts.
- `{anima}_entities` helper collection.
- Production retrieval entity boost for Legacy search.
- Config-controlled default-disabled behavior.
- Unit tests for registry and boost wiring.

### Out of Scope

- Fact invalidation — Reason: separate child issue.
- Entity-aware graph edges — Reason: later child issue uses registry once stable.
- New external NER dependencies — Reason: deterministic/no-new-dependency decision.
- Neo4j entity sync — Reason: Legacy-first scope.
- Default-enabling boost globally — Reason: requires LoCoMo/live regression approval.

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Entity registry drift | Wrong aliases/boost | Keep JSON inspectable; provide rebuild from facts. |
| Boost causes false positives | Retrieval regression | Default disabled, capped boost, tests for no-op when no overlap. |
| Chroma sync failure | Entity vector matching unavailable | JSON registry remains authoritative; continue without Chroma. |
| Metadata shape mismatch | Boost silently no-ops | Parse both list and JSON string, add tests. |
| Config confusion | Unexpected behavior changes | Default disabled and explicit config names. |

## Acceptance Criteria

- [ ] `state/entity_registry.json` is created/updated from fact entities.
- [ ] Entity registry upsert is idempotent and increments mention_count correctly.
- [ ] `{anima}_entities` collection sync is best-effort and non-fatal.
- [ ] `RAGConfig` includes entity boost fields with default disabled.
- [ ] With entity boost disabled, `RetrievalPipeline` output order is unchanged.
- [ ] With entity boost enabled, candidates sharing query entities receive capped additive score and metadata.
- [ ] Candidate metadata `entities` is preferred over content heuristic.
- [ ] Empty/no-match queries pass through unchanged.
- [ ] Tests cover registry corruption fallback, alias collision, boost cap, metadata list/JSON parsing, and default disabled config.

## References

- `docs/issues/20260603_legacy-atomic-facts-mvp.md` — Fact dependency.
- `docs/issues/20260522_legacy-entity-index-boost.md:1` — Earlier C5 superseded by this revised issue.
- `core/memory/retrieval/entity.py:92` — Existing `EntityBoostConfig`.
- `core/memory/retrieval/entity.py:104` — Existing deterministic `extract_entities`.
- `core/memory/retrieval/entity.py:126` — Existing `apply_entity_boost`.
- `core/memory/retrieval/pipeline.py:55` — Pipeline `entity_boost` parameter.
- `core/memory/rag_search.py:464` — Current pipeline invocation.
- `core/config/schemas.py:200` — Current `RAGConfig`.
- `core/memory/rag/store.py:443` — Metadata list serialization.
