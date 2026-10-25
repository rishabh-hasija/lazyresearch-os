# Temporal Cloud API-key/TLS support - 2026-10-25

Recommended: Codex GPT-6.1 Sol / Medium; Claude Code Sonnet 5.
Exact active model variant unavailable. No subagents, commit, push or Render deployment.
This section supersedes older statements that Temporal Cloud connection support is absent.

Implemented one shared official SDK connection path using Client.connect(api_key=..., tls=...).
Worker/reconciler, synthetic mission smoke and optional health probes all use it.
Temporal workflow definitions, PostgreSQL dispatch, domain/application and migrations are unchanged.
The existing local server remains usable without authentication. Address is now explicit:
missing/empty TEMPORAL_ADDRESS leaves Temporal unconfigured for web-only database use,
but connection commands reject it. Local .env.example retains 127.0.0.1:7233/default.

API keys are optional locally, mandatory for recognized Cloud endpoints, and omitted from repr.
TLS is explicit true/false or derived from the API key/Cloud endpoint; plaintext with a key/Cloud
is rejected. Cloud requires a non-default namespace. Malformed addresses, URL credentials,
empty enabled namespace/queue, invalid TLS and whitespace in keys fail without echoing values.
Shared connection and namespace failures suppress SDK exception messages/chained tracebacks.
No real key or endpoint was written to tracked files; the owner's ignored .env was not modified.

Health probes now verify namespace access with read-only DescribeNamespace, rather than only
server-wide health. Missing config skips networking; failed web probes state access is unverified
from this process. PostgreSQL still accepts/retains missions for the external worker.
Successful probes explicitly do not prove worker polling. Render startup/readiness has no new
Temporal dependency and no Temporal secret is needed on the web service.

Added scripts/smoke_temporal.py: explicit optional --env-file, no interpolation, process env
precedence, bounded connection/namespace read, generic PASS/FAIL only, no workflows or database/model
access. Worker and synthetic mission smoke continue to read exported env, without implicit files.

Files changed:
- .env.example; docs/DEPLOYMENT.md; docs/STATUS.md; docs/NEXT.md.
- src/lazyresearch/infrastructure/config.py.
- src/lazyresearch/infrastructure/workflows/connection.py (new), health.py.
- src/lazyresearch/infrastructure/health.py; src/lazyresearch/bootstrap.py; src/lazyresearch/ui/app.py.
- scripts/research_worker.py; scripts/smoke_research.py; scripts/smoke_temporal.py (new).
- tests/test_temporal_connection.py (new); tests/integration/test_mission_temporal.py.

Verification (existing .venv Python 3.12.10, every shell invocation through rtk):
- Initial inspection: clean git status; HEAD 2c3ffa7 Add Neon deployment support; prior commits
  2f65b49, bb5b48d, 9b4a68d, 0a54517.
- Focused pytest tests/test_temporal_connection.py tests/test_deployment.py -v:
  36 passed in 134.38s, exit 0.
- Full suite: python -m pytest -v through the existing .venv, with
  TEMPORAL_TEST_ADDRESS=127.0.0.1:7233 set only in the test subprocess:
  487 passed in 309.66s (5m09s), exit 0; no failures or skips.
  All 3 live local Temporal integration tests passed: publication/replay/dispatch retry,
  activity retry/worker restart/cancellation, source retry/publication acknowledgment loss.
  Existing PostgreSQL integration, PDF extraction and Streamlit UI tests passed.
- rtk proxy .venv/Scripts/python.exe -m ruff check .: All checks passed!, exit 0.
- rtk proxy .venv/Scripts/python.exe -m ruff format --check .:
  152 files already formatted, exit 0.
- rtk proxy .venv/Scripts/python.exe -m mypy src:
  Success: no issues found in 73 source files, exit 0.
- rtk proxy .venv/Scripts/python.exe scripts/smoke_temporal.py --env-file .env:
  Temporal connection and namespace access: PASS, exit 0; actual Cloud endpoint, API key and TLS,
  namespace matches quickstart-lazyresearch-demo.xesfo. No workflows started.
- Same smoke with explicitly exported local 127.0.0.1:7233/default, TLS false, no API key:
  Temporal connection and namespace access: PASS, exit 0. Existing local server reused.
- Actual-key scan of tracked and nonignored untracked files: 0 matches, exit 0.
- Final git diff --check: exit 0 (no whitespace errors).

During implementation, mypy caught the SDK RPC argument name (timeout, not rpc_timeout);
fixed before both live smokes. Ruff line length corrected. No unresolved implementation failures.

Limits: Cloud connectivity/namespace authorization is verified, but Cloud worker polling,
mission execution/recovery and hosted inference are not. No Cloud workflows were run.
No worker heartbeat or mTLS client-certificate configuration was added. Custom endpoint aliases
must be configured with the correct key/namespace; suffix detection does not discover endpoints.
Local workflows/replay/recovery run only against TEMPORAL_TEST_ADDRESS, explicitly set to the
existing local server for this task. Render deployment remains a separate authorized task.

Git: 15 changed files: 12 modified tracked files and 3 new untracked files; all unstaged. No staging, commit or push.

Historical verification follows.

# Neon PostgreSQL setup completed - 2026-10-23

This section supersedes the authentication-blocked attempt below.
Recommended: Codex GPT-6.1 Sol / Medium; Claude Code Sonnet 5.
Exact active model identity unavailable. No subagents, commit or push.

Retried neon login at user request: Auth complete (profile DEFAULT), exit 0.
neon deploy exited 0 against production (br-ancient-union-b92ofdc8):
No changes - branch production already matches the policy.
Utilized services: Postgres.
Pulled 3 Neon variables into .env: DATABASE_URL, DATABASE_URL_UNPOOLED, NEON_BRANCH.
Existing local test configuration was retained. Secrets remain ignored.

The empty production public schema was inspected before migrations. Created
temporary branch codex-neon-migration-check-20261023 from production with expiration.
Live direct-connection rehearsal passed base -> 0006, 0006 -> 0005 -> 0006 and
Alembic drift check (No new upgrade operations detected). Then production upgraded
to 0006; pgvector 0.8.6 available. Temporary branch deleted; branch list confirms
only production remains. Migration revisions and domain/application code unchanged.

Application keeps pooled DATABASE_URL with existing SQLAlchemy/psycopg 3;
Alembic prefers direct DATABASE_URL_UNPOOLED. Both pooled and direct client
connections verified TLS using psycopg pgconn.ssl_in_use. A server-side
pg_stat_ssl False result behind the pooler did not describe client transport.

Added python-dotenv as an explicit dependency. scripts/run_ui.py now parses quoted
Neon env values without interpolation, and preserves existing process env.
Added repeatable scripts/smoke_postgres.py, using real Streamlit AppTest and the
actual configured PostgreSQL database, no mocked database or model invocation.

Final verification:
- rtk proxy npm run build: exit 0, Successfully built lazyresearch-os;
  dist/lazyresearch_os-0.1.0-py3-none-any.whl.
- Started rtk proxy .venv/Scripts/python.exe scripts/run_ui.py --env-file .env --port 8503.
  HTTP GET /_stcore/health: ok. Stopped and restarted the app; health again ok.
- UI smoke saved a synthetic note via Save sources; extraction persisted in Neon.
  First smoke then failed on a wrong EvidenceCandidate field in the verification
  script; fixed to hit.chunk.content_id. Subsequent complete smoke exited 0:
  PostgreSQL pooled connection, client TLS and schema 0006: PASS
  Fresh workspace source read and lexical retrieval: PASS
  Streamlit Catch Up with live PostgreSQL: PASS
  PostgreSQL end-to-end smoke: PASS
- Same script --verify-only after app restart: same four PASS lines, exit 0.
  One clearly labeled synthetic smoke source is retained for repeat verification.
- Full pytest rerun after the Neon work (user-reported result): 455 tests collected;
  **452 passed, 3 skipped, 0 failed in 278.99s (4m38s)**. The 3 skips are the live
  Temporal integration tests because the local Temporal test environment was not active.
  All PDF extraction tests passed in this clean full run, confirming that the earlier
  PDF timeout failures were transient/environmental. This supersedes earlier
  statements that the full suite had not been rerun.
- Focused pytest (config/deployment/application boundaries/domain import boundaries),
  PGCONNECT_TIMEOUT=3: 24 passed in 6.84s, exit 0.
- Ruff check src tests migrations scripts: All checks passed!, exit 0.
- Ruff format --check src tests migrations scripts: 125 files already formatted, exit 0.
- mypy src: Success: no issues found in 72 source files, exit 0.
- pip check: No broken requirements found, exit 0.
- Final git diff --check: exit 0. Secret scan: PASS; nonignored tracked/untracked
  files contain no actual Neon URLs/passwords; .env/.neon/node_modules are ignored.

Failures resolved: initial browser sign-in timeout; smoke verification field typo;
initial TLS probe attempted a nonexistent ConnectionInfo attribute, corrected to
pgconn.ssl_in_use. Existing full offline Alembic SQL generation limitation at 0003
remains; actual live migrations are verified. The full-suite rerun result is recorded above.
Neon supplies PostgreSQL only. Render hosting, remote Temporal, model/search service
deployment and hosted research recovery were not part of this task and remain
unverified. App left running locally on port 8503 with Neon-backed configuration.

Historical attempts and earlier feature verification follow.

# Neon setup attempt - 2026-10-23 (authentication blocked)

Recommended: Codex GPT-6.1 Sol / Medium; Claude Code Sonnet 5.
Exact active model identity unavailable. No subagents, commit or push.

Global npm install of neon@latest succeeded (155 packages). Requested neon init
for org org-proud-waterfall-95717607, project empty-firefly-09124609, production,
Postgres only, exited 0. It wrote an OFFLINE, UNVERIFIED local link, neon.ts,
package.json/package-lock.json, and user-level Neon agent plugins/skills/MCP settings.
neon deploy exited 1: ERROR: Authentication timed out after 60 seconds.
neon profile list still reported DEFAULT with account/auth absent and missing
credentials. Asked owner to run neon login and finish browser sign-in.
No Neon env pull, hosted migration, hosted data write/read, or Neon E2E is verified.

Changes: retained SQLAlchemy/psycopg 3 and provider-neutral DATABASE_URL;
Alembic prefers optional DATABASE_URL_UNPOOLED for direct migration connections.
Added npm build wrapper scripts/build.mjs, which builds the actual Python wheel,
and ignored .neon/node_modules. Added example direct URL and setup handoff docs.
Local .env was not replaced by Neon because authentication failed.

Exact checks:
- rtk proxy npm run build: exit 0; Successfully built lazyresearch-os;
  produced dist/lazyresearch_os-0.1.0-py3-none-any.whl.
- rtk proxy .venv/Scripts/python.exe -m ruff check src tests migrations scripts:
  exit 0; All checks passed!
- rtk proxy .venv/Scripts/python.exe -m ruff format --check src tests migrations scripts:
  exit 0; 124 files already formatted.
- rtk proxy .venv/Scripts/python.exe -m mypy src:
  exit 0; Success: no issues found in 72 source files.
- Focused pytest files: tests/test_config.py, tests/test_deployment.py,
  tests/test_application_boundaries.py, tests/domain/test_import_boundaries.py:
  24 passed in 6.76s, exit 0, with PGCONNECT_TIMEOUT=3 via subprocess wrapper.
  Original run stalled on the unreachable-database probe and was interrupted.
- Alembic offline direct-URL selection with invalid fallback URL: PASS through 0002,
  exit 0. Full head SQL generation failed at existing 0003 because MockConnection
  has no scalar method (migration checks live extension capability). No revision changed.
- Started scripts/run_ui.py --env-file .env --port 8503: Streamlit started.
  GET http://127.0.0.1:8503/_stcore/health returned ok. Stopped after probe.
  This used existing local configuration, not Neon, and proves HTTP startup only.
- git diff --check: exit 0 before final handoff update; rerun recorded below.

Not run: full test suite, live Neon migration/intake/read/retrieval/restart tests.
Prior deployment status follows; its no-hosted-deployment limitation still applies.

# Task 5A — Deployment preparation (public deployment NOT performed)

**2026-10-22, Europe/Berlin**, from clean HEAD **bb5b48d**. Active model Claude Sonnet 5.5; recommended
Claude Sonnet 5 (reasonable equivalent). No subagent, commit or push.

**Outcome:** deployment artifacts and docs are done and locally verified. **No Render service, public URL, hosted
database, hosted Temporal, real SerpApi call, hosted recovery test, hosted performance run or screenshot exists.**
Those need the owner's accounts/credentials and a pushed branch (Render builds from Git); account creation and secret
entry were not attempted. See [DEPLOYMENT](DEPLOYMENT.md) for the topology decision and research.

Added: Dockerfile/.dockerignore, render.yaml, MIT LICENSE (+pyproject metadata), scripts/serve.py, scripts/health.py,
scripts/load_demo_data.py, infrastructure/health.py, application/demo_data.py, `system_health` in bootstrap, UI demo
banner and System-status panel, `APP_ENV` in .env.example, tests/test_deployment.py, docs/DEPLOYMENT.md, README section.
Migrations unchanged (head 0006). Domain/application import boundaries intact.

| Check | Result |
|---|---|
| Full pytest (TEMPORAL_TEST_ADDRESS set) | **447 passed, 8 failed** in 472 s: all 8 were PDF-extraction `EXTRACTION_TIMEOUT` while Docker Desktop was starting (machine loaded) |
| Rerun of the 3 affected files | **46 passed** (all 8 pass). Combined: 455 tests pass; no single clean 455 run |
| Ruff check / format | passed after auto-fix of import order and one reformat; final rerun below |
| mypy src | 72 files, no issues |
| Alembic | base→head, 0006→0005→0006 on isolated DB: ok |
| docker build / container health | ok, non-root |
| serve.py health | ok (~4 s) |
| Demo loader x2 | 5 sources, idempotent |
| History/tracked-file secret scan | DB password: 0 hits in tracked files and full history; no SerpApi key in .env |
| Dependency audit | `pip check` only; no vulnerability scanner run |

Known limits: Temporal Cloud TLS/API-key worker connection and authenticated remote Ollama are not implemented; the
web UI's Temporal probe will report unavailable on Render unless Temporal is reachable; free Render web cold-starts
~1 min; Render free has no workers; free Neon quotas unverified; paid Render sizes/prices unretrieved.
Cost estimate: Render free web + Neon free + local worker ≈ 0 EUR recurring, unverified; no hosted run happened.

# Task 4B — Minimal readable Streamlit application

Implemented and verified on **2026-10-22, Europe/Berlin**, from clean checkpoint **9b4a68d**
(committed Task 4A). Recommended **GPT-6.1 Sol / Medium**, Claude Code **Sonnet 5**. User
confirmed model 6.1 selected; exact runtime identity was not independently inferred. No
subagents, staging, commit, push or amend. This section supersedes historical records below.

## Delivered behavior and files

The four sections are Add Sources, Catch Up, Research and Actions. New application workspace
façade/models and narrow ports reuse existing intake/processing/ranking/indexing/mission/domain
action contracts. Bootstrap alone selects adapters. UI app/presenters contain delivery logic;
new PostgreSQL projections and action repository provide owner-scoped persistence. Migration
**0006** adds action review state only; **0001–0005 are unchanged**. Added the explicit local
launcher, bounded Temporal health probe, presenter/PostgreSQL/Streamlit tests and UI_WALKTHROUGH.
Updated dependencies, schema inventory, import-boundary checks and product/architecture/data/
roadmap/README/handoff docs. No FastAPI, React, connector, export or deployment was added.

Intake supports mixed batch URLs, pasted text and TXT/Markdown/text-PDF uploads, per-entry
receipts and explicit processing/retry. The optional idempotent sample button adds synthetic
sources only. Catch Up exposes honest baseline/personal gating, reasons, explicit four-class
feedback/corrections and deadline safeguards. Research saves scoped durable missions with explicit
public permission, actual status/cancellation, structured briefs, exact evidence, Current Brief,
history and stored baseline changes. Actions retain immutable proposals while edits and
accept/complete/dismiss/reopen persist separate optimistic-revision task state. No external
execution occurs. Empty/pending/partial/failed/unavailable states use sanitized messages.

## Actual verification

All shell/Python checks used rtk / rtk proxy. Final results:

| Check run | Result |
|---|---|
| Full pytest, TEMPORAL_TEST_ADDRESS=127.0.0.1:7233 | **451 passed in 163.72 s**, exit 0, no skips |
| Integration coverage in that suite | **111 cases**, including real PostgreSQL and **3 live Temporal** cases |
| Streamlit history regression after stable-ID fix | **1 passed in 8.31 s**; also included in final full run |
| Ruff check | All checks passed, exit 0 |
| Ruff format --check | **141 files already formatted**, exit 0 |
| Strict mypy src | **70 source files**, no issues, exit 0 |
| pip check | No broken requirements, exit 0 |
| Migration round trip/drift | 0006 → 0005 → 0006, fresh/all-revision tests and drift passed in disposable PostgreSQL schemas |
| Explicit development DB upgrade | Verified localhost lazyresearch_dev, upgraded to 0006; No new upgrade operations detected |
| Streamlit startup | localhost:8501 health returned **ok** |

All 433 pre-4B tests remain passing. New tests cover input bytes/presenters/errors, owner isolation,
feedback/corrections, action lifecycle/edits/provenance/concurrency/SQL guards, migrations,
Streamlit form interactions, result versions/citations/research actions and partial public-search
failure. AppTest uses deterministic fake providers with real PostgreSQL; live Gemma is separate.
An intermediate fixture attached a deadline to a no-date note and a persisted evidence decoder
used Python instead of strict JSON restoration; both were corrected before final passing runs.
The real-browser second publication exposed a stale topic DTO retained by Streamlit selection.
Selectors now store stable IDs and resolve fresh records; regression publishes v2 while the page
is open, then verifies Current Brief v2 and preserved historical v1.

## Browser and runtime observations

Real localhost Streamlit **1.66.1** + PostgreSQL + Ollama/Gemma walkthrough verified empty launch,
mixed valid text/invalid file URL, example.com intake, multi-file synthetic TXT/two-page PDF,
explicit real analysis/summary/topics/deadline action, baseline Catch Up, feedback persistence,
action provenance and accept/complete. Final feedback submission moved the TXT item to Useful
later with Your explicit choice and a success notice. Two real personal-only battery missions
completed through the separate Temporal worker. Answer/summary/findings exposed original quotes.
Final browser verified Current Brief v2, its frozen v1 baseline and model-only-change notice;
selecting previous v1 showed the original publication and first-brief notice. UI_WALKTHROUGH
records details.

Development hot reload retained old backend imports; restarting the UI resolved that cached
service mismatch. Restart after backend/config changes; browser refresh alone is insufficient.
An early feedback write survived that UI error in canonical PostgreSQL. Screenshot export timed
out in the computer-use tool; no screenshot artifact is claimed. Labeled native controls and
narrow-sidebar navigation were exercised; no exhaustive accessibility audit is claimed.

Temporal CLI could not open its project-path SQLite state although quick_check returned ok.
Original bytes/file were preserved and copied to Local AppData; the same CLI started successfully
there on localhost:7233. Exact Windows/path cause remains unknown. README documents explicit UI,
worker and local Temporal startup. No production service was installed or deployment performed.

## Limits and next task

Synthetic single-owner local demo only: no authentication or private multi-user security claim.
Refresh is manual, analysis is one source per explicit request, and research needs the separate
worker. Bounded list/excerpt reads lack pagination. Cancellation fences publication while an
in-flight bounded provider call may continue. Existing evidence support remains UNREVIEWED;
heuristic conflicts/diffs, bounded retrieval and model action-recall limits still apply.
No live SerpApi smoke, actual personal-history ranking-quality assessment, hosted verification,
privacy erasure, connectors, OCR, exports, schedules or external actions were added.

Community research found one relevant Streamlit ephemeral-state caution; PostgreSQL remains
canonical and no extra memory service was added. Source and evidence limits are documented in
UI_WALKTHROUGH. Challenge/event discovery was read-only; no submission/publication/message sent.

Next is the single **Task 5A — deploy and verify a reproducible synthetic demo**, bounded in NEXT.
Recommended **GPT-6.1 Sol / Medium**, Claude **Sonnet 5**. Do not start automatically.

Final working tree: **12 modified tracked + 14 untracked files**, all unstaged; HEAD remains
**9b4a68d**. No commit/push/amend. `git diff --check` passed; prior migrations 0001–0005 have
no diff from HEAD. Audit of **158 tracked/untracked files and 64 local Markdown links** found
no broken links, invalid JSON/fences or actual local-secret matches. No staged files and no
leftover `lr_test_%` PostgreSQL schemas. No unresolved test failure.

## Historical Task 4A handoff

Older sections below preserve historical test counts, working-tree states and next-task wording.

# Task 4A — Catch Up ranking with honest cold start

Implemented and verified on **2026-10-22, Europe/Berlin**, starting from clean checkpoint
**0a54517** (committed Task 3A). Recommended **GPT-6.1 Sol / Medium**, alternative
**Claude Sonnet 5**. Exact active identity was not reliably available and was not guessed.
No subagents, staging, commit, push or amend. This section supersedes historical state below.

## Changes and behavior

Added application/relevance_models.py, relevance.py, relevance_evaluation.py; ports/ranking.py;
infrastructure/ranking.py; persistence/ranking_models.py and ranking.py; migration **0005**;
scripts/benchmark_ranking.py; synthetic fixture/unit/PostgreSQL tests; RANKING_BENCHMARK.md and
raw ranking_benchmark_results.json. Updated bootstrap, migration imports, optional dependency
metadata, schema inventory and product/architecture/data/partner/roadmap/README/handoff docs.
Migrations **0001–0004 are unchanged**. No existing ingestion/analysis/retrieval/mission implementation
was refactored. Domain remains standard-library-only; TabPFN/Torch stay in infrastructure.

CatchUp selects owner-scoped unreviewed active sources and freezes versioned features from
existing extraction/analysis/captures/interactions at an aware cutoff. Missing analysis is
explicitly pending; no fresh model analysis happens during feature reads. Decisions retain
four-class probabilities, class/reasons, deadline visibility, model/mode/configuration/context
identity, exact source/extraction/analysis references and held-out metrics when attempted.
Current source visibility is rechecked before observation writes. Ranking never archives,
deletes, modifies source evidence/results or executes an action.

The deterministic rules baseline is visibly BASELINE. Only explicit FEEDBACK_LABELED supplies
READ/KEEP/ACT/IGNORE targets. Opens, ignores, archives, acted-on events, exposures and system
mission selections remain context, not inferred labels. Append-only event IDs support exact
retries; corrections explicitly supersede the current label and fence concurrent siblings.
Reviewed-source reads preserve the user's explicit override. Potential deadlines remain
visible and sort first even under IGNORE; absent an override they safeguard displayed ACT.

Personal mode requires enough explicit owner history (40 training labels, five/class), a
chronological held-out set (20 labels, two/class), macro-F1 improvement with no ACT-recall or
top-5 utility regression, and valid model output. Labels must have been available before the
test cutoff. Source/raw-hash groups, including transitive aliases, are purged across splits
and candidate context. Training uses stored features, not hindsight recomputation. Generic
synthetic examples are confined to tests/the benchmark and never bootstrapped as personal
history. Disabled/unavailable/invalid/unevaluated models retain the declared baseline.

Two PostgreSQL tables persist immutable observations and append-only interactions with scoped
foreign keys and guards. Feedback occurrence follows feature cutoff; DB receipt ordering is
checked using the DB clock for both records, avoiding an immediate-feedback app/DB clock
comparison bug found and fixed during verification. Labels before cutoff remain rejected.
Ordinary observation/event updates/deletes fail. Full privacy erasure remains unimplemented.

## Actual validation

All Python commands ran through `rtk proxy .venv/Scripts/python.exe`.

| Check actually run | Final result |
|---|---|
| Full pytest via Python wrapper setting TEMPORAL_TEST_ADDRESS=127.0.0.1:7233, then pytest.main(['-q']) | **433 passed in 119.73 s**, exit 0, no skips |
| Integration coverage in that full suite | **102 integration cases**, including real PostgreSQL and all **3 live Temporal** cases |
| Ranking-only unit/PostgreSQL suite before the clock regression case | **35 passed in 11.59 s** |
| Final ranking PostgreSQL suite, including clock regression | **15 passed in 11.68 s** |
| Ruff check | All checks passed, exit 0 |
| Ruff format --check | **127 files already formatted**, exit 0 |
| Strict mypy src | **61 source files**, no issues, exit 0 |
| pip check after editable metadata refresh | No broken requirements, exit 0 |
| Real local TabPFN benchmark (separate from pytest) | **84 train / 36 held out**, real four-class probabilities; repeated predictions identical |
| Migration checks | Fresh/base/all-revision test migrations; **0005 → 0004 → 0005** and Alembic drift in disposable PostgreSQL test schema, all passed |
| Isolated local development DB | Verified exact localhost lazyresearch_dev target, upgraded to **0005**; drift: **No new upgrade operations detected** |

The initial full suite passed 430 tests before final regressions were added. An intermediate
expanded run found a missing import in a new test and the immediate-feedback clock comparison
bug. Both were corrected; the final 433-test run above is clean. No unresolved test failure.
Ranking tests cover finite/exact probabilities/class mapping, missing checkpoint/classes,
small history, failed/equal held-out evaluation, future/foreign/self-group context exclusion,
transitive grouping, explicit overrides/deadlines, immutable cutoffs and artifact rows,
concurrent/stale correction fencing, exact retries, inactive/deleted sources and migration drift.
All **397 pre-4A tests** remain passing.

## Real predictor measurements and limitations

Installed optional **TabPFN 2.2.1**, **Torch 2.14.1+cpu**, **scikit-learn 1.6.1**, **NumPy 2.5.4**.
Built with PriorLabs-TabPFN. Public v2 classifier checkpoint: **29,009,539 bytes**, official
revision/hash/license attribution in [RANKING_BENCHMARK](RANKING_BENCHMARK.md). It is stored
under ignored .local-tools/ranking. CPU only, two estimators, seed 42, four threads; telemetry
disabled and no runtime checkpoint download. No remote data routing or credentials.

On 120 authored generic synthetic feature rows (30/class), held-out balance was nine/class.
Rules macro-F1 **0.54447**, TabPFN **1.00000**; ACT recall **1.0** for both; top-5 usefulness
**1.0** for both. The deliberately separable scenario fixture establishes actual integration,
not unbiased quality, personalization or calibration. Final cold import/fit/prediction
**11.3296 s**, repeated refit **0.9642 s**; initial run **28.5178 / 0.9058 s**. No memory or
latency-percentile measurement, confidence interval or real-user generalization claim.

The implemented feature set is deliberately narrower than the conceptual design: no authority
estimate, semantic topic/mission similarity or author/domain engagement aggregation. History
queries currently load before the 1,000-example inference cap. Personal evaluation/refits occur
per explicit rank request and need later performance work if measured UI usage justifies it.
No UI/API, action-status persistence, hosting, auth, erasure, connectors, exports or schedules
were added. Existing research/retrieval limitations and unvalidated real SerpApi access remain.
DevRelay community research and challenge/event discovery were attempted but returned an
MLH sign-in-service error; no article, consensus or current-event claim is fabricated.

Next task is **4B — minimal readable application experience**, bounded in [NEXT](NEXT.md).
Do not start it automatically. Recommended **GPT-6.1 Sol / Medium**, alternative **Claude Sonnet 5**.
Final working tree: **12 modified tracked + 14 untracked files**, all unstaged; HEAD stays
**0a54517**. No commit/push/amend. `git diff --check` passes. A tracked/untracked audit
checked **144 files / 60 local Markdown links**, JSON, fences, newlines, whitespace and actual
local-secret matches: **no errors**. No staged files. Prior-migration diff check also exited 0.

## Historical Task 3A handoff

All records below are historical, including their old next-task and working-tree counts.

# Task 3A — durable Research Missions

Implemented on checkpoint **4db9100** (Add hybrid retrieval and pgvector support). User confirmed the required model was selected; exact active identity was not independently available and was not guessed. Recommended **GPT-6 Astra / Medium**, alternative **Claude Opus 5**. No subagents, commit, push, amend or staging.

New modules: application/mission_models.py, mission_rules.py, mission_comparison.py and missions.py; ports/mission.py; infrastructure/search.py, ai/synthesis.py, persistence/mission_models.py and missions.py; infrastructure/workflows/research.py and runtime.py. Added migration 0004, worker/smoke scripts, synthetic test helpers, unit/search/PostgreSQL/Temporal tests, mission benchmark and raw synthetic smoke output. Updated research port, bootstrap/config, .env.example, dependency metadata, migration imports, schema inventory, Ollama's optional error classifier and documentation. Existing source-analysis transport behavior is preserved unless the synthesis-specific classifier is explicitly selected. Domain policies remain unchanged.

Six new tables persist explicit topics, frozen missions, immutable stage receipts, exact mission evidence, immutable results and result-derived ActionProposals. Scope includes owner/collections/personal-public permissions/retrieval modes/budgets. Topic locks allocate monotonic run_sequence and publication version separately. Publication invokes the existing pure-domain policy, commits result/proposals/mission completion together, and retains Current Brief by highest successful request sequence. Owner/topic/source/extraction/chunk foreign keys, exact-locator validation and immutability guards protect provenance. Research evidence is frozen before synthesis.

Personal retrieval reuses 2B; public discovery is conditional on explicit gaps and permission. The initial query strategy emits one sanitized question within a maximum of three. Private source text never enters query generation. SerpApi results are discovery only; selected URLs reuse secure intake, original bytes, extraction, deduplication and chunk indexing. Failed sources/search become explicit limitations; empty evidence produces no result. Source analysis is not redundantly required when original chunks are already available.

Gemma ResearchSynthesizer emits research-v1 cited answer/summary/findings/comparisons/recommendations/claims/actions. All known citation IDs and exact locators are validated, with at most one repair. Conflicts remain separately persisted even if synthesis omits them. Support stays UNREVIEWED. Heuristic conflicts cover dates/prices/quantities/versions/recommendations/freshness. Baseline-relative changes distinguish source/evidence/model/recommendation/action differences; snapshot sets eliminate row-order ambiguity. Missing evidence is not falsity. Action proposals retain original locators, result identity, stable ordinal and conservative raw/normalized deadlines.

Temporal SDK **1.34.0**, CLI **1.9.1**, server **1.32.0** run locally at **127.0.0.1:7233**. CLI/server files are ignored in .local-tools, with persistent dev storage and no public exposure. Workflows contain deterministic orchestration only; activities call application operations, with IDs/counts in history. Stage receipts and stable intake keys support recovery. Three transient attempts, source-specific activity boundaries, heartbeats, 900-second mission deadline, cooperative cancellation fencing and dispatch reconciliation are implemented. External calls can repeat across crash windows. Reconciliation handles ambiguous/missing starts and terminal workflow state. No generic agent framework or other infrastructure stack.

## Actual validation

- Final full suite with TEMPORAL_TEST_ADDRESS configured: **397 passed in 105.49s**, including all 347 pre-3A tests, **87 PostgreSQL integration tests** and all three live Temporal cases; no skips.
- Separate PostgreSQL/Temporal integration suite: **86 passed in 90.20s** before that additional case.
- Final three live Temporal tests: **3 passed in 17.06s**. Full mission completion/history replay; duplicate dispatch start; transient search retry across worker shutdown/restart; cancellation during synthesis; no-evidence failure; one-source timeout retry without rerunning its successful sibling; publication acknowledgment loss returns the same result.
- PostgreSQL concurrency tests: eight simultaneous request sequences; reverse completion produces versions/run sequences [(1,2),(2,1)] while Current Brief stays run 2; repeated publication does not duplicate proposals.
- Ruff: all checks passed. Formatting: **114 files already formatted**. Strict mypy: **54 source files**, no issues. pip check: no broken requirements.
- Isolated migration DB: **0003 → 0004 → 0003 → 0004**, passed; Alembic drift: **No new upgrade operations detected**. Fresh/all-revision migration tests also pass. Migrations 0001–0003 have no diff from checkpoint.

The deterministic Home Battery fixture verifies v1/v2, changed public price, new source, changed recommendations/actions, baseline preservation and current pointer. Fake providers test privacy/permissions, query/result bounds, duplicate discovery, provider failure, inaccessible sources, snippet exclusion, exact evidence, repair success/failure, malicious-source prompt separation and action provenance. HTTP contract tests cover SerpApi status/size/result bounds and safe failures. Prompt-injection tests verify architectural separation, not immunity to all model attacks.

Real Gemma + Temporal + PostgreSQL latest smoke: **gemma4:e4b / Ollama 0.40.6**, **2 evidence records**, **40.8077 s mission / 37.5769 s synthesis**, **one repair**, citations valid, result published, workflow completed. **2 findings, 0 optional claims-array entries, 0 actions**; answer/summary/recommendation also carry evidence. The explicit assessment task was missed by the model. The earlier run also missed actions. Raw synthetic output is research_mission_smoke.json; no action-recall or factual-entailment success is claimed. Real SerpApi smoke **skipped because credentials were absent**; no key request was necessary.

## Limitations and handoff

Heuristic conflicts/change pairing and pattern-based query privacy; lexical AND-token recall; bounded evidence/context; mutable model tags; model action-recall miss; no production Temporal setup or hard-kill/server-crash experiment. Worker replacement was exercised, as were replay and failure/cancellation paths. No UI, TabPFN, Render deployment, Gmail/RSS, Tinker, authentication, exports or OCR. Stage/result history can contain sensitive text in PostgreSQL and remains subject to a future privacy-erasure design.

Next task is **4A — Catch Up ranking with TabPFN and honest cold start**, recommended **GPT-6.1 Sol / Medium**, alternative **Claude Sonnet 5**. Await a new task instruction. Final git state: **16 modified tracked files + 22 untracked files**, all unstaged. Checkpoint **4db9100** remains HEAD. No commit/push/amend. `git diff --check` passes. Tracked/untracked audit: **130 files, 53 local Markdown links**, valid JSON/fences/newlines/whitespace and no actual local-secret matches. No leftover integration-test schemas remain.

## Historical Task 2B handoff

The following earlier reports are historical; the Task 3A section above is current.

# Verified repository status

As of 2026-10-21, Europe/Berlin. **Tasks 1A/1B/2A/2B are complete and validated. Task 3A has not begun.**

## Task 2B result and current handoff

Implemented deterministic immutable retrieval chunks, PostgreSQL lexical retrieval, independent EmbeddingProvider/VectorStore, optional native pgvector storage/search, hybrid RRF, collection filters, retrieval visibility/current-extraction policy, bounded embedding generation and labeled evaluation. User reported **GPT-6.1 Sol / Medium**, matching this task's recommendation; alternative **Claude Sonnet 5**. No model switch/subagent, research runtime, TabPFN, SerpApi, Temporal, UI, deployment, connectors, auth, exports or OCR was added.

Checkpoint **3987683** was clean at task start and was not amended. New source modules: domain/chunks.py; application/retrieval_models.py and retrieval.py; ports/retrieval.py; infrastructure/ai/embeddings.py; infrastructure/persistence/retrieval_models.py and retrieval.py. Changed config.py/bootstrap.py/.env.example, migration environment and the existing schema-inventory test. Added migration **0003_citable_chunks_lexical_and_optional_.py**, scripts/benchmark_retrieval.py, tests/test_retrieval.py, tests/integration/test_retrieval.py, RETRIEVAL_BENCHMARK.md, embedding_smoke.json and retrieval_benchmark_results.json. README/STATUS/NEXT and factual architecture/data/partner/roadmap passages updated. No new Python dependency was needed. Prior migrations **0001/0002 are unchanged**.

Chunk design: UUIDv5 identity includes owner, immutable extraction, chunker version/size/overlap and offsets. Defaults 1,000 Unicode characters / 150 overlap. PDF pages are separate ranges; whitespace-only separators are omitted. Chunks preserve exact text/hash/page and reject updates; PostgreSQL verifies citation text/page on insert. Changing chunker configuration preserves earlier chunks. Explicit store.index materializes current chunks idempotently after ingestion/extraction; retrieval is read-only and does not hide model/index work inside search.

Lexical strategy: native **simple** dictionary tsvector generated from chunk text, GIN index, bound plainto_tsquery AND-token matching, ts_rank_cd proximity ranking and UUID tie ordering. No embedding dependency, raw tsquery, separate search service or stemming. Both SQL candidate paths enforce owner, active visibility, current extraction/chunker and optional many-to-many collection membership before limiting results. Newest extraction is selected by created_at then UUID, including failed extractions; a newer unindexed/failed extraction never quietly exposes an old parser version. Archived/deletion-pending/deleted states are excluded. Flags are retrieval visibility, not erasure/authentication; historical ContentItem snapshots remain separate until explicitly hidden.

EmbeddingProvider accepts bounded text/config and returns validated vectors with provider/model/actual known revision, dimension, normalization, timing/runtime and observed input norms. It remains separate from AIProcessor. Selected local **Ollama 0.40.6 / qwen3-embedding:latest**, already installed **4,676,805,193 bytes**, Q4_K_M, **4,096 dimensions**, actual digest `64b933495768fbd3b87c20583d379728a07471e0c66733a9df87cd1901b3c44b`. No model download or silent substitution. Adapter sends truncate=false, bounds inputs/batches/timeouts, checks finite dimension/space and normalizes L2 explicitly. Namespace hashes include model/revision, dimension, normalization, query instruction and embedding version; different spaces coexist.

VectorStore persists owner/chunk/namespace metadata and fenced per-chunk status/attempt/error/runtime/latency, plus an optional native pgvector side table with dimension checks/FK. Inference is outside transactions; vector/status commit together. Failed work remains retryable; missing/failed embeddings do not alter lexical chunks. Successful rows are skipped, stale leases rejected, and namespace deletion/rebuild is owner-scoped. Workflow limits work per invocation; a failed explicit retry stops that invocation. Crashes can repeat computation. No general-purpose queue or Temporal.

pgvector was initially absent. A **274 KB** postgresql-17-pgvector package installed **0.8.7** in the existing isolated PostgreSQL **17.11** container, without server/database replacement. Migration 0003 creates five portable retrieval tables and optionally enables the public extension/native embedding_vector side table. Missing extension/permission support leaves lexical schema usable. A disabled-capability migration path is tested. The shared extension is retained on downgrade; native optional storage is explicitly excluded from ORM drift reflection. No HNSW/IVFFlat index. Container package changes are ephemeral and need reprovisioning on a fresh vanilla container.

RetrieveEvidence supports lexical/vector/hybrid modes, reports vector status, and uses lexical fallback for disabled/unavailable/failed semantic paths. Exact cosine search is namespace-isolated. RRF k=60 combines ranks without score calibration; chunk IDs deduplicate, SQL applies per-source caps before candidate limits, final fusion caps again. Default limit 5/source cap 2; candidate budgets 30–200. Re-resolution repeats scope/visibility predicates and the application rejects foreign-owner candidates even from an invalid adapter. Results preserve immutable source/extraction/chunk locators and component/fused scores. No answer synthesis or claim-entailment promise.

## Task 2B actual measurements and validation

Actual local embedding smoke: first single request **28.6491 s**, warm three-text batch **0.7176 s**, all 4,096 dimensions; observed norms **0.999999726–1.000000490**. Model-attributed memory was not measured. Actual pgvector insert/query of these spaces succeeded. Full evaluation: **13 owned documents / 16 chunks / 12 labeled queries**, plus another owner's matching distractor; **16 embeddings succeeded**, zero failures, indexing **7.6017 s**.

| Retrieval mode | Recall@5 | MRR | Mean source diversity | Mean query seconds |
|---|---:|---:|---:|---:|
| Lexical | 0.667 | 0.667 | 0.750 | 0.0143 |
| Vector | 1.000 | 1.000 | 4.750 | 0.5388 |
| Hybrid | 1.000 | 1.000 | 4.750 | 0.4834 |

Hybrid tied vector on this small authored fixture; no general superiority or latency comparison between semantic modes is claimed. Greater diversity includes distractors. Lexical remains default because it is model-independent and much faster; vectors are opt-in. See [RETRIEVAL_BENCHMARK](RETRIEVAL_BENCHMARK.md) and its raw JSON for exact corpus/labels, metrics and limits. Actual Ollama evaluation is separate from mandatory pytest.

| Task 2B check actually run | Result |
|---|---|
| python -m pytest -v | **347 passed in 60.87s**, exit 0; all 307 prior tests pass |
| python -m pytest tests/integration -v | **71 passed in 55.11s**, real PostgreSQL, exit 0 |
| python -m ruff check . | **All checks passed**, exit 0 |
| python -m ruff format --check . | **93 files already formatted**, exit 0 |
| python -m mypy src | **No issues in 42 source files**, exit 0 |
| Actual embedding/vector evaluation | **16 persisted embeddings**, all vector/hybrid queries executed |

Tests cover deterministic overlap/Unicode offsets/PDF pages/new chunk versions, exact lexical tokens, owner/collection isolation on both paths, inactive/deleted exclusions, newest extraction selection, bounds/source caps and long-source starvation, namespace/dimension isolation, missing/failed embedding fallback, explicit retry/stale lease fencing, RRF union/overlap/dedup/stable ordering/foreign-adapter defense, native nearest-neighbor search and unavailable-vector migrations. Domain/application import guards still pass.

Alembic against explicitly isolated lazyresearch_migration_check: **0002 -> head -> 0002 -> head**, successful; drift reports **No new upgrade operations detected**. Isolated dev DB upgraded to 0003 for actual evaluation. Fresh upgrades and disabled-capability downgrade/re-upgrade ran in isolated test schemas. No unrelated DB was downgraded. The native side-table reflection warning found during initial drift inspection was removed with pre-reflection exclusion; final check has no warning.

Limitations: small synthetic corpus, no held-out generalization, no semantic threshold/reranker/ANN, no multilingual/load benchmark, explicit reindexing required, native simple-token AND limitations and phrase splits across chunks. Current source snapshots are not lineage-collapsed; retrieval visibility does not implement privacy deletion. Extension denial/missing-package handling exists; fallback integration uses an explicit disabled-capability path rather than changing global extension permissions. Unknown runtime revisions remain unknown; mutable model tags still limit reproducibility. Optional native schema assumes the vector extension is in public and needs an explicit migration/setup step if capability arrives after a lexical-only upgrade. Lexical fallback remains available.

Final git state: checkpoint **3987683** remains HEAD; **12 modified tracked files and 14 untracked files**, all unstaged. No staging, commit, push or amend. `git diff --check` passed; separate tracked/untracked audit checked **108 files**, **48 local Markdown links**, JSON, whitespace/newlines/fences and accidental inclusion of the actual local DB password: **no errors**. Database inspection found **0 leftover test schemas**. `pip check` found no broken requirements. Ruff/format/mypy were rerun after documentation updates and passed with the counts above. Only next task: **3A — end-to-end Research Mission engine**, recommended **GPT-6 Astra / Medium**, alternative **Claude Opus 5**. Do not start it automatically.

## Historical Task 2A handoff

The following report and older sections are historical; the Task 2B report above is current.

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
