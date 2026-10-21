# Next task: 3A — End-to-end Research Mission engine

Tasks 1A, 1B, 2A and 2B are complete and validated. The single next slice is an end-to-end Research Mission engine spanning personal retrieval, permitted SerpApi public research, durable Temporal orchestration, contradiction-aware synthesis, immutable ResearchResult publication, actions and change comparison. Wait for a new user instruction. Task 3A has not started.

**Recommended Codex: GPT-6 Astra, Medium reasoning. Alternative Claude Code: Claude Opus 5.** This slice crosses external systems, workflows, provenance and publication transactions. Apply AGENTS.md's model-selection guard; do not assume or claim to switch the active model.

## Read first and preserve

Read AGENTS, README, PRODUCT, ARCHITECTURE, DATA_MODEL, PARTNERS, STATUS, RETRIEVAL_BENCHMARK, GEMMA_BENCHMARK and relevant ADRs (especially durable workflows, source/analysis separation and immutable research versioning). Inspect the existing domain publication policy and retrieval/analysis/intake ports before designing runtime contracts.

Checkpoint 3987683 covers the completed foundation before 2B. Task 2B changes were left unstaged/uncommitted. Head migration is 0003. Preserve 0001/0002/0003 and validated intake/analysis/retrieval behavior. Use the established isolated PostgreSQL 17.11/.env setup without exposing credentials; downgrade only disposable databases/schemas.

Local models: gemma4:e4b for source analysis and qwen3-embedding:latest for optional retrieval embeddings. Selected embedding space is 4,096 dimensions with explicit normalization/query instruction/revision identity. pgvector 0.8.7 was installed in the isolated container; a fresh vanilla container may have lexical-only capability. Lexical remains default and works without inference or vectors. Reindex explicit chunks after new extraction versions; citation identities stay immutable.

## Expected responsibilities

- Freeze each mission's question, owner/topic, permissions, evidence scope, budget and baseline; allocate run sequence using the approved publication semantics.
- Use current owner/collection/visibility-scoped personal retrieval. Preserve exact source/extraction/chunk locators and retrieval metadata when creating mission evidence.
- Use SerpApi only for explicitly permitted public research. Sanitize queries and do not leak private source payloads/titles into search or workflow history. Inspect actual account/configuration and required credentials safely when this slice is authorized.
- Keep Temporal SDK objects in infrastructure. Durable workflows carry opaque IDs and bounded metadata; activities perform network/model/DB work outside deterministic replay.
- Bound activity budgets, retries, cancellation and recovery. Reuse persisted stage outputs with stable operation identities; do not promise exactly-once external calls.
- Introduce synthesis capability only as justified, separately from existing source analysis. Validate citation identity and represent contradictions, missing information and uncertainty without treating citation resolution as factual proof.
- Publish immutable ResearchResult/evidence/actions and completed mission state transactionally. Allocate versions under the approved topic lock and preserve mission/result uniqueness, frozen baseline and Current Brief ordering by run sequence.
- Failed/cancelled reruns leave the prior Current Brief intact; out-of-order completions preserve history without replacing a newer requested result.
- Produce deterministic added/removed/changed evidence/claim/action comparisons against the frozen baseline; distinguish model-only changes from new source snapshots.

## Verification and boundaries

Keep all **347 tests** passing. Add fake-provider deterministic mission/recovery/publication/concurrency tests and real PostgreSQL transactions. Run actual bounded SerpApi/Temporal/model smokes separately when configured and authorized; report unavailable checks honestly. Validate fresh and additive migrations, safe one-revision rollback/re-upgrade, drift, Ruff, formatting, strict mypy and git/untracked-file audits.

Update README/STATUS/NEXT with exact measured outcomes. Do not implement TabPFN/Catch Up prediction, Streamlit/API delivery, Render deployment, Gmail/RSS/Tinker, authentication, exports, OCR or autonomous external actions unless the new instruction explicitly authorizes them. Do not silently download multi-GB models or expose services publicly. Leave changes unstaged; no commit/push/amend unless requested.
