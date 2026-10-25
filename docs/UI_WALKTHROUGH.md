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
  failed analysis can be queued for an explicit retry. No background source runner is implied.
- Existing collections can be assigned during intake and selected as research scope. Collection
  creation/management UI is not added. The optional sample button uses a stable owner/request key
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
