---
gh_issue:
parent: 20260522_legacy-memory-enhancement-epic.md
depends_on:
  - 20260522_legacy-locomo-regression-harness.md
  - 20260522_legacy-retrieval-confidence-gate.md
blocks: []
---

# LoCoMo deepseek Phase 1-3 rollback fix — Restore Run 2 behavior, then add targeted guardrails

## Overview

LoCoMo Legacy `scope_all` smoke for `deepseek-v4-flash` regressed from **44.7%** to **37.0%** after Phase 1-3 prompt/gate changes on 2026-05-25. This issue restores the Run 2-compatible behavior as the default, keeps the valid LLM routing and baseline infrastructure fixes, and adds narrow guardrails so the same regression is caught before running the 199-question smoke.

Run 3 must **not** become the deepseek baseline. The active deepseek baseline remains `benchmarks/locomo/baselines/legacy_scope_all_deepseek_v4_flash_20260525.json`, sourced from `/tmp/locomo_smoke_20260525_131445.json`.

## Problem / Background

### Current State

- Valid deepseek Run 2: `/tmp/locomo_smoke_20260525_131445.json`, overall F1 **0.4470**.
- Phase 1-3 Run 3: `/tmp/locomo_smoke_20260525_215811.json`, overall F1 **0.3699**.
- Overall regression: **-7.7pp**.
- Main category regression:
  - adversarial: **0.7872 -> 0.5532** (**-23.4pp**)
  - open_domain: **0.4033 -> 0.3473** (**-5.6pp**)
- Smoke threshold now fails because overall **0.3699 < 0.4270** minimum.
- Relevant code:
  - `benchmarks/locomo/answer_prompt.py:48` — new Phase 1 prompt template.
  - `benchmarks/locomo/answer_prompt.py:55` — "never abstain when context exists" instruction.
  - `benchmarks/locomo/answer_prompt.py:87` — category-aware gate thresholds.
  - `benchmarks/locomo/answer_prompt.py:116` — answer normalizer.
  - `benchmarks/locomo/answer_prompt.py:140` — category 2/4 year-only extraction.
  - `benchmarks/locomo/adapter.py:462` — category-aware gate overlay.
  - `benchmarks/locomo/adapter.py:579` — reduced `max_tokens`.
  - `benchmarks/locomo/metrics.py:163` — adversarial scoring rule.

### Root Cause

1. **Adversarial prompt conflict** — `benchmarks/locomo/answer_prompt.py:55` globally instructs the answer model to never abstain when any loosely related memory exists. This conflicts with category 5's required behavior, where unsupported or wrong-premise questions must answer exactly `No information available.`. Because `benchmarks/locomo/metrics.py:163` scores category 5 as 1.0 only for `No information available` / `not mentioned`, Run 3 converted 11 previously correct abstentions into 0-score answers.

2. **Unsafe open_domain normalization** — `benchmarks/locomo/answer_prompt.py:140` applies year extraction to category 4. Run 3 produced 13 open_domain answers that collapsed to `2023`, including questions whose references were non-date facts such as `"Becoming Nicole"`. These 13 items contributed about **-1.27pp** overall.

3. **Truncation and CoT leakage** — `benchmarks/locomo/adapter.py:579` reduces answer `max_tokens` from 512 to 128 while deepseek still emits single-line reasoning such as `We are asked...`. The normalizer at `benchmarks/locomo/answer_prompt.py:157` does not reliably strip single-line CoT, and some answers are truncated into invalid fragments such as `Melanie says "Congrats` or `but not`.

4. **Gate relaxation has negligible benefit** — Phase 2/3 changed default confidence thresholds from 0.35/0.02 to 0.20/0.01 for non-adversarial categories. This only changed `context_count=0` from 43 to 41 in Run 2 -> Run 3, so it does not justify the added behavioral complexity.

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `benchmarks/locomo/answer_prompt.py` | Direct | Prompt, gate settings, max token constant, and normalizer caused the Run 3 regression. |
| `benchmarks/locomo/adapter.py` | Direct | Uses category-aware gate overlay and reduced answer token limit. |
| `benchmarks/locomo/runner.py` | Indirect | Passes category into retrieve/answer; this can remain, but default behavior must not regress. |
| `scripts/locomo_legacy_smoke.sh` | Indirect | Correctly checks the Run 2 deepseek baseline and should continue to fail Run 3 behavior. |
| `benchmarks/locomo/baselines/legacy_scope_all_deepseek_v4_flash_20260525.json` | Direct | Must remain the Run 2 baseline, not be overwritten with Run 3. |

## Decided Approach / 確定方針

### Design Decision

**確定**: Restore the Run 2-compatible answer and gate behavior as the benchmark default, then add narrow regression guardrails around the exact failure modes found in Run 3. Keep the valid infrastructure fixes from 2026-05-25: LLM credential resolution, model-specific baseline selection, and smoke script argv/baseline handling.

This issue is a regression fix, not a score-optimization issue. Any future attempts to improve deepseek above 44.7% must be introduced behind a separate experiment flag or separate issue after this fix passes the existing deepseek baseline threshold.

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Update deepseek baseline to Run 3 37.0% | Makes smoke pass immediately | Codifies a measured regression and hides the adversarial/open_domain failure | **Rejected**: baseline must represent the last valid run, Run 2 44.7%. |
| Keep Phase 1 prompt and only tweak category 5 hint | Smaller patch | The global `never abstain` instruction still conflicts with adversarial scoring and encourages wrong-premise answers | **Rejected**: root instruction must be removed from default prompt. |
| Keep category 4 year extraction with heuristics | Could help some temporal-looking open_domain answers | Already caused high-confidence false reductions to `2023`; category 4 is not reliably date-only | **Rejected**: year extraction is allowed only for category 2 temporal answers. |
| Keep relaxed non-adversarial gate thresholds | Slightly reduces empty contexts | Observed benefit was only 2 questions; it changes retrieval behavior without improving F1 | **Rejected**: default gate returns to config/default 0.35 and 0.02. |
| Add an LLM verifier for all adversarial questions | Could improve category 5 | Adds latency/cost and another model-dependent failure mode to smoke | **Rejected**: out of scope for rollback; use prompt/normalizer guardrails only. |
| **Rollback harmful Phase 1-3 changes and add regression tests** | Restores known-good baseline and prevents repeat failures | Does not attempt a new score increase in this issue | **Adopted**: safest path to recover regression detection. |

### Key Decisions from Discussion

1. **Run 3 is a regression, not a new baseline** — Reason: overall F1 fell below the model-specific threshold and the drop is explained by concrete prompt/normalizer failures.
2. **Rollback is default-on** — Reason: the benchmark must first return to the last valid behavior before new experiments are added.
3. **Keep LLM routing and baseline selection fixes** — Reason: Run 1 credential failure was a separate infrastructure issue fixed before Run 2.
4. **Do not remove category plumbing immediately** — Reason: `runner.py` and adapters can continue passing category for future diagnostics/tests, as long as default gate/prompt behavior is Run 2-compatible.
5. **Add raw answer observability** — Reason: current result JSON stores only final `prediction`, making prompt vs normalizer failures hard to separate after a smoke run.

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `benchmarks/locomo/answer_prompt.py` | Modify | Restore Run 2-compatible prompt semantics, set `LOCOMO_ANSWER_MAX_TOKENS=512`, remove default category-specific answer hints, remove default relaxed gate constants, restrict year extraction to category 2 only. |
| `benchmarks/locomo/adapter.py` | Modify | Keep helper imports if useful, but ensure default confidence thresholds come from loaded config/defaults instead of Phase 2 relaxed values. Preserve fixed `No information available.` behavior when retrieval gate abstains. |
| `benchmarks/locomo/neo4j_adapter.py` | Modify | Mirror prompt/max-token/normalizer rollback where the shared prompt module is used, so Legacy and Neo4j benchmark adapters do not diverge accidentally. |
| `benchmarks/locomo/runner.py` | Modify | Add optional result fields for `raw_prediction`, `normalized_prediction`, `abstain_reason`, and top retrieval score when adapter exposes them. Existing `prediction` remains the scored final answer. |
| `benchmarks/locomo/baselines/legacy_scope_all_deepseek_v4_flash_20260525.json` | No change | Keep Run 2 baseline at overall F1 0.4470. Do not replace with Run 3. |
| `scripts/locomo_legacy_smoke.sh` | No change unless needed | Keep model-specific baseline selection and threshold check. |
| `tests/unit/benchmarks/test_locomo_answer_prompt.py` | Modify | Add regression cases for cat5 abstain preservation, category 4 no year-only extraction, and single-line CoT/truncation behavior. |
| `tests/integration/test_locomo_legacy_smoke.py` | Modify | Add a cheap fixture-level regression check using Run 2/Run 3 representative samples without calling the LLM. |
| `benchmarks/locomo/README.md` | Modify | Document that Run 3 was rejected and that prompt/gate experiments must be ablated before baseline update. |

#### Change 1: Restore default prompt semantics

**Target**: `benchmarks/locomo/answer_prompt.py`

```python
# Before: Phase 1-3 behavior
"If ANY memory is even loosely related, you MUST answer with your best short guess — never abstain when context exists"

# After: Run 2-compatible behavior
"If the context supports a reasonable inference, provide your best answer — only say \"No information available.\" when the context has absolutely no relevant information"
```

The default prompt must not contain category-specific instructions that override this rule. Category-specific experiments are out of scope unless placed behind a non-default experiment flag.

#### Change 2: Restore token budget

**Target**: `benchmarks/locomo/answer_prompt.py`

```python
# Before
LOCOMO_ANSWER_MAX_TOKENS = 128

# After
LOCOMO_ANSWER_MAX_TOKENS = 512
```

This avoids truncation artifacts observed in Run 3. Short-answer optimization can still happen via conservative post-processing, not by cutting the model mid-answer.

#### Change 3: Restore default gate thresholds

**Target**: `benchmarks/locomo/answer_prompt.py`, `benchmarks/locomo/adapter.py`

```python
# Before
non_adversarial: confidence_threshold=0.20, rrf_confidence_threshold=0.01
adversarial: confidence_threshold=0.35, rrf_confidence_threshold=0.02

# After
all categories: use loaded settings/defaults
default confidence_threshold=0.35
default rrf_confidence_threshold=0.02
```

The `category` argument may remain for observability, but it must not relax production-parity gate thresholds by default.

#### Change 4: Make normalization conservative

**Target**: `benchmarks/locomo/answer_prompt.py`

Rules:

- `No information available` / `not mentioned` normalization remains canonical.
- `which is X` extraction may remain only when the extracted span is short and the original answer explicitly uses that phrase.
- Year-only extraction is allowed only for category 2 temporal questions.
- Category 4 must never be reduced to a year-only answer by normalizer logic.
- If CoT stripping cannot confidently identify a final answer, return the first concise answer-like line only when it does not start with reasoning prefixes such as `We need`, `We are asked`, or `The question asks`.

### Edge Cases

| Case | Handling |
|------|----------|
| Category 5 with related context but wrong subject/person | Default prompt may answer `No information available.`; normalizer canonicalizes `not mentioned`/`No information available` to exact string. |
| Category 4 answer contains dates and non-date facts | Keep the model's phrase; do not reduce to a year. |
| Category 2 answer is verbose but ends with `which is 2022` | Normalize to `2022`. |
| Retrieval gate abstains | Adapter returns exact `No information available.` without calling the LLM. |
| Cross-encoder unavailable | Existing retrieval fallback remains; gate threshold uses RRF threshold from settings/defaults. |
| Result JSON compatibility | Existing `prediction`, `f1`, and `context_count` fields remain unchanged; new diagnostic fields are additive. |

## Implementation Plan

### Phase 1: Roll Back Harmful Defaults

| # | Task | Target |
|---|------|--------|
| 1-1 | Restore Run 2-compatible default answer prompt and remove global "never abstain" instruction. | `benchmarks/locomo/answer_prompt.py` |
| 1-2 | Set answer max tokens back to 512. | `benchmarks/locomo/answer_prompt.py` |
| 1-3 | Restore default gate thresholds to loaded config/defaults for all categories. | `benchmarks/locomo/answer_prompt.py`, `benchmarks/locomo/adapter.py` |
| 1-4 | Apply the same shared prompt/max-token behavior to the Neo4j adapter imports/usages if affected. | `benchmarks/locomo/neo4j_adapter.py` |

**Completion condition**: Default code path no longer contains Phase 1-3 behavior that caused Run 3: no global never-abstain instruction, no category 4 year extraction, no relaxed default gate thresholds, no 128-token answer cap.

### Phase 2: Add Conservative Normalizer Guardrails

| # | Task | Target |
|---|------|--------|
| 2-1 | Restrict year-only extraction to category 2. | `benchmarks/locomo/answer_prompt.py` |
| 2-2 | Add tests proving category 4 answers are not collapsed to `2023`. | `tests/unit/benchmarks/test_locomo_answer_prompt.py` |
| 2-3 | Add tests for canonical adversarial abstain text. | `tests/unit/benchmarks/test_locomo_answer_prompt.py` |
| 2-4 | Add tests for single-line reasoning prefixes that previously leaked into predictions. | `tests/unit/benchmarks/test_locomo_answer_prompt.py` |

**Completion condition**: Unit tests cover the Run 3 failure modes without requiring an LLM call.

### Phase 3: Add Smoke Diagnostics

| # | Task | Target |
|---|------|--------|
| 3-1 | Expose raw and normalized answer values from adapter answer generation without changing scored `prediction`. | `benchmarks/locomo/adapter.py`, `benchmarks/locomo/neo4j_adapter.py` |
| 3-2 | Include `raw_prediction`, `normalized_prediction`, `abstain_reason`, and top retrieval score in result JSON when available. | `benchmarks/locomo/runner.py`, `benchmarks/locomo/run_neo4j.py` |
| 3-3 | Document how to use diagnostics for prompt/gate ablations. | `benchmarks/locomo/README.md` |

**Completion condition**: A future smoke run can distinguish retrieval abstain, raw LLM abstain, normalizer output, and scored prediction from the JSON alone.

### Phase 4: Verify Against Deepseek Baseline

| # | Task | Target |
|---|------|--------|
| 4-1 | Run unit tests for prompt/config/smoke helpers. | `tests/unit/benchmarks/` |
| 4-2 | Run `./scripts/locomo_legacy_smoke.sh --skip-neo4j` in an environment where `deepseek-v4-flash` via `vllm-lb` is available. | local smoke |
| 4-3 | Confirm result passes existing baseline threshold: overall >= 0.4270 and open_domain >= 0.3733. | smoke result JSON |
| 4-4 | Confirm adversarial F1 is not below 0.75 unless a new investigation explains the change. | smoke result JSON |

**Completion condition**: The smoke script exits 0 against the Run 2 deepseek baseline, and the result JSON has enough diagnostics for future ablations.

## Scope

### In Scope

- Roll back harmful Phase 1-3 prompt/gate/max-token defaults.
- Keep valid LLM routing and model-specific baseline fixes.
- Keep Run 2 deepseek baseline as the active regression baseline.
- Add unit/integration guardrails for the Run 3 failure patterns.
- Add additive diagnostics to LoCoMo result JSON.

### Out of Scope

- Raising deepseek score above 44.7% — Reason: this issue is for regression recovery.
- Updating the deepseek baseline from Run 3 — Reason: Run 3 is below threshold and has identified defects.
- Qwen 397B remeasurement — Reason: different model/path and unrelated to this regression fix.
- LLM judge evaluation — Reason: smoke baseline is F1-only.
- Search-quality experiments such as top_k, chunking, BM25 weighting, or new rerankers — Reason: Run 3 regression is explained by answer/gate behavior, not retrieval quality.
- Full adversarial verifier LLM — Reason: adds cost/latency and should be designed separately.

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Reverting prompt loses some Run 3 gains | Some individual non-adversarial questions that improved may regress | This is acceptable because Run 3 overall regressed; future gains require ablation-gated experiments. |
| Removing category-aware gate prevents retrieval recall experiments | Potential recall improvements are delayed | Keep category plumbing available but default thresholds restored; experiment flags can be added later. |
| Raw/normalized diagnostics change result JSON size | Slightly larger smoke artifacts | Fields are additive and do not affect scoring. |
| Full smoke is slow | Feedback loop remains 1.5-3 hours | Unit tests cover representative failures; full smoke remains acceptance gate. |

## Acceptance Criteria

- [ ] `benchmarks/locomo/answer_prompt.py` no longer contains the global "never abstain when context exists" instruction in the default prompt.
- [ ] `LOCOMO_ANSWER_MAX_TOKENS` is restored to 512 for default LoCoMo answer generation.
- [ ] Default Legacy `scope_all` confidence gate thresholds are 0.35 and 0.02 unless overridden by config, with no category-based relaxation by default.
- [ ] Category 4 normalization cannot reduce a non-temporal answer to `2023` or another year-only answer.
- [ ] Category 2 verbose answers ending in an explicit `which is 2022` style phrase can still normalize to the year.
- [ ] Category 5 abstain variants normalize to exact `No information available.`.
- [ ] Result JSON includes additive diagnostics sufficient to distinguish retrieval abstain, raw LLM output, normalizer output, and scored prediction.
- [ ] Unit tests covering the above cases pass.
- [ ] `./scripts/locomo_legacy_smoke.sh --skip-neo4j` passes against `benchmarks/locomo/baselines/legacy_scope_all_deepseek_v4_flash_20260525.json` in the configured deepseek environment.
- [ ] The deepseek baseline JSON remains sourced from `/tmp/locomo_smoke_20260525_131445.json` and is not overwritten by Run 3.

## References

- `/tmp/locomo_smoke_20260525_131445.json` — valid deepseek Run 2, overall F1 0.4470.
- `/tmp/locomo_smoke_20260525_215811.json` — Phase 1-3 Run 3, overall F1 0.3699.
- `benchmarks/locomo/baselines/legacy_scope_all_deepseek_v4_flash_20260525.json` — active deepseek baseline.
- `benchmarks/locomo/answer_prompt.py:55` — conflicting global never-abstain instruction.
- `benchmarks/locomo/answer_prompt.py:140` — unsafe category 4 year extraction.
- `benchmarks/locomo/adapter.py:579` — answer token cap usage.
- `benchmarks/locomo/metrics.py:163` — category 5 scoring rule.
- `scripts/locomo_legacy_smoke.sh:71` — baseline threshold check.
