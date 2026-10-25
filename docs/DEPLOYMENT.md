## Neon setup verified (2026-10-23)

This supersedes the historical blocked attempt below. neon login succeeded;
neon deploy applied production and pulled DATABASE_URL, DATABASE_URL_UNPOOLED and
NEON_BRANCH into ignored .env. No additional Neon services were enabled.
Production schema is 0006; pgvector 0.8.6 is available. Live migration rehearsal on
a temporary child branch passed fresh install, downgrade/upgrade and drift check;
that branch has been deleted. Production pooled/direct client TLS verified.

Keep SQLAlchemy/psycopg 3. Runtime reads DATABASE_URL; migrations prefer
DATABASE_URL_UNPOOLED. Explicit env-file loading uses python-dotenv with
interpolation disabled to preserve passwords and handles quoted Neon values.
Hosted serve/worker entry points still read process environment only.

With the Python environment installed:

    npm install
    npm run build
    .venv/Scripts/python.exe scripts/run_ui.py --env-file .env --port 8503
    .venv/Scripts/python.exe scripts/smoke_postgres.py --env-file .env --verify-only

For first-time smoke use omit --verify-only: it explicitly saves a synthetic source
via the real Streamlit UI if missing. The verified source remains in production for
repeat checks. The smoke checks TLS/schema, real source extraction/read, lexical
retrieval and Catch Up; it makes no model/search calls. After stopping/restarting
the app, the verify-only smoke passed again. See STATUS for exact results.
npm build produces the actual Python wheel; it does not host the frontend.

For future migrations, explicitly load the env before invoking Alembic, e.g. from
Python with load_dotenv(".env", interpolate=False), then
alembic.command.upgrade(alembic.config.Config("alembic.ini"), "head").
Do not migrate automatically at app startup.
Render public hosting and remote Temporal/model deployment remain unverified.

### Historical initial attempt

## Neon setup attempt (2026-10-23)

Recommended: Codex GPT-6.1 Sol / Medium; Claude Sonnet 5. Exact active model was
unavailable. User authorized the specified existing production branch.

Global Neon CLI installation succeeded. Requested init linked project
empty-firefly-09124609, org org-proud-waterfall-95717607, branch production,
Postgres only. It created ignored .neon, neon.ts and npm metadata, and installed
user-level agent plugins/skills/MCP configuration. The link was written offline
and was not verified. neon deploy opened browser authentication but failed:
ERROR: Authentication timed out after 60 seconds.
No hosted database or env pull is verified. Owner must run neon login, finish
browser sign-in, then deployment can be retried.

Keep SQLAlchemy/psycopg 3 for the long-lived Python/Streamlit runtime. Neon provides
DATABASE_URL for pooled app traffic and DATABASE_URL_UNPOOLED for direct migrations.
Alembic now prefers the latter, falling back to DATABASE_URL for other providers.
See [Neon pooling guidance](https://neon.com/docs/connect/connection-pooling).

npm run build packages the Python app as a wheel in ignored dist/. It uses .venv
if present, otherwise PYTHON/python, and requires pip, setuptools and wheel.
Node dependencies are Neon configuration tooling only; this does not host the UI.

After login: retry neon deploy; inspect env names without exposing values; explicitly
load the pulled env for migrations and app launch; migrate using the direct URL;
seed synthetic fixtures; test actual intake/read/retrieval and persistence after
app restart against Neon. Local Streamlit health alone is not database proof.
Render hosting remains separate.

# Deployment (Task 5A)

**Status: deployment artifacts are prepared and verified locally. No public URL exists.** Creating a Render
account/service, a hosted database and a Temporal runtime needs the owner's accounts and credentials, and Render
builds from a pushed Git branch. None of that was done; nothing below claims a hosted run.

## Decision (simplest topology that honestly shows the product)

| Component | Choice | Why |
|---|---|---|
| Streamlit web | **Render web service** (Docker, `render.yaml`) | Only component that must be public. |
| PostgreSQL | **External, via `DATABASE_URL`** — recommended Neon (pgvector on every plan, TLS) | Render free Postgres expires after 30 days, has no backups, one per workspace. |
| Temporal | **Supervised, owner-run** (local `temporal server start-dev` or Temporal Cloud) | Render has no free background workers; Temporal Cloud free tier not confirmed in docs. Real Temporal is kept; no in-memory fallback. |
| Research worker | **Owner-run** `scripts/research_worker.py` (same image can run it: `python scripts/research_worker.py`) | Needs Temporal and the model host. |
| Gemma / qwen | **Owner's GPU machine (Ollama), not public** | See inference below. |
| SerpApi | `SERPAPI_API_KEY` secret on the web service **and** the worker | Search runs inside the worker; UI only reads it to enable the checkbox. |

The web process reads/writes PostgreSQL only; the worker's dispatch reconciliation (every 5 s) picks up queued
missions from PostgreSQL. The web service does not require Temporal or Ollama connectivity.
Temporal settings/secrets may be omitted on Render; direct probing is optional. An unconfigured
or unsuccessful web probe reports that Temporal access is unverified from this process, while
missions remain saved for the external worker. A successful probe proves namespace access,
not that a worker is polling. No worker heartbeat is implemented.

## Research findings (docs fetched 2026-10-22)

- Render free: web services (and Postgres/Key Value) only — **no free background workers**; web spins down after 15 min
  idle (~1 min cold start); filesystem is ephemeral; 750 free instance hours/month. Free Postgres: 1 GB, expires in
  30 days, no backups. Paid instance sizes/prices were **not retrievable** from the pricing page; GPU instances were not
  confirmed, so none are assumed.
- Neon: pgvector available on every plan (0.8.0 documented). HNSW/IVFFlat cap `vector` at 2,000 dimensions; this
  project uses exact search (no index) with 4,096-dimension qwen vectors, so it is unaffected. Free-plan storage/compute
  quotas were not verified.
- Temporal Cloud: the worker, mission smoke and optional health probe now share official Python
  SDK API-key/TLS connection support (2026-10-25). Local plaintext Temporal remains supported.
  See configuration and verification below; this does not verify hosted workflow recovery.
- Inference: measured locally — gemma4:e4b is 6.58 GB (Q4_K_M, 7.5B params) on an RTX 3060 6 GB laptop GPU; warm source
  analysis ≈ 7.6 s, research synthesis ≈ 38 s; qwen3-embedding is 4.68 GB, warm batch ≈ 0.7 s. These need a GPU or a
  large-RAM host; not practical on Render CPU instances. Do **not** expose raw Ollama to the internet.

## Public-demo policy

Synthetic data only, one shared owner, **no authentication** — the UI shows a warning when `APP_ENV=demo`. Anyone with
the URL can read and write that shared workspace; never enter private content.

## Inference options (the owner must choose; not implemented)

1. Keep Gemma/worker on the owner's machine; visitors browse seeded sources/Catch Up; analysis and research complete
   only while the owner is online ("supervised demo"). Recommended; no inbound exposure needed because both the worker
   and Ollama are local and talk to PostgreSQL outward.
2. Rent a GPU host and put Ollama behind an authenticated TLS proxy. Needs per-request auth that `AI_ENDPOINT` does not
   currently support (no header support) — a code change.

## Procedure

```bash
# 1. Create database (e.g. Neon); enable pgvector once:  CREATE EXTENSION IF NOT EXISTS vector;
# 2. Migrate explicitly (never on web start). Free Render web has no pre-deploy hook:
DATABASE_URL='postgresql+psycopg://…?sslmode=require' python -m alembic upgrade head
DATABASE_URL=… python scripts/load_demo_data.py      # idempotent synthetic fixtures
# 3. Push the repo, create a Render Blueprint from render.yaml, set the sync:false secrets.
# 4. Owner machine: temporal server start-dev; then with the same DATABASE_URL/SERPAPI_API_KEY:
python scripts/research_worker.py
# 5. Verify: python scripts/health.py   (database/temporal/ai, exit 1 only if database is not at 0006)
```

`/_stcore/health` (Render health check) proves only that Streamlit is up. Database/Temporal/model status is the
sidebar **System status → Check services** panel and `scripts/health.py`; a degraded model host does not stop the UI.

## What was verified locally (2026-10-22)

- `docker build` succeeded; container runs as non-root, health `ok`, connected to the local PostgreSQL, and
  `scripts/health.py` inside it reported database/Temporal/AI ok.
- `scripts/serve.py` binds `0.0.0.0:$PORT`, health `ok` after ≈4 s; exits with a clear message when `DATABASE_URL` is
  missing.
- Alembic on an empty database and 0005→0006 upgrade, on the isolated migration DB: pass.
- Idempotent demo loader run twice: 5 synthetic sources, no analyses/feedback/results fabricated.

## Not verified

Render deploy, public URL, real SerpApi call, hosted restart/recovery, hosted
performance, live Render cold start, screenshots (no stable browser capture was attempted).

## Temporal local and Cloud configuration (2026-10-25)

Every application connection uses the same SDK helper: worker/reconciler, synthetic mission smoke,
and optional web/CLI health probe. It calls official
[Client.connect](https://python.temporal.io/temporalio.client.Client.html) with `api_key` and `tls`;
no custom auth headers or transport. Workflow definitions, dispatch and persistence are unchanged.

| Setting | Local development | Temporal Cloud |
|---|---|---|
| `TEMPORAL_ADDRESS` | `127.0.0.1:7233` (explicit) | Exact gRPC host:port from the namespace console |
| `TEMPORAL_NAMESPACE` | `default` if omitted | Exact namespace/account name from console |
| `TEMPORAL_API_KEY` | Empty/omitted | Required, from an authorized secret store or ignored env file |
| `TEMPORAL_TLS` | `false` or omitted | `true` or omitted (derived from API key) |
| `TEMPORAL_TASK_QUEUE` | `lazyresearch-missions-v1` default | Same value on all workers/dispatchers |

Current owner-supplied namespace: `quickstart-lazyresearch-demo.xesfo`. This is documentation,
not a runtime default. Copy the endpoint from the console; no endpoint is inferred from this name.
Use only placeholders in tracked files, as shown in `.env.example`.

When the address is absent/empty, Temporal is unconfigured in that process; database/UI operations
still work. Commands that actually connect (worker or smoke) require an explicit address.
This removes the old implicit loopback target: local users should retain the address in
`.env.example` or export it explicitly. Exported environment variables are authoritative.

TLS defaults to true when an API key or a recognized Cloud endpoint is present, otherwise false.
Explicit `TEMPORAL_TLS=false` with any API key or Cloud endpoint is rejected before networking.
Known Cloud host suffixes (`.tmprl.cloud`, `.temporal.io`) additionally require an API key and
a non-default namespace. Custom endpoint aliases must supply the key/namespace explicitly;
host detection is validation assistance, not an endpoint discovery mechanism.
TLS-only self-hosted connections are supported; client-certificate/mTLS configuration is outside
this task. Invalid TLS booleans, malformed addresses/embedded credentials, empty enabled namespace/
queue and keys with whitespace fail with messages that omit values. Key and address are omitted
from settings repr; SDK connection/namespace failures are replaced with sanitized messages.

Local server and worker (using exported settings; worker does not implicitly load env files):

```powershell
rtk proxy .local-tools/temporal/temporal.exe server start-dev --ip 127.0.0.1 --headless
# In another terminal, export DATABASE_URL and the local Temporal settings above.
rtk proxy .venv/Scripts/python.exe scripts/research_worker.py
```

For Cloud, export the Cloud settings above on the external worker machine alongside DATABASE_URL,
AI and optional search settings, then run the same worker command. No inbound connection to the
worker machine is needed. Do not start a duplicate local server on an occupied port.

Repeatable read-only connectivity smoke (local or Cloud):

```powershell
rtk proxy .venv/Scripts/python.exe scripts/smoke_temporal.py --env-file .env
# Or, with settings already exported:
rtk proxy .venv/Scripts/python.exe scripts/smoke_temporal.py
```

Only an explicitly requested env file is loaded, with interpolation disabled and existing process
values taking precedence. A missing file fails clearly. The smoke needs no database or model service.
It connects, describes the configured namespace to verify access, and prints only PASS/FAIL.
It never prints credentials, starts workflows, writes database records or runs a worker.
The smoke has a 20-second overall bound; shared connection attempts have a 10-second bound,
namespace RPCs 5 seconds, and optional web probes 3 seconds.

Live Cloud smoke on 2026-10-25: PASS using the owner's ignored `.env`, API key and TLS;
configured namespace access verified without workflows. This proves connectivity and namespace
permission only. Worker polling, mission execution/recovery on Cloud, Render hosting and inference
availability need a subsequent authorized verification task.
