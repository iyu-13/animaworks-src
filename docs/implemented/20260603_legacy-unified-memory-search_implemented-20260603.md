---
parent: 20260603_legacy-brain-memory-expansion-epic.md
supersedes_scope:
  - 20260522_legacy-priming-search-unification.md
depends_on:
  - 20260603_legacy-atomic-facts-mvp.md
  - 20260603_legacy-entity-index-boost.md
  - 20260603_legacy-fact-invalidation-valid-until.md
blocks:
  - 20260603_legacy-entity-aware-graph.md
---

# Legacy Unified Memory Search — search_memory / backend / priming の retrieval 経路を統一する

## Overview

Legacy の intentional recall (`search_memory`) と automatic recall (Priming C/F/G) を同じ retrieval policy に寄せる。`core/memory/retrieval/unified_search.py` に `UnifiedMemorySearch` を追加し、`RAGMemorySearch`、`LegacyRAGBackend.retrieve()`、Priming Channel C/F/G、LoCoMo adapter の Legacy `scope_all` が同じ fact/entity/validity-aware retrieval pipeline を使うようにする。

## Problem / Background

### Current State

- `RAGMemorySearch.search_memory_text()` は `scope=all` で独自に ranked lists を作り `RetrievalPipeline` を呼ぶ — `core/memory/rag_search.py:293`、`core/memory/rag_search.py:406`。
- `LegacyRAGBackend.retrieve()` は `scope=all` / `activity_log` のみ `search_memory_text` に委譲し、それ以外は `MemoryRetriever.search()` を直接呼ぶ — `core/memory/backend/legacy.py:169`。
- Priming Channel C は `MemoryRetriever` で knowledge を直接検索する — `core/memory/priming/channel_c.py:196`。
- Priming Channel F は Neo4j branch以外で `MemoryRetriever` で episodes を直接検索する — `core/memory/priming/channel_f.py:170`。
- Channel G は `MemoryBackend.get_recent_facts()` を呼ぶが、Legacy実装は activity_log proxy である — `core/memory/priming/channel_g.py:44`、`core/memory/backend/legacy.py:381`。
- `RetrievalPipeline` は RRF/rerank/confidence/temporal/entity を統合できる — `core/memory/retrieval/pipeline.py:29`。

### Root Cause

1. **Retrieval orchestration が `rag_search.py` に閉じている** — Priming/backend/LoCoMo が同じ candidate list policy を再利用できない。
2. **Scope policy が呼び出し元ごとに違う** — Chat、heartbeat、task、inboxなどの trigger別 pool/rerank/scope が統一されていない。
3. **Fact/entity/validity の反映点が分散する** — 今後の修正が `search_memory` と Priming でずれやすい。
4. **Legacy recent facts が proxy のまま** — Atomic facts後も Channel G が実 facts を自然に使えない。

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/memory/retrieval/unified_search.py` | Direct | New single Legacy retrieval orchestration。 |
| `core/memory/rag_search.py` | Direct | `scope=all` and `scope=facts` delegate target。 |
| `core/memory/backend/legacy.py` | Direct | Backend retrieve/get_recent_facts route unified。 |
| `core/memory/priming/channel_c.py` | Direct | Knowledge recall route changes. |
| `core/memory/priming/channel_f.py` | Direct | Episode recall route changes. |
| `core/memory/priming/channel_g.py` | Direct | Recent facts use actual facts. |
| `benchmarks/locomo/adapter.py` | Direct | Legacy scope_all can use production policy or adapter shim. |

## Decided Approach / 確定方針

### Design Decision

**確定**: `UnifiedMemorySearch.search(query, *, scope, limit, trigger, offset=0, min_score=0.0, time_start=None, time_end=None)` を追加する。Legacy retrieval の candidate list construction をここへ集約し、trigger別 policy で pool_k、rerank有無、target scopes、confidence gate を決める。Neo4j backend はこの Issue の対象外で、Legacyのみを統一する。

### Trigger Policy

| trigger | pool_k | rerank | scopes in RRF | confidence gate |
|---------|--------|--------|---------------|-----------------|
| chat | 50 | true | facts, episodes, knowledge, procedures, activity_log | enabled |
| inbox | 30 | true | facts, episodes, activity_log | enabled |
| heartbeat | 20 | false | episodes, activity_log | enabled with RRF threshold |
| task | 30 | true | facts, procedures, knowledge | enabled |
| cron | 30 | true | facts, episodes, knowledge, activity_log | enabled |
| tool | 50 | true | scope argument controls exact list | enabled |

`search_memory` uses `trigger="tool"`. Priming caller passes its actual trigger where available; if unavailable, `chat` is used.

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Keep Priming direct retriever calls | Minimal change | automatic/intentional recall divergenceが残る | **Rejected**: Epic目的に反する |
| Move all logic into `RAGMemorySearch` only | Existing classを使える | Backend/Primingから使いにくく肥大化する | **Rejected**: retrieval moduleに分離 |
| Always use full chat policy | 実装が単純 | heartbeat/inboxでcostとnoiseが高い | **Rejected**: trigger policy必須 |
| Include Neo4j in UnifiedMemorySearch | 一つのAPIにできる | scopeが広がりLegacy-firstから外れる | **Rejected**: Neo4jは既存維持 |
| **Legacy-only unified search module (Adopted)** | 影響範囲をLegacyに限定しつつ経路統一 | 呼び出し元修正が必要 | **Adopted**: 回帰管理しやすい |

### Key Decisions from Discussion

1. **UnifiedSearchは facts/entity/invalidation 後** — Reason: 統一する retrieval policy の中身を先に安定させる。
2. **`search_memory` は trigger=`tool`** — Reason: user-initiated intentional recall として offset/scope を尊重する。
3. **heartbeat rerank off** — Reason: latency/costを抑える。
4. **Neo4j pathは変更しない** — Reason: Legacy拡張Issueであり runtime bridgeではない。
5. **Channel Gは real facts 優先** — Reason: Atomic facts後、activity_log proxyを残す理由が薄い。

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/memory/retrieval/unified_search.py` | New | `UnifiedMemorySearch`, trigger policy, candidate source collection, pipeline invocation。 |
| `core/memory/rag_search.py` | Modify | `scope=all`/`facts` pathを unifiedへdelegateし、legacy formatting compatibilityを保持。 |
| `core/memory/backend/legacy.py` | Modify | `retrieve()` と `get_recent_facts()` を unified経由にする。 |
| `core/memory/priming/channel_c.py` | Modify | Knowledge direct retriever callを unified searchに置換。 |
| `core/memory/priming/channel_f.py` | Modify | Episode direct retriever callを unified searchに置換。Neo4j branchは維持。 |
| `core/memory/priming/channel_g.py` | Modify | Backend real facts output shapeを前提に formatting調整。 |
| `benchmarks/locomo/adapter.py` | Modify | scope_all の adapter-local logicを unified-compatible shimへ寄せる。Benchmark-specific env ablationは維持。 |
| `tests/unit/core/memory/test_unified_memory_search.py` | New | trigger policy and candidate list tests。 |
| `tests/unit/core/memory/test_priming_unified_search.py` | New/Modify | Channel C/F/G route tests。 |

### Edge Cases

| Case | Handling |
|------|----------|
| `facts` not indexed yet | Candidate list for facts is empty; other scopes continue. |
| Unified search gets unknown trigger | Use `chat` policy and log debug. |
| Scope is explicit `knowledge`/`episodes`/`facts` | Restrict target scopes to requested scope regardless of trigger. |
| `activity_log` search unavailable | Omit activity_log list and continue. |
| Confidence gate abstains in Priming | Channel returns empty string; no injection. |
| Offset pagination | Only `trigger="tool"` applies offset after final ranking; Priming uses offset 0. |
| Neo4j backend selected | Existing Neo4j branches continue; UnifiedSearch is not used for Neo4j. |
| LoCoMo env ablations | Benchmark-specific toggles remain in adapter; unified path must not remove them until equivalent diagnostics exist. |

## Implementation Plan

### Phase 1: Unified Search Core

| # | Task | Target |
|---|------|--------|
| 1-1 | Add trigger policy dataclass/table | `core/memory/retrieval/unified_search.py` |
| 1-2 | Add candidate list builders for facts/episodes/knowledge/procedures/activity_log | `core/memory/retrieval/unified_search.py` |
| 1-3 | Call existing `RetrievalPipeline` with config-derived rerank/confidence/entity settings | `core/memory/retrieval/unified_search.py` |
| 1-4 | Add unit tests for policies and empty sources | `tests/unit/core/memory/test_unified_memory_search.py` |

**Completion condition**: UnifiedSearch returns the same result shape as `RAGMemorySearch` and respects trigger/scope policies.

### Phase 2: `search_memory` and Backend Delegation

| # | Task | Target |
|---|------|--------|
| 2-1 | Delegate `RAGMemorySearch.search_memory_text()` to UnifiedSearch for supported scopes | `core/memory/rag_search.py` |
| 2-2 | Delegate `LegacyRAGBackend.retrieve()` to UnifiedSearch | `core/memory/backend/legacy.py` |
| 2-3 | Implement real facts in `get_recent_facts()` | `core/memory/backend/legacy.py` |
| 2-4 | Preserve formatting and `last_search_meta` behavior | `core/memory/rag_search.py` |

**Completion condition**: `search_memory` and Legacy backend return compatible results with shared ranking metadata.

### Phase 3: Priming and LoCoMo Integration

| # | Task | Target |
|---|------|--------|
| 3-1 | Replace Channel C direct retriever call | `core/memory/priming/channel_c.py` |
| 3-2 | Replace Channel F Legacy direct retriever call while preserving Neo4j branch | `core/memory/priming/channel_f.py` |
| 3-3 | Adjust Channel G to real facts | `core/memory/priming/channel_g.py` |
| 3-4 | Replace LoCoMo Legacy `scope_all` production-equivalent path with UnifiedSearch while preserving benchmark-only env ablation hooks | `benchmarks/locomo/adapter.py` |
| 3-5 | Add priming/search consistency tests | `tests/unit/core/memory/test_priming_unified_search.py` |

**Completion condition**: For the same `(anima, query, trigger=chat)`, search_memory and Priming C/F use the same candidate source policy and top-k document IDs are consistent for overlapping scopes.

## Scope

### In Scope

- Legacy-only unified retrieval orchestration.
- `search_memory`, Legacy backend, Priming C/F/G alignment.
- Trigger-specific retrieval policy.
- Real facts for Legacy `get_recent_facts()`.
- Tests for behavior compatibility and abstain propagation.

### Out of Scope

- Neo4j backend routing changes — Reason: Legacy-first scope.
- Entity-aware graph edge implementation — Reason: next child issue.
- Query expansion/access boost changes — Reason: existing separate issues handle these changes outside this Issue.
- Prompt injection formatting redesign — Reason: retrieval route only.
- Default enabling benchmark-specific LoCoMo env features — Reason: separate measurement decisions.

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Broad behavior regression | Priming/search_memory output changes | Implement after fact/entity/invalidation; add compatibility tests and staged delegation. |
| Latency increase | Chat/Priming slower | Trigger policy controls pool/rerank; heartbeat rerank off. |
| Formatting mismatch | Tool output or priming pointers break | Preserve existing result dict fields and pointer formatting helpers. |
| Neo4j branch accidentally changes | Existing Neo4j users regress | Keep explicit Neo4j branches untouched and test Legacy-only wiring. |
| LoCoMo adapter divergence | Benchmarks become incomparable | Keep env ablations and document adapter-specific differences. |

## Acceptance Criteria

- [ ] `core/memory/retrieval/unified_search.py` exists with explicit trigger policy table.
- [ ] `RAGMemorySearch.search_memory_text()` delegates supported Legacy scopes to UnifiedSearch while preserving output fields and `last_search_meta`.
- [ ] `LegacyRAGBackend.retrieve()` uses UnifiedSearch for Legacy scopes including `facts`.
- [ ] `LegacyRAGBackend.get_recent_facts()` returns actual facts when fact store/index exists, falling back only when no facts are available.
- [ ] Priming Channel C and F no longer call `MemoryRetriever.search()` directly for Legacy paths.
- [ ] Priming Channel F keeps the Neo4j branch unchanged.
- [ ] Confidence gate abstain yields empty priming channel output.
- [ ] Heartbeat trigger does not invoke cross-encoder rerank.
- [ ] Unit tests cover trigger policies, explicit scope restriction, offset behavior, abstain propagation, and missing fact index fallback.
- [ ] A focused regression confirms search_memory and Priming share top-k document IDs for overlapping chat policy scopes.

## References

- `docs/issues/20260603_legacy-atomic-facts-mvp.md` — Facts dependency.
- `docs/issues/20260603_legacy-entity-index-boost.md` — Entity boost dependency.
- `docs/issues/20260603_legacy-fact-invalidation-valid-until.md` — Validity dependency.
- `docs/issues/20260522_legacy-priming-search-unification.md:1` — Earlier C7 superseded by this revised issue.
- `core/memory/rag_search.py:293` — Current search entrypoint.
- `core/memory/rag_search.py:406` — Current `scope=all` hybrid implementation.
- `core/memory/backend/legacy.py:169` — Current Legacy backend retrieve.
- `core/memory/backend/legacy.py:381` — Current activity_log proxy recent facts.
- `core/memory/priming/channel_c.py:196` — Current Channel C direct retriever.
- `core/memory/priming/channel_f.py:170` — Current Channel F direct retriever.
- `core/memory/priming/channel_g.py:44` — Current recent facts call.
- `core/memory/retrieval/pipeline.py:29` — Shared retrieval pipeline.
