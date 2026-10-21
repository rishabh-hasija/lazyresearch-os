# LazyResearch OS

Give it the things you were too lazy to read, organize, or research. LazyResearch OS is designed to find what matters in saved URLs, documents, and pasted text, combine personal evidence with fresh public research, and show what is worth knowing or doing. Saving should be easy; organization is the system's job.

**Hacktoberfest Week 3 theme:** Slow and Steady. **Current phase:** source analysis (Tasks 1A/1B/2A complete).

The pure domain foundation, persistent intake, and configurable source analysis are implemented for URLs, pasted text, TXT, Markdown, and text PDFs. Originals commit before extraction; immutable analyses retain exact extraction citations and action proposals. Expiring PostgreSQL leases support recovery and reject stale workers. Research runtime, retrieval/embeddings/ranking, UI/API, exports, and deployment remain planned.

Development uses **Python 3.12**, SQLAlchemy **2.0.x**, Alembic, psycopg 3, pypdf 6, Pydantic **v2**, pytest, Ruff, and strict mypy. PostgreSQL 17 is the development baseline (tested on **17.11**); any compatible provider can supply DATABASE_URL. The domain remains standard-library-only. The approved future UI is Streamlit; the public demo uses synthetic content.

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

The RTK prefix follows this workspace's agent instructions. This slice exposes library use cases, not an application entry point.

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

Start with [Product](docs/PRODUCT.md), [Architecture](docs/ARCHITECTURE.md), [Data model](docs/DATA_MODEL.md), [Partners](docs/PARTNERS.md), and [Roadmap](docs/ROADMAP.md). [Status](docs/STATUS.md) records verified results; [Next](docs/NEXT.md) defines Task 2B for the next user-authorized instruction. [Agent instructions](AGENTS.md) govern future work.
