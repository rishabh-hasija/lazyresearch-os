# Current Research UX follow-up — 2026-10-26

Selecting a topic automatically renders its current COMPLETED/PARTIAL brief under Current
research. There is no View result button for this brief. Partial results say:
"This result is based on limited evidence. Review the coverage limitations below."

Answer, Summary, Findings, Recommendations, exact evidence panels, stored limitations and
What changed are preserved. Previous research stays collapsed by default; older completed
missions can be opened with Open brief or selected in the existing version picker. Failed
missions show their actual failure state and never acquire a fake brief.

Verified with 8 focused PostgreSQL/Streamlit tests; Ruff, formatting and mypy passed.
This follow-up changes UI only. Earlier direct-button instructions below are historical.

---

# Research result access update — 2026-10-26

Choose an existing Research topic. Current research shows its stored Current Brief mission,
with a View result button for a published COMPLETED or PARTIAL result. Clicking opens the
answer, summary, findings, recommendations, exact evidence/citations, coverage limitations and
stored What changed. Empty required sections explicitly say nothing was published.

Partial coverage is an available brief with limitations, not a failure. The Office software brief
uses one saved meeting note and bounded collection context without a full-question lexical match.
Both stored limitations are shown with explanations. Its recommendations section truthfully
reports no published recommendations. Exact evidence opens through each claim's evidence panel.

Previous research is collapsed by default and contains older terminal attempts, including both
preserved Office software failures, and the existing immutable version picker. Failed reruns do
not replace Current Brief. Queued/running requests stay visible under Research in progress.
Refresh reads existing progress/results; do not submit another mission merely to open a brief.

Verified against the saved Neon Office software mission using read-only Streamlit AppTest:
one immutable partial result v1, only the meeting note cited, two preserved failures in history,
and unchanged source/extraction/analysis/mission/result snapshots. Chrome also verified View result,
the exact citation and both old failures in collapsed-by-default history. Proof screenshot:
.local-tools/research-result-open.png. Local preview was restarted;
hosted Render was not redeployed.

---

# What Matters scope update — 2026-10-26

The top Collection picker offers All sources plus this workspace's collections. Membership is
filtered in PostgreSQL before the candidate limit; counts and grouped items use only that scope.
Feedback still refers to the original saved source. Ranking/TabPFN rules and owner-wide history
are unchanged. The last collection survives page navigation within the session, and creating or
using a collection on Add Sources carries that choice to What Matters. Other sessions start at
All sources; no database/global preference is saved.

Interests uses the new plain-language question/example/help; matching remains case-insensitive
exact topic matching, with comma-separated interests parsed internally. Scope/interests changes
refresh the ranking cache. Use Refresh for external changes. Existing unreviewed/50-candidate
limits remain. The local Neon-backed owner preview verified Office software has one Action
required item (meeting notes), with no battery items; all four counts reflect that filter.
Focused ranking/PostgreSQL/UI tests: 57 passed; Ruff/format/mypy passed. Not redeployed to Render.

---

# UX/onboarding update — 2026-10-25

Recommended Codex GPT-6.1 Sol / Medium; Claude Code Sonnet 5. Exact active model variant unavailable.
These changes are local and uncommitted; the public deployment still runs the earlier commit.

Navigation uses four native full-width Streamlit buttons in the keyed sidebar container
`workspace-navigation`: Add Sources, What Matters, Research, Actions. A callback updates
`workspace-section`; only the selected button is primary. Scoped CSS sets the entire selected
row to exactly #00E300 with #101810 text, a large target, hover border and visible keyboard
focus outline. There are no radio circles. Navigation and page rendering share a named
`workspace-content` fragment; the single app name/tagline and demo warning sit outside it.
Native fragment navigation preserves the header rather than rerendering it on every switch.

A retained workspace missing the current collection API is recomposed without clearing form
drafts. The owner failure on 2026-10-25 confirmed that a long-running process can also retain
old Python imports: that requires a process restart, followed by restoring any unsaved draft.
Collection failure logs retain exception classes, SQLSTATE and stack locations, never payloads
or credentials. Real Neon creation, immediate selection and assignment were verified afterward.

Workspace/bootstrap, SQLAlchemy engine/pool and optional ranking model remain session-owned,
constructed once per session. A configuration change requires a clean session/process restart.
Source-processing provider initialization still happens only on explicit analysis; research
providers run in the worker. No cross-session data/resource cache was added. Existing ranking
decisions remain session display state, invalidated on intake/processing and explicitly refreshed.
Mutable sources, tasks, topics, mission progress and results are reread; exact evidence and
current deletion visibility are checked on every read, including when a lazy panel opens.

Collapsed source, citation, contradiction and action-provenance expanders use Streamlit's
tracked `on_change="rerun"` / `.open` API. Their detail reads run only when opened. Evidence
validation now selects exact extraction/title/current visibility directly, avoiding full source
and latest-analysis loading for each citation. Ownership, quote matching and unavailable/deleted
source behavior are retained. No schema, domain policy or partner architecture changed.

Contextual delayed Streamlit spinners cover saved sources, ranking, research/history, actions,
service checks and research submission. There are no artificial sleeps. Research explicitly
continues through the separate worker after leaving the page. System status checks remain
explicit; opening Research no longer performs a Temporal network probe.

Public-demo UI and README explain that this is a shared synthetic workspace with no auth;
anyone with the URL can read/change it. Saved/uploaded data persists in Neon/PostgreSQL, not
browser storage. Never upload personal/private information. Email/Gmail is not implemented;
paste synthetic email text or upload supported exports. Future Gmail should be selective.
Inputs include examples; the README explains the complete flow both simply and technically.
Baseline says Learning your preferences; only actual PERSONAL mode says Personalized for you.
Repeated action title/description text is hidden for display only; stored proposals/tasks/evidence
are unchanged. No Update available feature was implemented.

## Navigation measurements

Read-only `scripts/measure_ui_navigation.py --env-file .env --rounds 2` measured AppTest rendering
against the configured seven-source synthetic Neon workspace. Same laptop, session workspace,
existing saved analyses, one published brief, seven source actions; closed detail panels.
Cycle: Add Sources → What Matters → Research → Actions → Add Sources, repeated twice.
What Matters uses an explicitly empty repeat-visit decision snapshot to avoid writing ranking
observations during measurement; these numbers do not measure first ranking or populated ranking.
SQL counts include projection reads and pool checks; bootstrap/import/initial load are excluded.

| Destination | Before seconds (two samples) | After seconds (two samples) | SQL before → after |
|---|---|---|---|
| What Matters | 0.054 / 0.052 | 0.133 / 0.091 | 0 → 0 |
| Research | 2.573 / 2.557 | 0.433 / 0.409 | 117 → 9 |
| Actions | 4.498 / 4.208 | 1.744 / 1.566 | 214 → 57 |
| Add Sources | 2.391 / 2.315 | 1.399 / 1.221 | 142 → 72 |

These are server-side samples, not browser paint, percentiles, concurrent load, hosted Render
measurements or cold-start benchmarks. Add Sources and Actions still take over a second in
this environment; effectively immediate navigation is not achieved for every page. Remaining
per-item projections and shared remote-database latency are visible limits, especially at scale.
No stale mutable data cache was introduced to conceal that work. Refresh/mission progress are
manual; edits and state transitions reread fresh records. The existing source/history caps remain.

## Manual checks for the owner

Switch all four rows; confirm a single stable header and the bright green full selected row.
Use Tab/Enter and verify focus visibility. Open a saved source, brief citation and action
provenance, then verify the quote against the saved text. Refresh research after the worker
finishes, select an older version and check Current Brief. Review baseline wording, all input
examples, action edits/status controls and the Neon persistence warning. Use synthetic data.

---

# Task 4B application and verification

Implemented 2026-10-22, Europe/Berlin, on clean checkpoint `9b4a68d`.
Recommended GPT-6.1 Sol / Medium; Claude Sonnet 5 alternative. User confirmed GPT-6.1 selected.

## Structure and boundaries

`ui/app.py` is a single Streamlit entry point with Add Sources, What Matters, Research and Actions
selected by sidebar navigation. `ui/presenters.py` maps inputs, statuses, class names, errors
and evidence labels, escaping untrusted Markdown. No React, FastAPI, ORM, partner SDK, retrieval,
synthesis, ranking or action transition implementation lives in UI. Bootstrap alone composes
providers from existing Settings. No model download/switch or startup migration is implicit.

`application/workspace.py` is the application façade. WorkspaceReads/MissionCommands are narrow
ports for actual delivery needs. PostgreSQLWorkspaceReads supplies bounded owner-scoped source,
topic, mission, result and proposal projections. Existing intake, analysis, ranking, indexing,
mission creation/publication/cancellation fence and domain action policies are reused.
The read projection validates saved evidence against the exact referenced extraction, not
the newest parser text. Currently deleted/deletion-pending evidence denies result/proposal
reads. This is not a completed privacy-erasure implementation or authentication boundary.

Migration **0006** adds action_item only. It references its immutable source-analysis or research
proposal, keeps mutable user text/deadline/status separate, enforces one task per owner/proposal,
and guards origin identity, revision increments and transitions. PostgreSQLActionRepository
implements the existing ActionRepository optimistic-revision contract. Proposals are shown
without writes; task state is initialized idempotently on explicit user changes. Accept,
complete, dismiss, reopen and edits use domain methods. No external execution adapter exists.

## Product behavior

- Add Sources accepts one URL per line, pasted text/title and multiple TXT/Markdown/PDF files,
  using configured backend limits. Originals and successful siblings survive extraction/model
  failures. Receipts distinguish failed, saved, duplicate and unavailable/failed extraction.
  Saved-source details show current processing state, exact original extraction excerpt, model
  summary/topics/proposals and safe source URL. Analyze next source is explicit synchronous work;
  failed analysis can be queued for an explicit retry. Analyze next source prioritizes first-time
  analysis over configuration refreshes, reports the actual source name only after persistence and
  fresh projection validation, and shows how many distinct sources remain queued for the current
  settings. Failures never show completion. No background source runner is implied.
- Collections can be created inline on Add Sources using + Create collection and a name only.
  No collection remains the default; a new collection is selected for the pending submission.
  Blank names are rejected; trimmed, case-insensitive duplicates reuse an existing owner-scoped
  collection. Source drafts survive the inline form. Collection editing/deletion remains absent.
  Existing collections can be assigned during intake and selected as research scope.
  The optional sample button uses a stable owner/request key
  and two clearly synthetic battery texts. Repeating it does not multiply captures or invent
  analyses/results/feedback. Session state contains display/cache data; PostgreSQL remains canonical.
- What Matters uses the four backend classes with human labels and explicit BASELINE versus PERSONAL
  language. Ranking is refreshed deliberately and cached per browser session across forms. Explicit
  feedback persists through the existing event system; stale corrections fail. A reviewed-item
  re-read obtains the backend's override class and deadline safeguard. IGNORE never archives.
- Research creates/selects topics, freezes public permission and optional collections, explicitly
  indexes current sources, and queues durable missions for the existing separate worker. Service health is checked explicitly through System status; navigation does not probe Temporal.
  Refresh reads actual stages. Cancellation first persists the existing terminal fence; an in-flight
  bounded provider call may continue, but cannot publish after cancellation.
- Briefs show actual structured sections, partial-coverage notices, exact saved quotes, titles,
  personal/public origin, PDF page and safe original URL. UUIDs are replaced only for display with
  evidence labels; stored provenance is unchanged. Each cited statement has an evidence expander.
  Mechanical citation validity is explicitly separate from unreviewed factual support.
- Current Brief is selected by the stored pointer, not the highest publication number. Previous
  versions remain selectable with run/publication context. What Changed renders the stored baseline
  comparison; it does not infer changes in UI. Source changes, findings, recommendations, actions
  and model-only categories are displayed when present.
- Empty sources/topics/actions, pending processing, queued research, missing search key, unavailable
  model/server/database and extraction failure have explanatory states. Exceptions never appear as
  raw traces or arbitrary provider messages. The demo has a fixed configurable owner; no production
  multi-user security or private-data permission policy is claimed.

## Automated verification

See STATUS.md for the final full-suite counts. Tests include presenter mappings, mixed input bytes,
safe links/Markdown, sanitized errors, real PostgreSQL intake/feedback/task persistence, stale and
concurrent task edits, immutable proposal preservation, wrong-owner reads/writes, SQL guards,
0006 downgrade/re-upgrade/drift, real Streamlit AppTest forms/upload/feedback/action interactions,
two result versions/citations/research proposals and partial coverage after unavailable search.
An AST check rejects ORM/partner SDK imports from UI. AppTest uses deterministic fake model/search
providers with real PostgreSQL; it is not a live Gemma quality benchmark.

## Local browser verification

Used the actual localhost Streamlit application, real PostgreSQL and configured local Gemma.
The following were visibly checked:

1. Empty-state launch before adding any source in the UI owner.
2. Pasted synthetic battery quote alongside an intentional `file:///` URL failure; the text saved.
3. Real public `https://example.com` intake, independently of the invalid sibling test.
4. Multi-file chooser upload of a synthetic TXT and a valid two-page text PDF; both saved/extracted.
5. Source status and original text, plus real Gemma summary/topics and a source-backed action with
   normalized 2026-11-07 deadline.
6. What Matters baseline label, groups, pending-analysis reasons and prominent deadline warning.
7. Explicit feedback submission; the final build displayed a success notice and moved the TXT
   item to Useful later with Your explicit choice. Canonical feedback survives a refreshed session.
8. Topic creation and a personal-only mission, with public search visibly unchecked and missing-key
   notice. The real worker completed and published a cited brief.
9. Readable answer/summary/findings and exact quotes in the answer evidence expander.
10. Actions provenance plus accept/complete state changes; original proposal/deadline/quote retained.

11. A second real personal-only mission completed and published v2. The final browser showed
    Current Brief v2, its frozen v1 comparison and the model-only-change notice. Selecting Previous
    version v1 displayed its original publication/run and first-brief baseline notice; v2 remained
    the Current Brief. A stale topic-object bug found during this check was fixed by selecting stable
    IDs and re-reading fresh records. AppTest now publishes v2 while the page is open and verifies
    both the current selection and historical v1 selection.

Keyboard-labeled inputs, native form controls, focus navigation and narrow sidebar operation were
used; no formal screen-reader or exhaustive WCAG audit is claimed. A narrow viewport requires
closing the sidebar overlay before interacting with the main page.

The first UI process retained old backend imports during development hot reload, so it was
restarted after backend changes. The final build must be restarted after backend code/config
changes; browser refresh alone is insufficient for an already-cached service object. Canonical
sources, feedback, results and action state remain in PostgreSQL.

Optional screenshot exports timed out in the computer-use tool; no screenshot artifact is claimed.
This did not prevent accessibility-tree/browser interaction verification.

## Services and limits

Tested Streamlit **1.66.1**. PostgreSQL is required for all persistence. Ollama/Gemma is needed only
when explicitly processing/researching; embeddings remain optional and lexical retrieval stays
default. Research requires the separate Temporal server and existing research_worker.py. SerpApi
is optional at runtime, remains visibly unavailable without its key, and has not received a new
live smoke in this task. TabPFN is optional via TABPFN_MODEL_PATH; the real-browser cold start used
baseline. No actual personal-history quality/evaluation claim is made.

The existing Temporal CLI could not open a SQLite state file in the project directory on this
Windows host. The original passed SQLite quick_check and was left intact; its bytes were copied
to `%LOCALAPPDATA%/LazyResearchOS/temporal-task4b-20261022.db`, where the same CLI started successfully
on 127.0.0.1:7233. The precise Windows/path cause was not established. This location is a local
runtime detail, not an application path requirement. See README for startup instructions.

Read lists currently cap sources/proposals at 200, topics at 100, missions/results at 50; there is
no pagination/search for large workspaces. Source excerpts cap at 12,000 characters; evidence
quotes retain exact stored spans. Refresh is manual, source analysis is one-at-a-time, and no
private-data hosting/auth/erasure, connectors, exports, schedules or external action execution
was added. Existing model, lexical recall, conflict/diff and evidence-coverage limits remain.

Community research found one relevant caution about ephemeral Streamlit session state in
[We replaced Streamlit session state with Hindsight vector memory](https://dev.to/rithvik44/i-replaced-streamlit-session-state-with-hindsight-vector-memory-g9b).
Its comments were empty; no consensus is claimed and its extra memory service was not adopted.
This app keeps canonical state in the already-selected PostgreSQL backend.

## Feedback confirmation follow-up (2026-10-26)

In What Matters, select Office software and use the meeting note's feedback form. After Save feedback,
the committed-write confirmation appears inside that form, above the button: Saved. LazyResearch
will use this choice to learn your preferences. A failed write shows a sanitized error in the same
place; a committed write followed by a refresh failure retains success with a separate refresh warning.
The live Neon check preserved the two existing ACT events and appended one ACT correction. Focused
real PostgreSQL/UI regressions cover success location, reruns/corrections, COMMIT rollback and
post-commit read failure; final focused suite 52 passed. No hosted deployment was performed.

## Shared collection and page navigation follow-up (2026-10-26)

Workspace navigation scrolls the main viewport to top immediately on a different page click. It does
not reset on current-page clicks or evidence/filter/feedback/refresh interactions. This is a static
JavaScript handler using Streamlit 1.66.1 DOM hooks; no timer is used.

What Matters and Actions use the shared session collection (All sources remains available). Research
preselects that collection in its editable scope and retains explicit topic choices per scope. A new
context starts without a topic: use + New research topic, edit its collection-based suggested name,
then Create topic. Collections and research topics remain separate objects. Previous research is
collapsed/lazy until opened, or a followed mission completes and Refresh exposes its new brief.

Actions uses each action's immutable cited-source memberships. All cited sources must belong to the
selected collection; mixed/unassigned evidence stays under All sources. The real Office software
check returned Confirm Tool B SSO support and Confirm Tool C data export capability; All sources
returned 16 actions. Test review/edit transitions preserve evidence and optimistic revisions.

Live preview: http://127.0.0.1:8505. The new Office software topic and personal-only scoped mission
df99600f-8f4c-4d60-9c40-c0c9a58a71cf persisted in Neon; last verified QUEUED. Worker completion and
hosted deployment were not verified. Focused tests: 42 passed; final filtered-edit test passed again;
Ruff/format/mypy passed. See STATUS for exact commands, limitations and evidence.

## Office software mission completion follow-up (2026-10-26)

The two prior failed missions remain in history. Full-question lexical matching found no evidence,
and freeze rejected NO_EVIDENCE. Selected-collection missions now use bounded collection context
when question search is empty, with a disclosed PARTIAL limitation; no collection means no such
fallback, and truly empty evidence still fails.

One new mission 49cceeee-0ba2-4cf9-aa09-c5777703d412, with the exact owner question and Office
software scope/public=false, completed through Temporal Cloud and real Gemma in 30.29 s of synthesis.
It published immutable brief 20addecb-a05a-5d55-b67f-10a9037b163d v1, PARTIAL, with one citation to
Meeting notes about new office software. Open Research, explicitly select the Office software topic,
Refresh research, then open Previous research to inspect the brief and evidence. Do not queue another
mission to read it. The worker was restarted with the fix and remains running; the hosted web was
not deployed. See STATUS for the preserved-data audit and exact focused test results.
