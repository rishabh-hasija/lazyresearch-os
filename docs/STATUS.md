# Verified repository status

As of 2026-10-21, Europe/Berlin. **Tasks 1A/1B/2A are complete and validated. Task 2B has not begun.**

## Task 2A result

Implemented configurable source analysis, immutable ContentAnalysis/cited statements, source-backed ActionProposal persistence and per-attempt ProcessingRun audit. Selected **local Ollama 0.40.6 / gemma4:e4b**. The user explicitly approved the 6.58 GB download before it began. No remote provider, research synthesis, retrieval, ranking, missions, UI/API, deployment, connectors, auth, exports or OCR was added.

Recommended Codex **GPT-6.1 Sol / Medium**, alternative **Claude Sonnet 5**. Active setting could not be independently verified; the repository's identity-unknown rule was stated and followed. No model switch or subagent was used.

New modules: domain/analysis.py; application/analysis_models.py and analysis.py; ports/ai.py; infrastructure/ai/__init__.py and ollama.py; infrastructure/persistence/analysis.py. Updated domain/actions.py with immutable candidate kind/uncertainty; persistence/models.py, config.py and bootstrap.py; .env.example and pyproject.toml. Added Pydantic >=2.10,<3, installed **2.14.1**. Domain stays standard-library-only; no AI SDK or generic agent framework.

Added migration **0002_versioned_source_analysis_and_.py**, preserving 0001. New tables: processing_run, content_analysis, action_proposal, analysis_evidence. Composite keys retain owner/content/extraction scope; quote/page triggers and deferred publication constraints enforce evidence and atomic success. Successful artifacts and completed attempts reject updates. No mutable ActionItem or research tables were added.

New scripts: scripts/benchmark_gemma.py and smoke_processing.py. New tests: analysis_helpers.py, test_analysis.py, test_ollama_http.py, integration/test_analysis.py. Existing migration inventory test now includes four additive tables; previous behavioral assertions remain. README/STATUS/NEXT and factual implementation-state passages in ARCHITECTURE/DATA_MODEL/PARTNERS/PRODUCT/ROADMAP updated. [GEMMA_BENCHMARK](GEMMA_BENCHMARK.md) links all seven synthetic measurement/diagnostic/smoke JSON records.

## Contracts and behavior verified in 2A

AIProcessor.analyze accepts a bounded AnalysisRequest with owner/source/extraction identity, exact segment and configuration. It returns validated AnalysisOutputSchema plus call attempts or sanitized AIError. HTTP/Ollama objects stay in infrastructure. AnalysisStore supplies fenced claim/renew/publish/fail operations; application ProcessPendingContent owns orchestration.

Versions: prompt **source-analysis-v4**, schema **analysis-v2**, pipeline **source-chunks-anchors-bytes-v3**. Structured summary/topics/entities/claims/actionability/candidates use Pydantic strict validation and forbidden extra fields. Insufficient information/uncertainty remain expressible. At most one structural repair per chunk is audited; invalid citations fail without repair.

Model offset failures led to preallocated evidence IDs: the adapter resolves a selected known ID to the exact immutable segment. Application and PostgreSQL verify identity, exact quote, Unicode bounds and PDF page. Locators are chunk-level, not sentence-level. Claims/entities/actions require evidence. Citation resolution does not prove entailment: claim support remains **UNREVIEWED**, with deterministic claim_review_cases for later human review. Summary/topic orientation text is not separately certified as fact. Injection stays source data without tools; one successful attack fixture is not a universal security claim.

Chunks are deterministic, ordered and page-aware, bounded by characters plus a conservative UTF-8 context budget. Defaults: 4,000 characters, currently 2,566 source bytes, 64 chunks, 8,192 context tokens, 2,400 output tokens, 120-second per-call timeout. Whitespace separators retain coverage without inference. Ordered summaries/claims/entities/actions merge without new synthesis; topics deduplicate in first-seen order. Reaching the cap records explicit **PARTIAL** covered ranges.

Proposals retain candidate text/kind/uncertainty, analysis/processing identity, evidence and raw deadline. Only low-uncertainty explicit ISO dates without competing cited dates normalize. Relative, invalid, uncertain/conflicting and time-bearing wording remains unresolved; candidates survive parsing failures. No external action executes.

Configuration fingerprints include provider/model/revisions-or-unknown, prompt hash/version, schema/pipeline and generation/input budgets; operation version also includes extraction UUID. Runs retain extraction hash, parameters, timing, attempt and call/repair/error audit. Pending 1B analysis placeholders are superseded without fabricated success. Unchanged successful work returns IDLE; configuration changes create another immutable analysis. No latest pointer exists. Known revision snapshots are checked before inference; mutable tags still prevent a stronger reproducibility guarantee.

Inference runs outside transactions. Analysis/evidence/proposals and run/job success commit together. Leases cover two inference timeouts plus 30 seconds and renew between chunks; stale/cancelled/expired workers cannot publish. Explicit failed retry preserves prior attempts; abandoned attempts close as LEASE_EXPIRED on reclaim. DB failure after inference rolls back output and leaves recoverable state. Crashes can repeat computation and lose uncommitted call detail; exactly-once inference is not promised.

## Actual model and database verification

Hardware: **15.36 GiB RAM**, RTX 3060 Laptop GPU with **6 GiB VRAM**. Selected installed digest: `dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c`, Q4_K_M. Final corpus: **7/7 schema and locator validations passed without repair**, six requested fixture categories plus warm repeat. Final warm-batch median **7.629 s**; clear-deadline repeat **8.589 s**. First-ever initial-prompt request **103.134 s** including startup. Initial failures are retained in [the benchmark](GEMMA_BENCHMARK.md).

Installed gemma3:4b fallback comparison: **7/7 schema, 5/7 complete validation**, warm repeat 4.720 s with an earlier prompt. It was not rerun with the final prompt, so this is not a controlled model comparison. Gemma 4 remains selected because its final configuration worked locally. No automatic/remote fallback. The official [model card](https://ai.google.dev/gemma/docs/core/model_card_4) identifies Apache 2.0 licensing.

GPU-wide use rose from 14 MiB to around 4,573–4,585 MiB. Ollama reported 100% GPU but only 369 MB resident size, inconsistent with that reading. Exact model-attributed RAM/VRAM and peak memory were **not measured**. Separate [real model plus PostgreSQL smoke](gemma_postgres_smoke.json): **SUCCEEDED**, saved original, COMPLETE analysis, **2 claims / 1 action / date 2026-11-07**, using production wiring and a new synthetic owner in the isolated dev DB.

| Task 2A check actually run | Result |
|---|---|
| python -m pytest -v | **307 passed in 48.15s**, exit 0; all 218 earlier tests retained |
| python -m pytest tests/integration -v | **59 passed in 41.14s**, real PostgreSQL 17.11, exit 0 |
| python -m ruff check . | **All checks passed**, exit 0 |
| python -m ruff format --check . | **81 files already formatted**, exit 0 |
| python -m mypy src | **No issues in 35 source files**, exit 0 |
| python -m pip check | **No broken requirements**, exit 0 |
| Actual model benchmark | Final **7/7** schema/locator success; prior failures retained |
| Actual model + PostgreSQL | **SUCCEEDED**, 2 claims and 1 proposal |

Tests cover malformed/extra/missing output, bounded repair, fabricated references, invalid quotes/spans/pages, Unicode budgets, conservative deadlines, injection envelope separation, provider errors/revision changes, rollback after inference, two-worker claims, stale/cancelled/expired leases, retries/history, immutable outputs, actual PDF page/separator coverage and DB evidence constraints. Controlled real HTTP tests verify parsing, total response deadline and redirect rejection. Pytest never calls a real model.

Migration commands against explicitly isolated **lazyresearch_migration_check**: **upgrade head -> downgrade 0001 -> upgrade head**, all exit 0. Alembic drift check: **No new upgrade operations detected**. Isolated lazyresearch_dev upgraded to 0002 for actual inference. Integration tests also validate fresh migrations and one-revision downgrade/upgrade preserving saved 1B data. Existing Docker/PostgreSQL and ignored credentials were reused; no unrelated DB was downgraded.

Limitations: only Ollama is implemented. Human claim/action support review remains necessary. Large-document semantic quality, cross-chunk conflict resolution, multilingual inference, broad injection resistance, load/throughput and hosted routing are unmeasured. The byte bound is conservative for the tested runtime rather than a universal tokenizer contract. Remote-endpoint DNS/setup timing was not benchmarked. 1B fetch/PDF limits, private-data policy and deletion/backup gaps remain. No stronger factual, reproducibility or security claim is made.

Git: unborn main; **94 nonignored files**, all untracked/unstaged, including prior tasks. No staging/commit/push. `git diff --check` exited 0 and `git status --short` confirmed no staged files. Because diff excludes untracked files, a separate audit checked all **94 files**, **43 local Markdown links**, JSON validity, whitespace/final newlines/fences and accidental inclusion of the actual local DB password: **no errors**. Final database inspection found **0 leftover test schemas**. Ruff/format/mypy were rerun after documentation changes with the same passing results. Next only: **Task 2B — lexical retrieval + optional vector retrieval**, recommended **GPT-6.1 Sol / Medium**, alternative **Claude Sonnet 5**. Do not begin automatically.

## Historical Task 1B verification

The remaining sections preserve the earlier completed handoff. Their implementation-state descriptions and counts are historical; the Task 2A report above is current.

## Project phase

Approved architecture and Python stack. Task 1A's pure domain foundation remains intact, with a small additive capture-provenance extension. Task 1B implements persistent source intake, extraction, and recoverable leases. No AI, research runtime, embeddings/ranking, UI/API, or deployment is implemented.

The user reported GPT-6.1 Sol / Medium for this task, matching its recommendation. No model switch was requested or performed.

## Files and modules created/changed

Added root configuration: `.env.example`, `compose.yaml`, `alembic.ini`.

Added migrations: `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/0001_initial_durable_intake_storage.py`.

Added application: `src/lazyresearch/application/__init__.py`, `intake_models.py`, `intake.py`.

Added infrastructure: `src/lazyresearch/infrastructure/__init__.py`, `config.py`; `persistence/__init__.py`, `database.py`, `models.py`, `repositories.py`; `sources/__init__.py`, `http.py`, `extract.py`.

Added wiring/ports: `src/lazyresearch/bootstrap.py`, `src/lazyresearch/ports/intake.py`.

Added tests: `tests/__init__.py`, `conftest.py`, `db_fixtures.py`, `http_fixtures.py`, `test_config.py`, `test_application_boundaries.py`; `tests/sources/test_http.py`, `test_extract.py`; `tests/integration/test_intake.py`, `test_pdf.py`, `test_recovery.py`, `test_url.py`.

Changed `pyproject.toml` for actual runtime dependencies, full test discovery and the integration marker. Ruff explicitly recognizes frozen scalar-only IntakeLimits as a safe immutable argument default. Extended `domain/content.py` CaptureOccurrence with optional final URL/content type/HTTP status; original required fields and prior tests remain compatible. No framework/provider imports entered domain.

Updated README, STATUS, NEXT and only factual implementation-state passages in ARCHITECTURE, DATA_MODEL, PRODUCT and ROADMAP. No research/action ORM, placeholder partner adapters, or unrelated refactor was added.

## Implemented behavior

- Batch intake: stable owner/request key with frozen input fingerprint; independent entry states/outcomes, derived summaries, explicit saved versus extraction outcomes, safe error categories. Repeated same request reuses receipts/captures; changed inputs under that key conflict. Queued local bytes are durable before extraction; rejected uploads retain metadata without their payload.
- PostgreSQL/SQLAlchemy persistence: seven intake tables, composite owner foreign keys, duplicate/entry/capture/job constraints, raw/normalized hash checks, immutable-update triggers for content/capture/extraction, and conversion to domain/application values at ports.
- Save ordering: snapshot + capture + saved entry + EXTRACT receipt commit together, then parsing occurs outside that transaction. Extraction outcome + completion/failure of the extraction job + an ANALYZE pending receipt for successful text commit together.
- Supported sources: batches of HTTP/HTTPS URLs; pasted text; `.txt`; `.md`/`.markdown`; text PDFs. Local upload type/size checks precede accepted snapshot storage. UTF-8/BOM and BOM-marked UTF-16 text decoding is conservative; line endings normalize separately from originals. HTML scripts/styles are omitted and never executed. Unsupported remote media is saved with extraction unavailable.
- PDF: pypdf 6.21.1 in a bounded child process; text/page offsets preserved; encrypted/malformed PDFs produce extraction failure while originals remain saved; no-text PDFs report extraction unavailable/OCR may be required. No OCR or active document execution.
- Exact duplicates: never cross owners; identity includes source type, conservative submitted URL/external identity when present, and raw SHA-256. Duplicate captures keep timestamp/submitted/final URL/media/status metadata. Different URLs/query strings do not merge. New URL bytes form linked snapshots; reverting to known bytes reuses the snapshot, with a new capture. The next novel version links to the latest captured version.
- HTTP: all redirect destinations and DNS answers checked, pinned public IP connections, preserved query parameters, verified TLS hostnames, bounded body/redirect/connect/read/total time, no environment proxies/browser/JS/decompression. Credentials, local/private/link-local/multicast/reserved and unsafe IPv6 transition destinations are rejected.
- Leases: short PostgreSQL FOR UPDATE SKIP LOCKED transactions, expiring unique tokens, per-owner/source/version checks, expired-lease reclaim, stale completion rejection and no reclaim of finished work. Intake receipt and processing leases survive new sessions. No general queue framework, scheduler, AI processor or Temporal workflow exists.

## Database environment and schema

Docker was installed but its daemon was stopped; no local PostgreSQL executable/service was found. Docker Desktop was started and a new isolated container `lazyresearch-task1b-postgres` was created with image postgres:17, bound only to 127.0.0.1:55432. Existing databases were not modified or repurposed.

Actual server: **PostgreSQL 17.11 (Debian 17.11-1.pgdg13+2)**. Isolated databases: lazyresearch_dev, lazyresearch_test and lazyresearch_migration_check. Random credentials are stored only in ignored `.env`; no credentials are in repository files or test output. The local dev role is for isolated development, not a production grants/authentication design. Provider-neutral URLs use PostgreSQL/psycopg; no hosting-provider SDKs.

Tables: owner_scope, intake_batch, intake_entry, content_item, capture_occurrence, content_extraction, processing_job; Alembic also maintains alembic_version. Job kinds are EXTRACT and ANALYZE. ANALYZE is a durable future-work receipt, not generated analysis or a full ProcessingRun model. ResearchMission, ResearchResult and ActionItem remain unpersisted.

Every integration test migrates a separate random schema inside lazyresearch_test, then drops only its own schema. Final database inspection found **0** leftover lr_test_* schemas. The isolated dev database is migrated to head. No unrelated database was downgraded.

## Dependencies and configuration

Python 3.12.10; SQLAlchemy 2.0.55 (project range >=2.0.36,<2.1), Alembic 1.20.0, psycopg/psycopg-binary 3.3.6, pypdf 6.21.1; pytest 9.1.1, Ruff 0.17.1, mypy 1.20.2. Dependencies were installed in local ignored .venv; editable project metadata was refreshed. No future AI/UI/workflow SDK installed.

DATABASE_URL plus intake limits are loaded explicitly by Settings.from_env. TEST_DATABASE_URL is separate. `.env.example` contains placeholders only. Production settings/Alembic do not implicitly load `.env`; test configuration may load its test URLs. Limits and setup commands are in README.

## Validation actually run

All Python commands use `.venv\Scripts\python.exe` through `rtk proxy`.

| Check | Verified result |
|---|---|
| `python -m pytest -v` | **218 passed in 19.97s**, exit 0; includes all 148 previous domain cases |
| `python -m pytest tests/integration -v` | **33 passed in 18.37s**, exit 0; real PostgreSQL, including concurrency, leases, rollback, source updates, PDF and migrations |
| `python -m ruff check .` | **All checks passed!**, exit 0 |
| `python -m ruff format --check .` | **66 files already formatted**, exit 0 |
| `python -m mypy src` | **Success: no issues found in 28 source files**, exit 0 |
| `python -m pip check` | **No broken requirements found**, exit 0 |
| `docker compose config --quiet` | Exit 0 with local password passed privately through environment |

Migration validation actually executed Python/Alembic module commands through a wrapper that selected only the explicitly isolated migration URL: downgrade base -> upgrade head -> downgrade base -> upgrade head, all exit 0. The first reset cleared the earlier draft schema in that disposable database; the subsequent upgrade/downgrade/upgrade validated the final revision. The isolated dev DB's `python -m alembic upgrade head` exited 0. `alembic.command.check` against the migrated database reported **No new upgrade operations detected**. Fresh initial upgrades also ran per integration schema, including one explicit test of downgrade/base then upgrade/head.

Import boundaries passed: the existing 10 domain checks and the new application/ports check reject SQL/HTTP/parser/infrastructure imports in inward layers. Real PostgreSQL race tests cover duplicate snapshots and same-request submissions; stale processing/intake tokens cannot overwrite new owners. Failure injection verifies snapshot/capture/job rollback together and recovery afterward. Independent-session inspection verifies the original source is committed before extraction.

Network testing: **real controlled loopback HTTP server**, with a test-only injected transport mapping a validated public address to that server; production private-network checks stay enabled. No random public website or external HTTPS smoke test was used. PostgreSQL tests use actual TCP/database transactions. Internet access was used for reference research, dependency downloads and the PostgreSQL image, not application test fixtures.

During development, tests caught an HTTP/1.0 socket-wrapper lifetime issue on Windows; a retained shutdown handle now enforces the deadline across headers/body. A later verbose run had 216 passes and one intermittent slow-header classification failure: the deadline callback could abort before a coarse sampled clock advanced. An explicit timer-fired event now classifies that shutdown as FETCH_TIMEOUT. A deterministic coarse-clock regression was added; the final full verbose run passed all 218 cases. Type/lint failures were corrected. No failing tests were hidden or SQLite substitutes used.

## Known limitations / unresolved work

No known failing 1B checks. OCR, legacy text encoding guesses, Unicode URL rewriting, automatic job runners/heartbeat renewal, deployment-triggered reprocessing, authentication and private-data retention/deletion implementation are out of scope. PDF subprocess time/page/text/stream bounds are not a hard memory sandbox on Windows; pypdf decompression may allocate before the stream-size check. No public HTTPS smoke test or broad database-provider compatibility matrix was run. Supported baseline is PostgreSQL 17.

An EXTRACT failure is terminal for its current version; retrying identical bytes does not silently overwrite that outcome. New versions/new captures can queue reprocessing. Analysis jobs are pending receipts only; Task 2A must introduce validated processing identities/outputs and idempotent persistence before doing AI work. In-memory domain construction is not database publication safety; research publication transactions remain future work.

The public demo policy remains synthetic data. Exact inference hardware/runtime, retention/backup policy, license selection and the challenge deadline discrepancy in ROADMAP remain unresolved before affected later work. No partner integration beyond PostgreSQL infrastructure is complete.

## Git and handoff

Unborn main; no commits. Verified inventory: **72 nonignored files**, all untracked/unstaged, including earlier tasks' files. `rtk git status --short` reports .env.example, .gitignore, AGENTS.md, README.md, alembic.ini, compose.yaml, docs/, migrations/, pyproject.toml, src/, tests/. Local .env, .venv, caches and egg-info are ignored. No staging, commit, or push performed.

`rtk git diff --check` exited 0; because all files are untracked, a separate inline audit checked all 72 files for trailing whitespace/final newlines, Markdown fences, all 31 local links, and accidental inclusion of the actual local database password. It exited 0 with no errors. Database inspection after the final suite again confirmed zero leftover test schemas.

Single next task: **Task 2A — configurable Gemma processing and evidence/action extraction**, as described in NEXT.md. Do not begin it automatically.
