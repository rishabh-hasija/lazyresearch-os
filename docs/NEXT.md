# Next task: 2B — Lexical retrieval + optional vector retrieval

Tasks 1A, 1B and 2A are complete and validated. The single next slice is owner-scoped personal retrieval over immutable successful extractions, beginning with PostgreSQL lexical search. Optional vector retrieval requires a concrete embedding-model/runtime choice and capability check. Wait for a new user instruction; no retrieval implementation has started.

Recommended **Codex GPT-6.1 Sol, Medium reasoning**. Alternative **Claude Code Claude Sonnet 5**. Apply AGENTS.md's model guard; do not infer active identity from prior chats.

## Prerequisites and preservation

Read AGENTS, README, PRODUCT, ARCHITECTURE, DATA_MODEL, STATUS, GEMMA_BENCHMARK and relevant ADRs, particularly storage/provider neutrality, source/analysis separation and optional vectors. Inspect extraction/page mappings, owner scoping, migrations, analysis identities and inward dependency tests.

Reuse isolated PostgreSQL 17.11 and ignored .env; production settings/migrations do not automatically load .env. Head is 0002: seven intake and four analysis tables. Never print credentials or downgrade unrelated databases. Preserve immutable sources, extractions, analyses and proposals. Exact locators use half-open Unicode character offsets and one-based PDF pages. There is no mutable latest-analysis pointer.

Gemma 4 E4B is installed and selected locally. Keep actual model benchmarks separate from mandatory pytest. Do not redesign validated source processing without a demonstrated contradiction.

## Expected slice

- Introduce only the narrow application-owned retrieval contract/use case actually exercised. No research orchestration or synthesis.
- Build PostgreSQL lexical retrieval first: owner predicates on every join, deterministic ranking/tie order, bounded query/result budgets, source/extraction/capture identity.
- Return exact immutable evidence spans/pages; discovery snippets do not prove factual support. Avoid returning whole private documents by default.
- Choose and document a deterministic extraction-version policy per source; historical references remain pinned.
- If vectors are explicitly included, inspect pgvector permissions/capability and benchmark an approved embedding model. Separate EmbeddingProvider from AIProcessor/vector storage. Do not select the installed qwen3-embedding model merely because it exists; measure resources and fit first. Report/ask before any substantial unapproved download.
- Version embedding model/revision, dimensions, normalization and chunker/embedding-space identity; never mix incompatible spaces. Lexical-only retrieval must remain usable with vectors disabled/unavailable.
- Add a new additive migration only as required, preserving 0001/0002. An opaque serialized vector is not a replacement for a real vector capability.

## Validation

Keep all **307 existing tests** passing. Add meaningful tests for owner isolation, deterministic lexical results, exact quote/page restoration, bounds, unavailable extractions, duplicate captures and changed snapshots without provenance confusion. If vectors are included, separately validate actual extension/model capability, dimensions/space mismatches, fallback and measured retrieval behavior.

Run full pytest, real PostgreSQL integration tests, Ruff, format check and strict mypy. Validate upgrade from 0002 and a one-revision downgrade/upgrade only in a disposable database/schema; check Alembic drift. Check git diff/status and untracked-file whitespace/secrets separately. Update README/STATUS/NEXT with exact observed results and limitations.

## Boundaries

Do not implement TabPFN/ranking, public SerpApi search, Temporal, Research Missions/synthesis, UI/API, Render, Gmail/RSS/Tinker, authentication, exports, OCR or external actions. Do not start another slice automatically. Leave changes unstaged; no commit/push unless explicitly requested.
