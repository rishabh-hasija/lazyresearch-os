# Next task: Render-hosted verification and challenge handoff

Recommended: Codex GPT-6.1 Sol / Medium; Claude Code Sonnet 5.
Escalate demonstrated networking/Temporal Cloud issues to GPT-6 Astra Medium /
Claude Opus 5. These are project recommendations, not tool-availability claims.

Neon PostgreSQL setup is completed and verified on 2026-10-23:
project empty-firefly-09124609, production branch br-ancient-union-b92ofdc8,
schema 0006, pgvector 0.8.6. DATABASE_URL (pooled) and DATABASE_URL_UNPOOLED (direct)
are in ignored .env; do not print or commit them. Alembic prefers the direct URL.
The temporary migration branch was deleted. Streamlit intake, read, Catch Up,
lexical retrieval and persistence after restart passed against the real Neon DB.
See STATUS for exact commands/outcomes and DEPLOYMENT for setup instructions.

Next authorized slice must address remaining hosting work; do not begin automatically.
Render Blueprint requires a pushed branch: ask before commit/push. Supply secrets,
decide supervised versus rented inference, optionally supply SerpApi key.
Temporal Cloud requires API-key/TLS connection support before use.
Verify public intake, Catch Up, research/history/actions, restart/recovery and
graceful model-offline behavior. Measure hosted latency and capture screenshots.
Then polish README/demo video/DEV article/submission checklist and release tag.
No new product features. Challenge deadline discrepancy remains in ROADMAP.

Local repeat verification:
- npm run build (packages the Python app; requires configured Python toolchain).
- .venv/Scripts/python.exe scripts/run_ui.py --env-file .env --port 8503
- .venv/Scripts/python.exe scripts/smoke_postgres.py --env-file .env --verify-only
The smoke source is synthetic and intentionally retained; no model calls are made.
The full suite has now been rerun after the Neon work (user-reported): 455 collected,
452 passed, 3 skipped, 0 failed in 278.99s (4m38s). All PDF extraction tests passed
in this clean full run; earlier PDF timeout failures were transient/environmental.
The 3 skipped live Temporal integration tests still need a run with the local
Temporal test environment active. Hosted research recovery and public Render
checks remain unverified. No commit or push performed.
