# Product design

Task 4B implements a local Streamlit MVP with Add Sources, Catch Up, Research and Actions, explicit
processing, feedback and provenance-preserving action review. UI capabilities and actual browser
verification are recorded in UI_WALKTHROUGH.md and STATUS.md; hosting remains planned.

Task 4A supplies backend Catch Up ranking/feedback with an honest rules baseline and optional
evaluated local TabPFN. No Catch Up UI exists yet. The synthetic benchmark is generic/demo,
not evidence of personal quality; see RANKING_BENCHMARK.md and STATUS.md.

Status: product design with backend intake and source analysis implemented in Tasks 1B/2A; UI and research experiences remain planned. See STATUS.md for verified scope. Design baseline: 2026-10-20, Europe/Berlin.

## Promise and audience

"Give it the things you were too lazy to read, organize, or research. It finds what matters, combines it with fresh research, and tells you what is worth knowing or doing."

Primary users are busy individuals accumulating saved articles, PDFs, notes, and decision research. Their problem is the work after saving: finding relevance, comparing conflicting advice, noticing deadlines, and revisiting stale conclusions. The Week 3 theme, Slow and Steady, means durable background progress with useful partial outcomes, not forced organization or instant-answer theater.

## Three modes

**Catch Up:** answer "What did I save or receive that is actually worth my attention?" Group unreviewed items as Read now (READ), Useful later (KEEP), Action required (ACT), or Ignore/archive suggestion (IGNORE). Repetitive and Low relevance are explanatory badges, not additional target classes. Show why each suggestion appeared and allow corrections. IGNORE never automatically deletes or archives a source.

**Research Mission:** accept a question, optional topic/collection scope, personal-only or public-search permission, and a bounded research budget. Search personal content, find information gaps, obtain current public evidence when permitted, and produce an answer with findings, comparisons where relevant, changed conclusions, personal/public evidence, contradictions, missing information, open questions, recommended actions, and citations. A lack of evidence should remain visible.

**Act:** show proposed tasks, deadlines, replies, renewals, forms, applications, events, decisions, purchases, and follow-ups. Every proposal links to source snapshots and, where applicable, its research result. Users accept, edit, complete, or dismiss; the MVP never sends a reply, purchases, submits a form, or modifies a mailbox.

## Ingestion UX and multiple sources

One inbox entry point offers batch URLs (one per line), multiple PDF/TXT/Markdown uploads, or pasted text with an optional title. No collection is required. A mixed intake session may submit these inputs sequentially into the same optional batch label. Each entry gets its own receipt and progress: queued, fetching, saved, processing, ready, or failed. These are display states derived from intake and processing records, not one overloaded content status.

Show invalid URLs and rejected files individually; keep valid siblings. Distinguish "saved, analysis pending" from "not saved". Retry only failed entries. A duplicate receipt points to the already-saved item and preserves the new capture occurrence. A changed page is a new snapshot, never a silent replacement. Proposed initial limits: 20 entries per batch, 10 MiB per file, 200 PDF pages; these are budgets to validate before ingestion implementation, not supported capabilities.

Optional collections such as Home Energy, AI Business, Travel Planning, and Personal Finance are many-to-many groupings. Topic suggestions never move or hide material automatically. A research topic represents a continuing question; it is distinct from a collection and can draw from several collections.

Later connectors: Gmail only through selected labels, senders, newsletters, or explicit search queries, with preview/count and revocation. Full-mailbox access is a separate explicit opt-in, never a default. RSS/newsletters and image/screenshot ingestion are stretch. Scanned PDFs without extractable text should report OCR required; OCR is not promised for MVP.

## Output and repeated research

Primary output is an in-app readable brief, backed by database records. The UI will expose Current Brief, Previous Versions, and What Changed Since Last Run. A repeat creates a new mission and immutable result; previous evidence is useful context, not automatically current truth. Show added/removed evidence, changed claims, changed recommendations, and unchanged conclusions, distinguishing source updates from model-only changes.

For Home Battery Systems, v1 can compare saved installation quotes; v2 adds current public pricing and highlights differences while retaining v1. A failed rerun leaves Current Brief unchanged. Partial results carry a coverage warning. Simultaneous runs use explicit version ordering described in DATA_MODEL.md.

Markdown and JSON exports are planned derived views of a chosen result ID, including version, timestamps, limitations, and citations. JSON has a schema version; Markdown resolves citation labels from stored evidence. Downloading does not save the canonical result. PDF export is stretch; none are implemented now.

## MVP, stretch, and non-goals

Demo-critical MVP: batch URLs, PDFs with text, TXT/Markdown, pasted text, persistent originals, configurable Gemma processing, source-based actions, honest Catch Up ranking with a measurable TabPFN role, personal retrieval, SerpApi research, Temporal mission recovery, immutable briefs with citations and change comparison, and a Render-hosted demo. Basic action status updates and feedback are included. Export architecture is required now; Markdown/JSON implementation follows the core demo if time permits.

Stretch: Tinker classifier experiment, scoped Gmail, RSS/newsletters, scheduled Catch Up/digests/refresh, images, PDF export, advanced collection management. Non-goals: autonomous external actions, full-mailbox default ingestion, social knowledge sharing, microservices, a generic agent platform, universal OCR, and guaranteed factual correctness or financial advice.

## Success metrics (targets, not measurements)

Use a consented or synthetic 20-item fixture and at least two research runs. Target: 100% saved originals survive AI failure; 100% displayed citations resolve to the correct snapshot; 100% action proposals have provenance; zero cross-owner retrieval; no duplicate final result on retry. Human review should find at least 90% of sampled factual claims supported, reported separately from citation-link validity. Compare top-5 Catch Up usefulness and macro-F1 against a simple baseline; report sample counts and class balance, not personalization claims. Record median/p95 save latency separately from AI completion, mission duration, model configuration, and estimated reading time saved versus actual review time. Set latency budgets after hardware measurements.

## Journeys and user control

1. A user drops ten URLs and two PDFs without folders. All twelve originals save; the encrypted PDF reports extraction failure. A model outage preserves the originals with pending analysis and retry opportunities.
2. A user researches a home battery using Home Energy and public search. The brief separates personal quotes from current web claims and flags incompatible currencies/dates rather than fabricating a comparison.
3. A renewal notice produces an action with a quoted deadline. An ambiguous timezone asks for clarification; accepting the proposal does not purchase anything.
4. A week later, a rerun preserves v1 and presents v2's evidence changes. Deleting a sensitive source later removes access to its text and marks affected citations unavailable.

Users choose public-search and remote-processing permissions separately, correct ranking, inspect evidence, cancel processing, export, and delete. Content and retrieved pages are untrusted data, never instructions to the system. Private titles/quotes must not leak into public queries or logs.

## Open questions and approval gates

| Decision | Proposed direction | Must resolve by |
|---|---|---|
| Backend/UI stack | Approved for Task 1A: Python 3.12, pytest/Ruff/mypy; Pydantic v2 where useful; future SQLAlchemy 2.x/Alembic/psycopg 3 and Streamlit | Resolved; future adapters/UI not implemented |
| Demo audience and authentication | Approved: eventual public Render demo uses synthetic/demo content; no auth or private data in Task 1A | Private-data expansion requires its own access policy |
| Inference hardware and hosting | Benchmark Gemma 4 E4B locally; choose permitted reachable worker deployment | Before real AI adapter/demo commitments |
| Retention and deletion policy | Explicit deletion cascades to derived private data; document backup expiry | Before storing real personal content |
| Search cost and intake caps | Bounded defaults; user-visible budget and cancellation | Before ingestion/research integrations |
| Public search defaults | Explicit per-mission permission, sanitized queries | Before SerpApi use |

The user approved the architecture and authorized Task 1A on 2026-10-21. Its pure domain foundation is implemented; see STATUS.md. Further slices require their own task instruction. Remaining gates above apply before their affected integrations.
