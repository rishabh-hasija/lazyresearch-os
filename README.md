# LazyResearch OS

Give it the things you were too lazy to read, organize, or research. LazyResearch OS is designed to find what matters in saved URLs, documents, and pasted text, combine personal evidence with fresh public research, and show what is worth knowing or doing. Saving should be easy; organization is the system's job.

**Hacktoberfest Week 3 theme:** Slow and Steady. **Current phase:** local Streamlit MVP (Tasks 1A/1B/2A/2B/3A/4A/4B implemented; **supervised public Render demo deployed and verified**).

The pure domain foundation, persistent intake, configurable source analysis, and scoped personal retrieval are implemented for URLs, pasted text, TXT, Markdown, and text PDFs. Originals commit before extraction; immutable analyses and retrieval chunks retain exact extraction citations. Lexical search works independently of embeddings; optional local qwen3 embeddings and pgvector support semantic/hybrid retrieval. Research Missions combine scoped evidence, optional public discovery, Gemma synthesis and immutable publication through Temporal. What Matters supplies a transparent baseline and optional local TabPFN with explicit-feedback/evaluation gates. The local Streamlit application exposes intake, What Matters, research history/evidence and action review. Exports remain planned; see Deployment below.

## Start here: what goes in, what happens, what comes out

**Public demo: one shared synthetic workspace, no authentication.** Anyone with the URL
can read and change it. Uploaded/saved data **persists in Neon (PostgreSQL)**; it is **not
temporary browser storage**. Do **NOT** upload personal/private information. Use synthetic/demo
material only. This demo makes no production privacy guarantee.

### The simple version

```text
URLs · PDFs with text · TXT/Markdown · pasted notes or text
                         ↓
Save the original → extract readable text → Gemma analyzes it
                         ↓
Find saved evidence: exact words + optional meaning-based search
                         ↓
What Matters → ask a research question → worker researches it durably
                         ↓
Optional current public-web evidence → Gemma writes a cited brief
                         ↓
Review evidence, previous versions, What Changed and source-backed actions
```

Your originals stay separate from generated analysis. PostgreSQL is the durable source of
truth (Neon hosts the current demo), including saved originals, analysis, research versions,
actions, explicit preference feedback and evidence. Refreshing/closing the browser does not
remove saved data. A separate supervised research worker must be online to finish missions;
source analysis is an explicit operation and is not an automatic background source runner.

What Matters prioritizes saved material with an honest rules baseline. As you give enough
explicit feedback, TabPFN can personalize relevance **only after evaluation supports it**.
The UI says **Learning your preferences** for baseline mode and **Personalized for you** only
for actual evaluated personal mode. Generic samples do not count as personal history.

**Email/Gmail connection is not implemented.** For now, paste email text or upload supported
exported PDF/TXT/Markdown content (synthetic content only in the public demo). Future Gmail
integration should select labels, senders or explicit searches, with preview and revocation,
rather than ingesting the whole mailbox by default.

### The technical mapping

| Stage / partner | Role and current limits |
|---|---|
| URL/file/text intake | Saves original bytes separately from extraction and generated output; supports URLs, text PDFs, TXT/Markdown and pasted text. No OCR or email connector. |
| Gemma via Ollama | Analyzes saved sources and synthesizes the final cited research brief on the supervised model host. Originals are never overwritten. Render cannot reach the owner's local model directly. |
| qwen embeddings + pgvector | Optional semantic retrieval over compatible indexed chunks; disabled by default. Missing embeddings retain lexical retrieval. |
| PostgreSQL lexical search | Exact-lexeme retrieval over saved text, independent of embeddings; all query terms must match. Long natural-language questions can yield no evidence. |
| TabPFN | Optional relevance prediction after sufficient explicit feedback and held-out evaluation; baseline remains the fallback. The current Render image uses baseline ranking. |
| Temporal / research worker | Durable, recoverable mission execution and immutable cited result publication; the web queues requests in PostgreSQL. A live supervised external worker is required. |
| SerpApi | Optional current public-web discovery with explicit per-mission permission. No live search/key was verified in the current hosted demo. |
| PostgreSQL / Neon | Canonical durable storage configured by provider-neutral DATABASE_URL: originals, separate analysis, research versions, evidence, actions and feedback. Neon is the current host. |
| Render / Streamlit | Public interface for Add Sources, What Matters, Research and Actions; one shared synthetic workspace with no authentication. |
| Outputs | Prioritized What Matters, cited research briefs, exact evidence/history/What Changed, and source-backed actions for human review. No external action execution or exports. |

For a first walkthrough: save a synthetic note, inspect it under Add Sources, review What
Matters, create a Research topic, and ask for example: "Should I buy a 10 kWh home battery now,
and what should I verify first?" Inspect the brief's evidence and review any Actions. The
question is an input example, not a promise of sufficient evidence or a verified recommendation.

Development uses **Python 3.12**, Streamlit **1.66.1**, SQLAlchemy **2.0.x**, Alembic, psycopg 3, pypdf 6, Pydantic **v2**, pytest, Ruff, and strict mypy. PostgreSQL 17 is the development baseline (tested on **17.11**); any compatible provider can supply DATABASE_URL. The domain remains standard-library-only. The local demo uses synthetic content.

From PowerShell in the repository:

```powershell
rtk proxy python -m venv .venv
rtk proxy .\.venv\Scripts\python.exe -m pip install -e '.[dev]'
rtk proxy .\.venv\Scripts\python.exe -m pytest -v
rtk proxy .\.venv\Scripts\python.exe -m pytest tests/integration -v
rtk proxy .\.venv\Scripts\python.exe -m ruff check .
rtk proxy .\.venv\Scripts\python.exe -m ruff format --check .
rtk proxy .\.venv\Scripts\python.exe -m mypy src
```

The RTK prefix follows this workspace's agent instructions. The local application entry point is described below.

## Run the local application (Task 4B)

Prerequisites: Python 3.12, configured PostgreSQL 17 (tested 17.11), and explicit migrations.
Install development/UI dependencies in the existing environment:

```powershell
rtk proxy .venv/Scripts/python.exe -m pip install -e '.[dev,ui]'
```

Copy `.env.example` to ignored `.env` and configure its existing settings. To export an explicit
local env file into the current PowerShell process without printing its values:

```powershell
foreach ($taskSetting in Get-Content -LiteralPath .env) {
    if ($taskSetting.Trim() -and -not $taskSetting.TrimStart().StartsWith('#') -and $taskSetting.Contains('=')) {
        $taskName, $taskValue = $taskSetting.Split('=', 2)
        [Environment]::SetEnvironmentVariable($taskName.Trim(), $taskValue.Trim(), 'Process')
    }
}
rtk proxy .venv/Scripts/python.exe -m alembic upgrade head
rtk proxy .venv/Scripts/python.exe scripts/run_ui.py --env-file .env
```

The launcher binds **127.0.0.1:8501**, disables Streamlit usage telemetry, and loads `.env` only
because `--env-file` was explicitly passed. Environment values already present take precedence.
Without that flag, only exported environment settings are used. Startup never migrates or starts
model/research services. Open [the local app](http://127.0.0.1:8501). This is not a verified
one-command machine setup. Restart the app after code/configuration changes for a clean build;
cached Python/service objects can survive a development hot reload or browser refresh.

The four sections are Add Sources, What Matters, Research and Actions. **Load sample sources** is an
optional, explicit, idempotent intake of two synthetic battery texts. It creates no fake analyses,
feedback or research results. The default fixed owner is a shared synthetic/demo workspace;
`UI_OWNER_ID` may select a separately scoped UUID. There is no authentication or private multi-user
security claim. Keep all inputs synthetic/demo until a separate access/retention task is approved.

Saving/extracting and reading prior content do not require Ollama. **Analyze next source** explicitly
runs one pending analysis in the UI request. Ollama must be running with the configured **gemma4:e4b**
(or another explicitly configured supported model). No model is downloaded or substituted. The
optional **qwen3-embedding:latest** path remains off by default; lexical research requires no new
embedding generation. Existing vector configuration/indexing requirements still apply if enabled.

Research runs through the existing Temporal worker, not an in-memory UI task. In a terminal with
the same exported settings, run:

```powershell
rtk proxy .venv/Scripts/python.exe scripts/research_worker.py
```

The Temporal server must already be reachable. Do not start another process on an occupied port.
On this machine, the existing CLI and copied persistent state were verified with:

```powershell
rtk proxy .local-tools/temporal/temporal.exe server start-dev --ip 127.0.0.1 --headless --db-filename "$env:LOCALAPPDATA/LazyResearchOS/temporal-task4b-20261022.db"
```

The original project-directory state file was left intact after that CLI could not open it;
the same bytes worked under Local AppData. The exact Windows/path cause is unconfirmed. This is a
local development detail, not an application path requirement or production setup. A fresh machine
must explicitly provision a supported Temporal runtime; see [official CLI guidance](https://docs.temporal.io/cli).

Missing SerpApi credentials are visible in Research; personal-only requests remain usable. Queued
requests wait for the research service. Refresh reads actual progress/results. What Matters labels the
baseline honestly when TabPFN is absent or ineligible; `TABPFN_MODEL_PATH` can explicitly opt into
the existing local adapter. No demo seeds count as personal history. Actions support review/edit/
accept/complete/dismiss/reopen with provenance and optimistic revisions; they execute nothing
externally. Migration head is **0006**; PostgreSQL remains canonical.

See [UI walkthrough and limits](docs/UI_WALKTHROUGH.md), [STATUS](docs/STATUS.md) and
[NEXT](docs/NEXT.md). Render deployment is verified below; auth, connectors, exports and schedules remain outside this task.

## PostgreSQL setup

Copy `.env.example` to ignored `.env`, replace CHANGE_ME with a local password, and use the same password in POSTGRES_PASSWORD and the URLs. Compose can start isolated PostgreSQL on **127.0.0.1:55432**:

```powershell
rtk proxy docker compose up -d postgres
rtk proxy docker compose exec postgres createdb -U lazyresearch lazyresearch_test
rtk proxy docker compose exec postgres createdb -U lazyresearch lazyresearch_migration_check
```

The default database is lazyresearch_dev. This task's environment already has an isolated container named `lazyresearch-task1b-postgres` on that port, with all three databases and credentials in ignored `.env`; use it directly instead of starting another container on that port. Existing databases were not repurposed.

Application settings and Alembic read **environment variables**, not `.env` automatically. Export DATABASE_URL from your environment/secret manager, then migrate explicitly:

```powershell
rtk proxy .\.venv\Scripts\python.exe -m alembic upgrade head
```

No startup migration exists. Use only an empty isolated database such as lazyresearch_migration_check for downgrade/upgrade validation. Separate runtime and migration credentials before hosting; the local role is not a production permission policy.

Tests accept TEST_DATABASE_URL from the environment or ignored `.env` if unset. The database must be named `lazyresearch_*_test` (lazyresearch_test is accepted). Each integration test creates a random schema, migrates it, and drops only that schema. Missing PostgreSQL configuration fails integration tests; SQLite is not a substitute.

## Intake use case and recovery

Use `Settings.from_env()` and `build_intake(settings)` from `lazyresearch.bootstrap`, then call `IntakeService.ingest(owner_id, request_key, entries)` with a tuple of IntakeInput values. URL entries use SourceType.URL and `url`; pasted/TXT inputs use SourceType.TEXT and immutable `payload` bytes, optionally a `.txt` filename; Markdown uses SourceType.MARKDOWN, PDFs SourceType.PDF. No collection is required. Stable request keys retry the same batch without another capture; changed inputs under that key raise RepositoryConflict. A new capture uses a new request key.

`resume(owner_id, batch_id)` continues queued/expired intake leases and pending extraction of saved sources. `retry_failed=True` retries transient intake categories only. Original bytes, capture occurrence, saved receipt, and an EXTRACT job commit together. Extraction then commits its outcome plus an ANALYZE placeholder when text is available. There is no automatic background runner. `extract_saved(owner_id, content_id)` can resume current-version extraction. Standalone Windows scripts using PDF extraction need the standard `if __name__ == '__main__'` guard for subprocess spawning.

## Source analysis and local Gemma

After explicitly migrating to head, configure the AI variables in `.env.example` through the environment. Defaults are Ollama at **http://127.0.0.1:11434**, **gemma4:e4b**, a 120-second per-call timeout, 4,000 characters/chunk, 64 chunks, and 2,400 output tokens. The UTF-8 byte/context budget can make chunks smaller (currently 2,566 bytes at default prompt/settings). Nothing automatically downloads a model or starts Ollama. Gemma 4 E4B's 6.58 GB download was explicitly approved and benchmarked on this machine; see [benchmark results and limitations](docs/GEMMA_BENCHMARK.md). `AI_MODEL=gemma3:4b` selects the tested installed fallback. Unsupported AI_PROVIDER values fail explicitly.

`build_processing(settings)` returns `ProcessPendingContent`. Call `process_one(owner_id)` for the same owner used during intake. It returns SUCCEEDED with analysis_id, FAILED with a sanitized error category, or IDLE. Successful extractions become configuration-specific operations; their earlier pending dispatch placeholders are cancelled as superseded. Model calls run outside transactions. Analysis, relational evidence, immutable proposals, run outcome and job completion commit atomically. `SQLAlchemyAnalysisStore.get(owner_id, analysis_id)` restores the complete immutable artifact. No latest pointer is maintained.

Prompt/schema/pipeline constants live in `application/analysis_models.py`; change the appropriate version and actual prompt together when editing semantics. Model/runtime revision snapshots, prompt hash, schema/pipeline, full extraction hash, generation/budget parameters and extraction ID determine operation identity. Repeating unchanged work returns IDLE after success. Changing configuration creates another historical analysis. `SQLAlchemyAnalysisStore.retry_failed(owner_id, job_id)` explicitly retries a failed operation; `cancel` fences an active operation. Abandoned running attempts are recorded as LEASE_EXPIRED when reclaimed. Analysis leases allow two inference timeouts plus 30 seconds and renew between chunks. A crash can repeat inference; there is no exactly-once model-call guarantee.

The model selects preallocated evidence IDs. The adapter resolves them to exact immutable chunk spans/quotes; application and PostgreSQL validate scope, quote and PDF page again. Locators are chunk-level, not sentence-level. Each claim/entity/action requires evidence. `claim_review_cases` produces deterministic UNREVIEWED cases for later human support review. Citation resolution does not prove factual entailment; summaries/topics are generated orientation aids, and suggestions require review. Prompt injection is treated as source data with no tools or external action authority; this is a tested boundary, not a guarantee against every possible attack.

Chunks are deterministic, ordered and page-aware. Whitespace separators are recorded without model calls. Chunk outputs retain ordered summaries/claims/entities/actions; topics are deduplicated in first-seen order. Reaching AI_MAX_CHUNKS publishes explicit PARTIAL coverage and covered ranges. There is no cross-chunk synthesis or conflict resolution. Explicit ISO dates normalize only for low-uncertainty candidates with no competing ISO date in their cited evidence. Ambiguous/invalid/time-bearing wording remains raw and unresolved; candidates are retained.

Separate synthetic-only developer commands (not mandatory pytest checks):

```powershell
rtk proxy .\.venv\Scripts\python.exe scripts/benchmark_gemma.py --model gemma4:e4b
rtk proxy .\.venv\Scripts\python.exe scripts/smoke_processing.py
```

The benchmark uses only its built-in synthetic corpus and records local runtime/latency/validation observations. The smoke requires DATABASE_URL and creates a fresh synthetic owner/source/analysis in that configured database. Neither script loads `.env` implicitly. Output payloads are never included in the application's operational logs; benchmark JSON intentionally contains synthetic outputs for inspection.

BatchResult derives saved/duplicate/failed/pending counts separately from extraction outcomes. Encrypted/no-text PDFs remain saved with visible extraction failure/unavailability. Messages use sanitized categories. IntakeService provides full intake guarantees; ContentRepository.save_capture is a lower-level immutable snapshot/capture primitive.

## Current limits

Defaults: 20 entries, 10 MiB/upload or fetched body, 5 redirects, 5-second connect/read idle timeouts, 30-second total fetch deadline, 200 PDF pages, 15-second PDF extraction wait, 2 million extracted characters, 5 MiB per decoded PDF page stream, and 90-second leases. See `.env.example`. PDF parsing runs in a child process; the bounds do not provide a hard process memory sandbox on Windows.

Text decodes UTF-8 (optional BOM) or BOM-marked UTF-16 and normalizes line endings. HTML extraction ignores script/style content and never executes JavaScript. Other encodings can report DECODE_FAILED. HTTP uses no proxy/cookie/browser behavior, requests identity encoding, validates redirects/all DNS answers, pins a public IP, and verifies HTTPS hostnames. Non-ASCII URLs are rejected rather than rewritten; ASCII/Punycode hosts and percent-encoded paths can be supplied. Unsupported response media remains saved with extraction unavailable. No OCR exists.

Exact duplicates are owner-scoped: source type + submitted URL/external identity where present + raw SHA-256. Filenames do not prevent identical file reuse; different URLs/query strings stay distinct. A URL reverting to known bytes reuses that snapshot with a fresh capture. A subsequent novel snapshot links to the most recently captured source version. Captures retain submitted/final URL, timestamps, content type and HTTP status independently of immutable snapshot metadata. Normalized hashes never silently merge originals.

EXTRACT/ANALYZE claims use short transactions, SKIP LOCKED, expiry, and fresh tokens; writes validate owner/source/version/token/expiry. Finished work is not reclaimed. This is retry-safe persistence, not exactly-once external execution. Analysis renews leases between bounded calls; no general heartbeat service, scheduler, deployment-triggered reprocessing, or private-data access control is provided. A new intake capture can queue a new extractor version; earlier outcomes stay immutable.

Intended technologies: a modular monolith; configurable Gemma processing (initial candidate Gemma 4 E4B); TabPFN relevance prediction; SerpApi public search; Temporal durable missions; Render public hosting; provider-neutral PostgreSQL with optional pgvector. Tinker is an optional later experiment.

Start with [Product](docs/PRODUCT.md), [Architecture](docs/ARCHITECTURE.md), [Data model](docs/DATA_MODEL.md), [Partners](docs/PARTNERS.md), and [Roadmap](docs/ROADMAP.md). [Status](docs/STATUS.md) records verified results; [Next](docs/NEXT.md) records the owner-guided walkthrough and final demo/submission preparation. [Agent instructions](AGENTS.md) govern future work.

## Personal retrieval

Migrate explicitly to **0003/head**. `build_retrieval(settings)` returns RetrieveEvidence. After ingestion or a new extractor version, call `retrieval.store.index(owner_id, retrieval.chunks)` to materialize immutable chunks; repeat indexing is idempotent. Then call `retrieval.search(owner_id, query)` for configured defaults, or `retrieve(RetrievalRequest(...))` for collection IDs, lexical/vector flags, limit and per-source cap. Search is read-only; it does not silently run indexing/model work for unindexed sources. No scheduler exists.

Default chunks: 1,000 Unicode characters with 150-character overlap, split at PDF page boundaries. IDs include owner, immutable extraction ID, chunker version/size/overlap and exact offsets. A changed chunker creates new chunks. PostgreSQL validates exact text/page and rejects chunk updates. Whitespace-only separators are not search chunks. Results carry the chunk, content/extraction identity, exact SourceEvidence, title/URL/type and separate lexical/vector ranks/scores plus fused score. Ranking is not factual support or an answer.

Lexical search uses PostgreSQL **simple** tsvector + GIN and bound plainto_tsquery tokens with AND semantics. It preserves case-insensitive exact lexemes without stemming/stopword removal; native punctuation tokenization still applies. No raw SQL or tsquery syntax is accepted. Scope and visibility are enforced in SQL for both search paths and again when resolving fused evidence. Search selects only the newest extraction per ContentItem by extraction created_at then UUID, even if that newest extraction failed; it never quietly falls back to an older parser version. Until successful reindexing, new versions can yield no hits. Old chunks remain available by historical identity. Separate historical source snapshots remain active until explicitly hidden; lineage is not automatically collapsed.

Minimal collections: `create_collection(owner_id, name)` and `add_to_collection(owner_id, collection_id, content_id)` on the retrieval store. Membership is many-to-many with composite owner foreign keys. Multiple requested collections use union semantics. `set_visibility(owner_id, content_id, state)` after indexing accepts ACTIVE, ARCHIVED, DELETION_PENDING or DELETED; all but ACTIVE are excluded. These flags control retrieval, not erasure, authentication or a completed privacy deletion workflow.

Vectors are **off by default** (`VECTOR_SEARCH_ENABLED=false`). Installed and tested model: **qwen3-embedding:latest**, 4.7 GB, 4,096 dimensions. No model is downloaded automatically. Set the embedding settings in `.env.example` through your environment and explicitly enable vectors. `build_embeddings(settings).run(owner_id, limit=20)` generates missing embeddings outside DB transactions with fenced per-chunk leases; `retry=True` explicitly retries failed work. A failed retry stops that bounded invocation. Failed/missing embeddings never remove lexical chunks. Namespace hashes isolate model/revision, dimensions, normalization, query instruction and version; metadata records actual known revision/runtime and latency. No silent model switch occurs.

Migration 0003 attempts to enable pgvector safely. If unavailable or permission is denied, portable chunk/lexical tables still migrate and no native vector side table is created. Startup does not require pgvector. The migration-managed `embedding_vector` side table is deliberately excluded from ORM drift reflection; SQL constraints validate dimensions and link it to embedding metadata. It uses native pgvector, not a serialized substitute. Exact cosine search needs no HNSW/IVFFlat index. If capability becomes available after a lexical-only migration, an explicit later migration/setup step is required; startup does not install schema objects.

This machine's existing vanilla PostgreSQL container received the small `postgresql-17-pgvector` package (**0.8.7**); no DB/server replacement occurred. A new vanilla container will not retain that package. Install an appropriate trusted pgvector package/image explicitly when provisioning vector support; lexical mode remains usable without it. Downgrade removes task tables, retaining the shared extension.

Hybrid fusion uses **RRF k=60** over lexical and vector ranks, deduplicates chunk IDs and caps chunks per source. SQL also applies that cap before candidate limits to avoid long-document starvation. Candidate budget is bounded at 30–200, result limit defaults to 5, source cap to 2. Vector-disabled/unavailable/failed semantic requests report status and use lexical fallback, including when lexical was initially disabled. Hybrid ties vector quality on the small fixture and costs much more than lexical; see [retrieval evaluation](docs/RETRIEVAL_BENCHMARK.md).

Run the separate real-model evaluation with DATABASE_URL configured:

```powershell
rtk proxy .\.venv\Scripts\python.exe scripts/benchmark_retrieval.py
```

It creates fresh synthetic scopes/corpus, indexes chunks, performs actual local embedding generation and evaluates lexical/vector/hybrid modes over 12 labeled queries. It never runs as part of pytest, never loads `.env` implicitly, and never starts Research Missions.

## Research Missions

Migrate explicitly to **0004/head**. `build_research(settings)` wires ResearchOperations, PostgreSQLMissionStore, existing intake/retrieval, SerpApiSearch and OllamaResearchSynthesizer. `default_mission_scope(settings, public=False)` preserves configured retrieval/search budgets and requires explicit public permission. Use the store to create a topic, then `create_mission(owner, topic.id, question, scope)`. Topic association is explicit; every new mission freezes the current baseline and receives its own increasing run_sequence. The returned QUEUED receipt includes a durable dispatch intent.

Run `scripts/research_worker.py` with DATABASE_URL, AI, search and Temporal settings exported. It connects to an already-running Temporal service, reconciles dispatches every five seconds and runs the worker. It never migrates, downloads models or starts servers. On this machine the ignored `.local-tools/temporal/temporal.exe` can run a localhost-only development service:

```powershell
rtk proxy .local-tools/temporal/temporal.exe server start-dev --ip 127.0.0.1 --headless --db-filename .local-tools/temporal.db
rtk proxy .\.venv\Scripts\python.exe scripts/research_worker.py
```

The dev server is already running locally after Task 3A; do not start another process on port 7233. Its persistent file and downloaded CLI are ignored, not committed dependencies. See [mission measurements](docs/RESEARCH_MISSION_BENCHMARK.md) for exact versions and reproduction limits. Production runtime/hosting remains unimplemented.

The workflow retrieves personal chunks, detects explicit gaps, searches only when permitted and justified, fetches selected URLs through existing intake, freezes exact evidence, retains heuristic conflicts, synthesizes a structured cited brief, validates citations/actions and publishes atomically. It passes only IDs/counts through Temporal history. Stage outputs are durable database records. Failed public sources yield a PARTIAL brief only if supported findings remain; no evidence fails with no result. Missing SerpApi credentials do not block personal evidence or deterministic tests.

`store.get_topic`, `get_mission`, `get_result` and `versions` are owner scoped. Publication returns the existing result on retry; versions reflect publication order, while Current Brief follows the highest successful mission run_sequence. Baseline-relative changes retain source/evidence/model/recommendation/action distinctions. `cancel_mission(client, store, owner, mission)` fences publication in PostgreSQL before requesting workflow cancellation. The same mission cannot be rerun after terminal failure/cancellation; create another mission.

Mission scope defaults: max 3 public queries (currently one deterministic question query), 10 fetched sources, 5 concurrent source tasks, 900 seconds, 8 evidence chunks / 6,000 characters, 2,400 output tokens. Collection IDs, personal/public permissions, retrieval modes and tighter budgets are frozen per mission. Search queries derive only from the question, never private evidence. Pattern sanitization is not universal PII detection. Snippets are discovery hints, not citations. Primary chunks bypass unnecessary source-analysis calls.

Claims remain UNREVIEWED: exact citation validation is not factual entailment. Conflict detection and changed-claim pairing are heuristic. One bounded synthesis repair is permitted. The small real Gemma smoke passed citation validation but missed an explicit source task, so action extraction still needs human review. Historical snapshots remain immutable, and missing evidence never proves a claim false.

For optional local runtime tests, set TEMPORAL_TEST_ADDRESS=127.0.0.1:7233 before pytest; without it, only the three live Temporal tests skip. Ordinary deterministic mission tests use fake search/synthesis and real PostgreSQL. `scripts/smoke_research.py` separately runs real Gemma + Temporal + PostgreSQL on synthetic sources and one bounded SerpApi search/fetch only if a key is configured. It does not load `.env` implicitly. [STATUS](docs/STATUS.md) records actual validation; [NEXT](docs/NEXT.md) describes Task 4B, which requires a new instruction.

## What Matters ranking and feedback (Task 4A)

After explicit Alembic upgrade to head (0005), `build_catch_up(settings)` returns a baseline-first
application service. Call `.rank(owner_id, aware_utc_cutoff, interests=("Home Energy",), limit=50)`.
It returns immutable decisions for unreviewed active items with READ/KEEP/ACT/IGNORE scores,
displayed class, reasons, pending-analysis/deadline flags, BASELINE/PERSONAL mode and observation ID.
Use `content_id=...` for a reviewed item with its explicit class override. Predictions never archive
or delete content. Potential deadlines remain visible under any user override.

`PostgreSQLRankingStore.interact(owner, content, event_id, kind, occurred_at, explicit=..., ...)`
records append-only interactions. Reliable feedback uses `InteractionKind.FEEDBACK_LABELED`,
`explicit=True`, `observation_id` and a `Relevance` label. A correction supplies `supersedes` with
the current label event ID. Reuse the entire event, including timestamp, for an idempotent retry.
Archive/open/mission-selection events alone are never training targets. Event recording itself
does not perform an archive or external action.

Optional local TabPFN needs the `ranking` extra and an explicitly provisioned checkpoint path
passed as `build_catch_up(settings, tabpfn_path=...)`. Model absence/failure, sparse classes and
failed held-out improvement all preserve the labeled baseline. No generic/demo labels enter
production history. [RANKING_BENCHMARK](docs/RANKING_BENCHMARK.md) contains exact setup, feature
encoding, chronological/grouped evaluation, raw results, measured latency and known limitations.
No ranking UI, automatic schedules or remote predictor was added.

## Deployment and public demo (Task 5A)

**License:** [MIT](LICENSE). Optional models/libraries keep their own licenses (Gemma: Apache 2.0 per its model card;
TabPFN checkpoint attribution in [RANKING_BENCHMARK](docs/RANKING_BENCHMARK.md)).

**Status:** `Dockerfile`, `render.yaml`, `scripts/serve.py`, `scripts/health.py`, `scripts/load_demo_data.py` and a
`APP_ENV=demo` banner exist and were verified locally (image build, container health, migrations from empty and from 0005,
idempotent demo load). **Public demo: [lazyresearch-os-demo.onrender.com](https://lazyresearch-os-demo.onrender.com/). Render, Neon and Temporal Cloud are live; hosted workflow and recovery verified.** The planned
topology is Render web + external PostgreSQL (`DATABASE_URL`, pgvector-capable) + owner-supervised Temporal worker and
Ollama/Gemma on a local GPU machine. Details, research, limits and commands: [DEPLOYMENT](docs/DEPLOYMENT.md).

Demo limits: synthetic data only, one shared workspace, no authentication; research/analysis work only while the
supervised worker and model host are online (source analysis is explicitly run locally); SerpApi live search is unverified (no key was available); the demo image
omits TabPFN, so What Matters shows the transparent baseline.

Partner roles (code): Gemma — `infrastructure/ai/ollama.py`; TabPFN — `infrastructure/ranking.py` (optional, local);
SerpApi — `infrastructure/search.py`; Temporal — `infrastructure/workflows/`; Render — `render.yaml`/`Dockerfile`
(deployed supervised demo).

Hosted verification on 2026-10-25 passed pasted-text intake, source inspection, baseline
What Matters, mission queueing while the worker was offline, real Temporal Cloud/Gemma completion,
exact citations/history, source-action acceptance and web restart/persistence.
The hosted assessment mission took 78.43 s including offline queue wait; synthesis 39.93 s.
Its result had two validated citations and no research action candidates. Seven real local
source analyses produced seven proposals, one accepted through the public UI.
The owner-run worker/GPU must remain online; Render cannot call the local model directly.
Source analysis is explicitly run on the owner machine. Pages/actions render incrementally
and can be slow on the free service. No live SerpApi search or hosted TabPFN is claimed.
See [deployment facts and timings](docs/DEPLOYMENT.md), [verification](docs/STATUS.md)
and [next task](docs/NEXT.md). Final submission polish has not started.
