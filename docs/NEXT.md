# Next: Owner-guided manual product walkthrough and final demo/submission preparation

Recommended Codex GPT-6.1 Sol / Medium; Claude Code Sonnet 5. Apply AGENTS.md's model guard.

The UX/onboarding task is implemented locally on checkpoint 0cd9b7e. No commit, push or
redeployment was performed. Public Render still runs runtime commit 301068f. Review the
new local navigation and warnings before an explicitly authorized deployment task.

Owner walkthrough:
- Verify full-width Add Sources / What Matters / Research / Actions navigation, selected
  #00E300 row, keyboard focus/Enter behavior and stable app name/tagline.
- Confirm examples, explicit source analysis and worker-backed research messaging; inspect
  opened source/evidence/provenance panels and action edits/status transitions.
- Review README's simple flow and partner table. Confirm the public demo's shared synthetic,
  no-authentication, durable Neon storage and no-private-upload warning.
- Review baseline Learning your preferences versus actual evaluated Personalized for you.
- Prepare final demo/submission materials using verified behavior and honest limitations.

See UI_WALKTHROUGH.md for repeatable timing methodology and STATUS.md for exact checks.
Navigation is faster, but Add Sources/Actions still exceed a second in laptop-to-Neon tests.
No stale mutable-data cache was added; remaining per-item projections, remote latency,
manual research refresh, capped lists, Render cold starts and first/populated ranking costs
remain limits. These changes have not been measured on the hosted deployment.

Prior hosted verification remains historical evidence (see DEPLOYMENT.md/STATUS.md): shared
synthetic Render UI + Neon + owner-run Temporal Cloud/Gemma worker; no hosted TabPFN or live
SerpApi verification, no authentication or private-data guarantee. The prior worker was left
running as PID 10660; check actual process state before starting another worker. Its current
liveness was not reverified by this UX task. Local preview runs separately from that worker.

Gmail/email connector, exports, schedules and Update available UX are not implemented.
Do not add these or other product features automatically. Do not commit, push, publish,
submit, or deploy without the corresponding user instruction.

Validation: full suite 490 passed / 3 skipped in 298.30 s; explicit local Temporal 3 passed
in 18.06 s; final focused UI/presenter/deployment suite 29 passed in 162.20 s; final added
terminal-period presenter regression suite 13 passed in 0.36 s. Ruff check/format (153 files),
mypy (73 files), pip check and git diff --check passed. Changed/new credential scan: 11 files,
zero matches. Full suite collected before the two final evidence/README additions; focused
verification includes them. See STATUS for exact scope and limits. Local demo preview:
http://127.0.0.1:8504/ (separate task-owned web process; no research worker was changed).
