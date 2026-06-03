# LoCoMo Entity-Aware Retrieval Boost — multi_hop / open_domain向けのentity一致signalをopt-in診断に追加する

## Overview

親Issue `docs/issues/20260602_locomo-memory-score-improvement-parent.md` の Phase 2 / Issue2 として、LoCoMo Legacy `scope_all` の retrieval pipeline に entity-aware additive signal を追加する。Phase 1 で追加した retrieval-only diagnostics と boost hook を利用し、LLM smoke の default 挙動を変えずに multi_hop / open_domain の recall 改善を ablation で測れるようにする。

## Problem / Background

### Current State

- Phase 1 後の retrieval diagnostics では、multi_hop answer token recall@10 が 0.4807、open_domain が 0.6420、complex が 0.2421 に留まっている。
- 現行 `scope_all` は vector + graph + BM25 を RRF で統合し、cross-encoder rerank と confidence gate を通すが、query と chunk の人物・作品・場所名が一致しても明示的な additive score にならない。
- Phase 1 で `core/memory/retrieval/pipeline.py:54` に `temporal_boost` hook が入り、`benchmarks/locomo/retrieval_diagnostics.py:286` に temporal ablation CLI が追加された。
- `benchmarks/locomo/adapter.py:81` の metadata allowlist は `base_score` / `temporal_boost` までで、entity diagnostics はまだ伝播しない。
- `benchmarks/locomo/adapter.py:513` は pipeline に temporal boost だけを渡しており、entity boost の opt-in toggle がない。

### Root Cause

1. Entity signal が ranking に入っていない — `benchmarks/locomo/adapter.py:505` は vector / graph / BM25 の候補を pipeline item に変換するだけで、query と候補本文の固有表現一致を評価しない。
2. Retrieval pipeline の boost hook が temporal 専用 — `core/memory/retrieval/pipeline.py:54` は `TemporalBoostConfig` だけを受け取り、複数の additive ranker を合成できない。
3. Ablation harness が temporal 専用 — `benchmarks/locomo/retrieval_diagnostics.py:286` は `--temporal-ablation` のみで、entity boost の効果を same-run JSON で比較できない。
4. Smoke regression guard が default-disabled を検証していない — `tests/integration/test_locomo_legacy_smoke.py:25` は temporal boost だけを確認している。

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/memory/retrieval/` | Direct | entity extraction と additive boost を共有 pipeline から使えるようにする。 |
| `core/memory/retrieval/pipeline.py` | Direct | temporal / entity の複数 boost を default-disabled で適用できるようにする。 |
| `benchmarks/locomo/adapter.py` | Direct | LoCoMo `scope_all` で entity boost toggle と diagnostics metadata を伝播する。 |
| `benchmarks/locomo/retrieval_diagnostics.py` | Direct | `--entity-ablation` で baseline vs boosted summary / deltas を出す。 |
| `tests/` | Direct | entity extraction、pipeline default、adapter env、diagnostics ablation を固定する。 |

## Decided Approach / 確定方針

### Design Decision

確定: LLM / spaCy / external NER は使わず、LoCoMo smoke に依存しない deterministic な軽量 entity extraction を実装する。capitalized phrase、quoted phrase、CJK phrase、known speaker labels を抽出し、query entity と candidate entity の overlap に応じて category 1 `multi_hop` と category 4 `open_domain` のみに opt-in additive boost を適用する。default smoke では `LOCOMO_ENTITY_BOOST` 未設定のため無効のままにする。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| LLM entity extraction | 高精度が期待できる | retrieval-only diagnostics が遅くなり、LLM不調で検索評価が止まる | **Rejected**: Issue2 は fast deterministic ablation を目的にする |
| spaCy / Stanza NER | 既存NERを使える | 追加依存が重く、日本語/英語混在 LoCoMo で環境差が出る | **Rejected**: smoke環境の再現性を下げる |
| BM25重みを上げるだけ | 実装が小さい | entity一致と一般語一致を区別できず、adversarial / open_domain を傷つけやすい | **Rejected**: 親Issueの entity signal 方針に合わない |
| 全カテゴリでentity boost | recall改善対象が広い | temporal / adversarial を壊す可能性が高い | **Rejected**: category 1/4 の opt-in のみに限定する |
| **Deterministic phrase overlap (Adopted)** | 低依存・高速・diagnostics向き | NER精度は限定的 | **Adopted**: regression risk を抑えて測定基盤を拡張できる |

### Key Decisions from Discussion

1. **entity boost は default-disabled** — Reason: Phase 1-3 退行で default smoke を変えるリスクが実測済み。
2. **対象カテゴリは 1 と 4 のみ** — Reason: 親Issueでは multi_hop / open_domain の entity signal が主目的で、category 5 adversarial は保護対象。
3. **抽出器は deterministic regex/token heuristic** — Reason: retrieval diagnostics を LLM なし・追加依存なしで回す。
4. **pipeline は複数 boost を合成できる形にする** — Reason: Phase 1 temporal boost と Issue2 entity boost を同じ ranking stage で扱う。
5. **diagnostics は same-run ablation JSON にする** — Reason: baseline と boosted の category別 delta を同じ形式で比較する。

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/memory/retrieval/entity.py` | New | entity phrase extraction、overlap scoring、`EntityBoostConfig`、`apply_entity_boost()` を追加する。 |
| `core/memory/retrieval/pipeline.py` | Modify | `entity_boost` optional param を追加し、RRF後とrerank後に temporal boost と同様に適用する。 |
| `benchmarks/locomo/adapter.py` | Modify | `LOCOMO_ENTITY_BOOST` helper、metadata allowlist、pipeline invocation を追加する。 |
| `benchmarks/locomo/retrieval_diagnostics.py` | Modify | `--entity-ablation`、temporary env helper、entity ablation payload / deltas を追加する。 |
| `tests/unit/core/memory/test_retrieval_pipeline.py` | Modify | default無効、category 1/4 のboost、category 5無効を検証する。 |
| `tests/unit/test_locomo_adapter.py` | Modify | env helper と metadata propagation を検証する。 |
| `tests/unit/benchmarks/test_locomo_retrieval_diagnostics.py` | Modify | entity ablation CLI / JSON shape / env helper を検証する。 |
| `tests/integration/test_locomo_legacy_smoke.py` | Modify | smoke guardrail で entity boost default-disabled を確認する。 |

### Edge Cases

| Case | Handling |
|------|----------|
| query entity が空 | boost は適用せず候補順を維持する。 |
| candidate entity が空 | その候補は加点しない。 |
| category 2 temporal | entity boost は適用しない。temporal boost は既存通り opt-in で別管理する。 |
| category 5 adversarial | entity boost は適用しない。adversarial abstain 保護を優先する。 |
| quoted phrase と capitalized phrase が重複 | 正規化後に set dedup する。 |
| short/common words | 2文字以下、LoCoMo question boilerplate、speaker/common stopword は entity から除外する。 |
| cross-encoder rerank 使用時 | rerank後にも entity boost を再適用し、final score / gate に反映する。 |

## Implementation Plan

### Phase 1: Entity Utility

| # | Task | Target |
|---|------|--------|
| 1-1 | `extract_entities(text)` を追加し、quoted / capitalized / CJK phrase を正規化抽出する | `core/memory/retrieval/entity.py` |
| 1-2 | `EntityBoostConfig` と `apply_entity_boost()` を追加し、overlap数に応じた capped additive boost を実装する | `core/memory/retrieval/entity.py` |
| 1-3 | unit tests で stopword、dedup、category gating、score metadata を検証する | `tests/unit/core/memory/test_retrieval_pipeline.py` |

**Completion condition**: entity helper の unit tests が追加され、default disabled では候補が変わらない。

### Phase 2: Pipeline / Adapter Integration

| # | Task | Target |
|---|------|--------|
| 2-1 | `RetrievalPipeline.run()` に `entity_boost` param を追加する | `core/memory/retrieval/pipeline.py` |
| 2-2 | `LOCOMO_ENTITY_BOOST` helper と metadata propagation を追加する | `benchmarks/locomo/adapter.py` |
| 2-3 | `scope_all` で `EntityBoostConfig(enabled=locomo_entity_boost_enabled(), category=category)` を渡す | `benchmarks/locomo/adapter.py` |

**Completion condition**: temporal boost 既存挙動を壊さず、entity boost は環境変数がある時だけ動く。

### Phase 3: Diagnostics Ablation

| # | Task | Target |
|---|------|--------|
| 3-1 | diagnostics CLI に `--entity-ablation` を追加する | `benchmarks/locomo/retrieval_diagnostics.py` |
| 3-2 | JSON payload に `entity_ablation` と category別 deltas を追加する | `benchmarks/locomo/retrieval_diagnostics.py` |
| 3-3 | targeted diagnostics を 1 conversation で実行し、errors=0 を確認する | CLI |

**Completion condition**: `--entity-ablation` run が baseline / boosted summary と deltas を出し、errors=0 で完了する。

## Scope

### In Scope

- deterministic entity extraction utility。
- category 1 / 4 の opt-in entity additive boost。
- `LOCOMO_ENTITY_BOOST` environment toggle。
- retrieval diagnostics の `--entity-ablation`。
- unit / integration tests。

### Out of Scope

- LLM fact extraction / atomic fact dual index — Reason: 親Issue Phase 3 で扱う。
- reranker model差し替え / pool 100比較 — Reason: 親Issue Phase 4 で扱う。
- deepseek answer prompt / confidence gate の変更 — Reason: adversarial regression risk がある。
- entity boost の本番 default 有効化 — Reason: smoke F1確認前の default変更はしない。
- Neo4j adapter の entity boost — Reason: 今回は Legacy `scope_all` の回帰検知経路に限定する。

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| entity heuristic が一般語を拾う | 誤候補が上がり recall/F1 が下がる | stopword、min length、category gating、max_boost cap を入れる。 |
| rerank後の score 加算で gate が緩む | adversarial 誤回答が増える | category 5 は boost対象外、default-disabled を smoke guardで検証する。 |
| diagnostics がさらに遅くなる | 実験サイクルが長くなる | `--entity-ablation` 指定時だけ追加runし、通常 diagnostics は1runのままにする。 |
| temporal boost と metadata key が衝突する | JSON解釈が混乱する | `entity_boost`, `entity_overlap`, `query_entities`, `candidate_entities` の独立keyにする。 |

## Acceptance Criteria

- [ ] `core/memory/retrieval/entity.py` が追加され、entity extraction と additive boost が unit tested である。
- [ ] `RetrievalPipeline.run()` は default 引数なしで既存挙動を維持する。
- [ ] `LOCOMO_ENTITY_BOOST` 未設定では LoCoMo smoke-compatible path が entity boost 無効である。
- [ ] `LOCOMO_ENTITY_BOOST=1` かつ category 1 / 4 の時だけ entity boost metadata が出る。
- [ ] category 2 / 3 / 5 では entity boost が適用されない。
- [ ] `python -m benchmarks.locomo.retrieval_diagnostics --entity-ablation ...` が `entity_ablation.summary`, `entity_ablation.deltas` を JSON に出す。
- [ ] targeted unit / integration tests が pass する。
- [ ] 1 conversation diagnostics の baseline と entity ablation が errors=0 で完了する。

## References

- `docs/issues/20260602_locomo-memory-score-improvement-parent.md` — Parent roadmap and Issue2 direction.
- `docs/implemented/20260602_locomo-event-time-recall-temporal-rerank_implemented-20260603.md` — Phase 1 implementation foundation.
- `benchmarks/locomo/adapter.py:81` — metadata allowlist currently lacks entity boost fields.
- `benchmarks/locomo/adapter.py:451` — LoCoMo retrieval entrypoint.
- `benchmarks/locomo/adapter.py:513` — pipeline invocation with temporal boost only.
- `benchmarks/locomo/retrieval_diagnostics.py:76` — retrieval-only diagnostics runner.
- `benchmarks/locomo/retrieval_diagnostics.py:286` — temporal-only ablation CLI flag.
- `core/memory/retrieval/pipeline.py:54` — current temporal boost hook.
- `core/memory/retrieval/temporal.py:118` — additive boost config pattern to mirror.
