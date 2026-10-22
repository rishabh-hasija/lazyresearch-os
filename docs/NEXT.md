# Next task: 5A — Deploy and verify a reproducible synthetic demo

Tasks 1A/1B/2A/2B/3A/4A/4B are implemented. Task 4B remains unstaged on checkpoint
**9b4a68d**; see STATUS and UI_WALKTHROUGH for actual checks and limits. Wait for a new user
instruction; do not begin deployment automatically or commit/push these changes.

**Recommended Codex: GPT-6.1 Sol / Medium. Claude Code: Claude Sonnet 5.** Apply the AGENTS
model guard. Escalate measured cross-layer failures to GPT-6.1 Sol High or GPT-6 Astra Medium /
Claude Opus 5 when justified; these are project recommendations, not tool-availability claims.

Read AGENTS, README, PRODUCT, ARCHITECTURE, DATA_MODEL, PARTNERS, ROADMAP, STATUS,
UI_WALKTHROUGH and the Gemma/retrieval/research/ranking benchmarks plus relevant ADRs.
Bound the task to a reproducible synthetic Render demo and its verification. First verify the
hosting budget, independent PostgreSQL DATABASE_URL, Temporal/worker connectivity, reachable
inference path, secret provisioning and access/retention policy. Prepare concrete configuration
and reviewable deployment changes before any final approval required for external publication.
Do not use real personal inputs or claim production authentication/security from a fixed owner.

Preserve the four-section Streamlit application and existing application ports. Explicitly
migrate to **0006**, keep earlier revisions intact, and never require Render Postgres. Demonstrate
URL/text/TXT/Markdown/text-PDF intake, real Gemma, transparent baseline and the actual optional
TabPFN role, SerpApi only with authorized credentials, durable mission execution/cancellation,
exact citations, Current Brief/history/What Changed, and human action-state edits. Do not relabel
mock checks as live integrations or seed synthetic labels as personal history.

Verify fresh installation/upgrade, independent web/worker restarts, old-result persistence,
workflow recovery, backup/restore, sanitized errors/logs, owner isolation and a small claim-support
sample. Measure actual hosted limits. Local Task 4B passed 451 tests, including PostgreSQL and
three live Temporal cases; the browser completed two real Gemma missions. Real SerpApi access,
hosted runtime, real-user ranking quality and production privacy/security remain unverified.
The Windows Temporal state-path workaround in README is local only, not deployment configuration.

Retain existing bounded recall/evidence, heuristic conflicts/diffs, model action-recall and
repeated-call crash-window limitations. No Gmail/RSS/Tinker, schedules, OCR, external action
execution, broad ranking redesign or speculative transport layer. Defer exports unless separately
authorized and core hosted acceptance is complete. Run relevant full tests, PostgreSQL/Temporal,
migration drift, Ruff/format/mypy, dependency and git checks. Update README/STATUS/NEXT with exact
outcomes and unresolved issues; do not commit/push/amend unless explicitly instructed.
