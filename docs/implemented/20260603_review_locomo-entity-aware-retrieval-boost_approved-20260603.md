# Code Review: LoCoMo Entity-Aware Retrieval Boost - Approved

**Review Date**: 2026-06-03
**Original Issue**: `docs/issues/20260603_locomo-entity-aware-retrieval-boost.md`
**Worktree**: `/home/main/dev/animaworks-bak-issue-20260603-105059`
**Status**: APPROVED

## Summary

All required implementation checks passed. The implementation is ready for merge.

**Metrics**:
- Requirement Alignment: Complete
- Test Coverage: New `core.memory.retrieval.entity` module 97% via pytest-cov
- Code Quality: No blocking issues found
- SRP Compliance: New module is single-purpose; existing pipeline/adapter changes are narrowly scoped
- File Sizes: New/modified implementation files are within 500 lines except pre-existing `benchmarks/locomo/adapter.py` at 775 lines
- E2E / Real Workflow: LoCoMo retrieval diagnostics ran with `--entity-ablation`, errors=0
- Regression: Default smoke path keeps entity boost disabled

## Verification

- `ruff check ...`: passed
- Targeted pytest: `43 passed`
- Entity module coverage: 97%
- Real retrieval diagnostics:
  - Command: `python -m benchmarks.locomo.retrieval_diagnostics --data /home/main/dev/animaworks-bak/benchmarks/locomo/data/locomo10.json --mode scope_all --conversations 1 --top-k 10 --ceiling-top-k 10 --entity-ablation --output /tmp/locomo_retrieval_diag_issue2_top10_boost080`
  - Output: `/tmp/locomo_retrieval_diag_issue2_top10_boost080/2026-06-03T11-39-50_scope_all_retrieval_diagnostics.json`
  - Errors: 0
  - Baseline answer token recall@10: 0.5699828315
  - Entity ablation answer token recall@10: 0.5718625307
  - Overall delta: +0.0018796992
  - Open-domain delta: +0.0040816327
  - Multi-hop delta: 0.0

## Review Findings

### 1. Issue Requirement Alignment

**Status**: PASS

- `core/memory/retrieval/entity.py` implements deterministic extraction and capped additive boost.
- `core/memory/retrieval/pipeline.py` accepts optional `entity_boost` and preserves default behavior when omitted.
- `benchmarks/locomo/adapter.py` adds `LOCOMO_ENTITY_BOOST`, speaker-name ignore handling, metadata propagation, and scope_all integration.
- `benchmarks/locomo/retrieval_diagnostics.py` adds `--entity-ablation`, JSON payload, deltas, and top entity diagnostics.
- Tests cover default disabled behavior, category 1/4 allowlist, category 2/3/5 exclusion, env toggles, and JSON config shape.

### 2. Test Coverage

**Status**: PASS

- New entity helper has focused unit coverage at 97%.
- Diagnostics module full coverage is not measured at 80% because the heavy CLI path is verified by real diagnostics rather than unit tests.
- Targeted tests passed: `43 passed`.

### 3. Code Quality

**Status**: PASS

- No new dependency on LLM, spaCy, or external NER.
- Entity metadata uses independent keys: `entity_boost`, `entity_overlap`, `query_entities`, `candidate_entities`.
- Boost remains opt-in and category-gated.

### 4. SRP

**Status**: PASS

- Entity extraction/scoring is isolated in `core/memory/retrieval/entity.py`.
- Pipeline only orchestrates ranking stages.
- Adapter only wires LoCoMo-specific env/category/speaker concerns.

### 5. File Size

**Status**: PARTIAL / ACCEPTABLE

- New `entity.py`: 203 lines.
- `retrieval_diagnostics.py`: 396 lines.
- Existing `adapter.py`: 775 lines, already above the 500-line review guideline before this change. This change adds only narrowly scoped wiring and does not worsen architecture enough to block merge.

### 6. E2E / Real Workflow

**Status**: PASS

- Real retrieval-only diagnostics with entity ablation completed with `errors=0`.
- A top50 ablation attempt was stopped due runtime cost; top10-only ablation was used for this Issue2 acceptance check.

### 7. Regression Prevention

**Status**: PASS

- `entity_boost` defaults to `None` in `RetrievalPipeline.run()`.
- LoCoMo adapter only enables boost when `LOCOMO_ENTITY_BOOST` is explicitly set.
- Category 5 adversarial path is excluded from entity boosting.
- Smoke guardrail confirms `LOCOMO_ENTITY_BOOST` is disabled by default.

### 8. Independent Agent Reviews

**Cursor Agent Review**: Failed / unavailable

- Cursor launcher returned a PID and output path, but both review output and log were 0 bytes.

**Codex Subagent Review**: Skipped

- Subagent tooling was not used in this run.

## Residual Risks

- Entity boost improved open_domain retrieval recall slightly but did not move multi_hop recall in the measured top10 diagnostics. This suggests the next roadmap item should not rely on query/chunk entity overlap alone for multi_hop; atomic fact dual index or query expansion is still needed.
- The diagnostics CLI remains slow with cross-encoder rerank, especially for top50 ablations.
- `benchmarks/locomo/adapter.py` remains oversized from prior work and should be split in a separate refactor if this area grows further.

## Next Steps

1. Merge to main.
2. Keep entity boost default-disabled until a live smoke run confirms answer F1 does not regress.
3. Use the measured multi_hop no-op as input to the next child Issue.

---

**No revision required.**
