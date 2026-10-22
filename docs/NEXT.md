# Next task: Hosted verification and challenge submission

Task 5A prepared deployment artifacts but **did not deploy**. Do not start automatically.
**Recommended: Claude Sonnet 5 / Codex GPT-6.1 Sol Medium.** Escalate networking/Temporal Cloud issues to Opus 5.

Owner decisions/actions needed first: create the Neon (or other pgvector) database; create the Render Blueprint from
`render.yaml` (requires pushing a branch — ask before pushing); supply secrets; decide supervised vs rented inference;
optionally provide a SerpApi key.

Then: migrate and load demo data per [DEPLOYMENT](DEPLOYMENT.md); if using Temporal Cloud add API-key/TLS connection
support to the worker/probe; verify the public URL (intake, Catch Up, research, history, actions, restart/recovery,
graceful model-offline behavior); measure hosted latency; capture screenshots; then final README polish, demo video,
DEV article, submission checklist and a release tag. No new product features.
