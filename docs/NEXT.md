# Next: Owner-guided manual product walkthrough and final demo/submission preparation

Current Research UX follow-up (2026-10-26): the current completed/partial brief now renders
automatically under Current research, without View result. Partial copy directs readers to the
coverage limitations below. Older completed results retain Open brief under collapsed Previous
research; citations, versions and stored Current Brief ordering are preserved. UI-only change.
Focused Research UI tests: 8 passed / 24 deselected; Ruff/format/mypy passed. No backend/domain
changes, live data writes, deployment, commit or push. Continue the walkthrough by selecting the
existing topic and reading its current brief directly. Earlier View result instructions below
describe the prior UX and are superseded by this update.

Research result accessibility follow-up (2026-10-26): Current research now exposes View result
for published COMPLETED/PARTIAL missions. Previous research contains older terminal attempts
and remains collapsed by default; stored Current Brief ordering/versioning is preserved.
Exact saved Office software partial result v1 opened in read-only Neon-backed AppTest, with
only the meeting note cited; two failed attempts and all database snapshots were preserved.
Stored source-count/context-fallback limitations are visible. This brief has no recommendations;
the UI says so explicitly. No new mission was submitted. Local 8505 preview restarted.
Focused UI/application suite: 73 passed; final extended regression subset: 3 passed.
Ruff/format/mypy and diff checks passed. See STATUS for commands/evidence and remaining limits.
Continue the owner walkthrough by opening the existing Office software brief; use Previous
research only to inspect old attempts/versions. No Render deployment, commit or push performed.

Recommended Codex GPT-6.1 Sol / Medium; Claude Code Sonnet 5. Apply AGENTS.md's model guard.

The UX/onboarding task is implemented locally on checkpoint 0cd9b7e. No commit, push or
redeployment was performed. Public Render still runs runtime commit 301068f. Review the
new local navigation and warnings before an explicitly authorized deployment task.

Latest copy-only follow-up: generic default input examples and concise URL/file/pasted-text
batching guidance are implemented; Home Battery samples remain behind Load sample sources.
Relevant presenter/UI tests: 19 passed in 25.16 s; broader checks not rerun by request.

Latest collection follow-up: Add Sources now creates/selects collections inline through the
existing PostgreSQL model, reuses owner-local duplicate names, and preserves source drafts.
Focused UI/application checks: 9 passed / 5 deselected in 23.85 s; final two creation tests
passed in 6.35 s. Focused Ruff/format and mypy passed; broader suites/hosted checks not run.

Collection failure follow-up: actual owner-session logs confirmed stale imported Workspace
classes missing create_collection, rather than a Neon write failure. The local web process
was restarted, draft retained, and Office software creation/selection/assignment verified in
Neon. All 8 source IDs/hashes remain unchanged. Session compatibility guard and safe diagnostics
added. Focused tests: 11 passed / 5 deselected in 27.73 s; Ruff/format/mypy passed. See STATUS.
Restart the web process after application API changes; page reruns cannot reload old imports.

Analysis-state follow-up verified on real Neon/Gemma: a 240→120-second timeout fingerprint
change had queued older-source refreshes ahead of new meeting notes. Claim priority now favors
never-analyzed extractions; structured results identify the exact source/job and queue count.
The target completed in one real Gemma call (37.26 s), is READY, and retained all originals and
prior analyses. Two refreshes remain queued. Final focused tests: 44 passed in 78.21 s;
Ruff/format/mypy passed. See STATUS for exact evidence. No full-suite run or Render deployment.

What Matters scoping follow-up (2026-10-26): Collection selector now filters candidates through
owner-scoped membership SQL before the ranking limit; counts and feedback use that scope.
Selection survives navigation and carries from collection creation/use on Add Sources within
one browser session. Interests wording is user-facing; exact-topic matching is unchanged.
Final focused tests: 57 passed in 71.06 s; Ruff/format/mypy passed. Real Neon/local UI verified
Office software shows only the meeting note (Action required=1), and selection survives navigation.
No global preference, migration or hosted deployment. See STATUS for limits/evidence.

Feedback visibility follow-up (2026-10-26): Neon already contained two committed ACT events for
Meeting notes about new office software. The old page-top success was offscreen at the feedback
form. Confirmation/failure now appears inside that form and success waits for COMMIT. Live save
verified the exact requested text and a third ACT correction preserving prior history. Real database
regressions include deferred COMMIT rejection and post-commit readback failure. Final focused tests:
52 passed in 72.63 s; Ruff/format/mypy passed. No ranking/TabPFN or schema change. See STATUS.

Workspace context follow-up (2026-10-26): navigation resets the main viewport only on a changed
page click. Shared collection context now reaches Research and Actions; Research never selects an
unrelated topic by database row order, offers inline topic creation and keeps history collapsed.
Actions filters by all immutable cited-source memberships and preserves review revisions/provenance.
Focused suite: 42 passed in 79.77 s; final filtered-edit test passed again in 10.16 s; Ruff/format/mypy
passed. Live local preview is 127.0.0.1:8505. Neon Office software shows exactly the two requested
tasks, versus 16 for All sources. Created Office software topic and one scoped personal-only mission
(df99600f-8f4c-4d60-9c40-c0c9a58a71cf), last verified QUEUED. Check its worker availability and refresh
its state during the next walkthrough; do not claim it completed. No hosted deployment performed.

Temporal freeze failure follow-up (2026-10-26): both Office software failures had empty personal
retrieval: full-question all-term lexical matching returned zero, and freeze correctly rejected
NO_EVIDENCE (hidden as INVALID_OPERATION). Explicit collection missions now have a bounded,
truthfully labeled collection-context fallback with a PARTIAL limitation; no evidence/state/publication
invariants were relaxed. Local diagnostics retain safe operation/error codes and IDs without contents.
One clean Cloud mission 49cceeee-0ba2-4cf9-aa09-c5777703d412 finished QUEUED -> RUNNING -> PARTIAL;
real Gemma took 30.29 s. Result 20addecb-a05a-5d55-b67f-10a9037b163d v1 cites only the meeting note.
Publication retry returned the same result; failed history, 8 originals/extractions and 14 analyses
are unchanged. Focused mission/retrieval/real-local-Temporal tests: 63 passed; Research UI subset:
4 passed. Ruff/format/mypy passed. Updated worker child PID 12084 remains running (launcher 20824).
Refresh/read this completed brief during the next walkthrough; do not resubmit it just to refresh.
The older queued verification note above is historical and superseded by this completed check.

Owner walkthrough:
- Verify full-width Add Sources / What Matters / Research / Actions navigation, selected
  #00E300 row, keyboard focus/Enter behavior and stable app name/tagline.
- Create a collection inline, retry its name, and save a source into it.
- Switch What Matters and Actions between All sources and Office software; confirm scoped counts,
  the two software verification tasks, provenance and feedback/action review controls.
- From a scrolled page, select another Workspace page and confirm it starts at top. Same-page
  filters/evidence/feedback/refresh should preserve the viewport apart from normal content reflow.
- Open Research with Office software active; confirm scope, explicit topic selection and collapsed
  Previous research. Open an old topic/history manually, then return to the Office software topic.
- Refresh the newly queued Office software mission with the supervised worker available; inspect
  its actual status/result without submitting a duplicate just to refresh.
- Verify named analysis completion, Ready source card and remaining queue count.
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
