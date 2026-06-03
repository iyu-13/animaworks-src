# Review: Legacy Entity Index Boost

Issue: `docs/issues/20260603_legacy-entity-index-boost.md`
Branch: `issue-20260603-134413`
Merge commit: `2cbd89be`
Final branch commit: `419cccdc`
Status: APPROVED

## Summary

The implementation adds a legacy-first entity registry and production entity boost path, then resolves all review findings from iterations 1 through 4.

## Review Findings

No Critical, High, or Medium findings remain.

Resolved during review:

- High: registry read-modify-write lost updates under concurrent fact ingestion. Fixed with process and OS advisory locking around registry load/upsert/save/rebuild.
- High: `LegacyRAGBackend.retrieve(scope="episodes")` bypassed RAGMemorySearch entity boost. Fixed by routing episodes through RAGMemorySearch.
- Medium: helper entity collection was write-only. Fixed by best-effort collection query fallback, filtered against authoritative JSON registry keys.
- Medium: entity collection sync re-embedded the full registry on every ingest. Fixed by resolving changed entity keys from stored facts and syncing only those entries.
- Medium: `entity_registry_enabled=False` did not disable registry writes/sync. Fixed by gating registry upsert and entity collection sync while preserving fact storage/indexing.
- Medium: `episodes` backend retrieval regressed `limit > 10`. Fixed by adding an internal `result_limit` through RAGMemorySearch.
- Medium: non-hybrid keyword fallback paths bypassed entity boost. Fixed by applying boost before fallback result slicing.
- Medium: `scope="all"` hybrid keyword fallback still sliced before entity boost. Fixed by passing `entity_boost` and `result_limit=pool_k` into the hybrid keyword fallback path.
- Low: stats counted `{anima}_entities` helper documents as memory chunks. Fixed by excluding the helper collection.

## Verification

- `ruff check` on changed memory/config/test files: passed.
- `python3 -m compileall` on changed runtime/test files: passed.
- Focused tests: `58 passed, 2 warnings`.
- Broad memory/RAG regression set: `110 passed, 2 warnings`.
- Targeted coverage: `86.21%` for `core.memory.entity_index` and `core.memory.retrieval.entity`.
- E2E marker suite: `174 passed, 2 skipped, 14431 deselected, 20 warnings`.
- `git diff --check main...HEAD`: passed before merge.

Full `pytest --tb=short -q` was attempted, but the repository-wide run hit unrelated Playwright browser installation errors in viewport E2E tests (`chromium_headless_shell` missing). The issue-specific E2E marker suite passed.

## Independent Review

- Cursor Agent review was attempted in iterations 1 and 2, but produced empty output/logs and was treated as unavailable.
- Codex subagent review found issues in iterations 1, 2, and 3; all were addressed by commits `ef36a57f`, `878c7bad`, and `419cccdc`.

## Residual Risk

- Registry `entity_type` remains empty because current `FactRecord` stores entity names but not extracted entity type/summary. The registry/document shape includes the field, but richer typing needs a follow-up schema extension.
