# Research Mission implementation and measurements

Task 3A, measured 2026-10-21, synthetic content only. Baseline commit **4db9100**. This is a backend/library slice, not a product UI or deployment.

## Implemented flow

Explicit topics never auto-merge. Mission creation locks its topic, increments request-order run_sequence, freezes question, baseline, permissions, collection scope and budgets, and persists a dispatch intent in the same row/transaction. Inputs reject database updates. Status and stage are separate. Start, terminal cancellation/failure and publication enforce the domain lifecycle.

Personal evidence uses Task 2B's owner/collection/visibility/current-extraction retrieval. Lexical is default; vector/hybrid are explicit and preserve fallback status. Primary immutable chunks are used directly. Public sources use the existing secure fetcher, original-byte persistence, extraction, deduplication and chunk indexing. Mission synthesis does not require an extra source-analysis call: primary chunks are already available. Prior summaries are context only.

Gap detection is deterministic: fewer than two personal sources, explicit freshness/pricing requests, stale timestamps, or insufficient comparison coverage. Initial query generation emits **one** focused sanitized question when justified, within the **maximum three** query budget. No personal evidence, titles or quotes feed query generation. Email addresses, URLs, UUIDs, recognized internal identifiers and double-quoted spans are removed. This is conservative pattern filtering, not a universal private-information classifier; questions themselves can disclose interests.

SerpApi is behind SearchProvider. It receives bounded queries, uses HTTPS without redirects, bounds time/body/results, and emits sanitized failures. Snippets remain discovery metadata and never become evidence. Missing credentials/transient exhaustion/inaccessible pages become explicit limitations. No key was requested because deterministic implementation does not depend on one.

Defaults: three queries maximum, ten fetched sources maximum, five concurrent source tasks, 900-second mission deadline, eight evidence chunks / 6,000 evidence characters, 2,400 synthesis output tokens. One public query is currently generated; retries can repeat a provider call. Fetch retries distinguish timeout/connection/429/5xx from permanent rejection. Source failures do not restart completed siblings.

## Persistence and provenance

Migration **0004** adds research_topic, research_mission, research_stage, research_evidence, research_result and research_proposal. Original migrations 0001–0003 are unchanged. Topic/current and mission/baseline links enforce owner/topic scope. Evidence links enforce owner/source/extraction/chunk scope; exact range/page/quote/hash are checked against immutable chunks. Evidence insertion ends when the mission freezes. Successful stage records, evidence, results and research proposals reject ordinary updates/deletes.

JSONB holds bounded versioned sections and operational stage payloads. Relational identities, owner boundaries, source references and publication uniqueness remain columns/foreign keys. Research proposals use the existing domain ActionProposal/ActionOrigin/Deadline values, in a result-specific persistence table; existing source-analysis proposals are unchanged. Candidate ordinal plus deterministic result/proposal IDs prevents retry duplication. Ambiguous deadlines remain raw/unresolved; competing ISO dates also prevent normalization. No mutable ActionItem UI or external action execution was added.

Publication locks the topic before the mission, revalidates exact evidence and structured citations, allocates publication-order version, writes result/proposals and completes the mission atomically. A unique mission result makes retry return the existing publication. Current Brief follows highest successful request-order run_sequence, independently of publication version. Failed/cancelled/no-evidence runs allocate no result version. Terminal cancellation fences late synthesis and publication writes.

## Synthesis, conflicts and change comparison

ResearchSynthesizer is separate from source-analysis AIProcessor. Schema **research-v1** requires cited answer, summary and findings; optional comparisons, recommendations, claims and action candidates also cite known evidence UUIDs. Missing information/open questions/limitations remain explicit. Unknown structured or inline citation IDs fail; URLs/numeric bracket citations cannot serve as authoritative claim links. At most one schema/citation repair is allowed. Unsupported results fail rather than silently dropping claims. No tools are given to source text.

Gemma runs through Ollama; the prompt and hash are recorded. Runtime/model revision are observed, not a guarantee that mutable tags remain immutable. Explicit configuration/OOM error responses are permanent; transient availability/timeouts receive bounded retries. Citation validity is not factual support: all claims remain **UNREVIEWED**.

Conflict detection preserves unresolved, high-uncertainty possible price/date/quantity/version/recommendation conflicts and changed snapshots of one URL. Shared-word matching is heuristic and can both miss conflicts and flag different applicable scopes. Conflicts are supplied to synthesis and retained independently in the result, so model omission does not erase them.

What Changed compares against the frozen baseline: source sets per URL, changed snapshots, evidence IDs/hashes, added/removed claims, changed recommendations/actions and model-only differences. Multiple snapshots of one URL use sets, avoiding row-order-dependent results. Changed-claim pairing is explicitly positional/heuristic. Missing evidence never means a claim became false. Historical snapshots remain separate and can both appear in a new brief.

## Temporal runtime and recovery

Installed Python SDK **1.34.0** (15.4 MB wheel) and local standalone CLI **1.9.1**, bundling Server **1.32.0** and UI **2.54.1** (46.4 MB CLI archive). The CLI and persistent dev-server database live in ignored `.local-tools/`; server binds **127.0.0.1:7233**, headless. No new Docker/database stack or public exposure. The CLI download was announced before execution; no multi-GB download was needed. Dev server is not a production setup.

ResearchMissionV1 workflow replay performs only deterministic orchestration. Activities invoke application operations; history contains owner/mission IDs, source/query indices, bounded counts and result ID, not questions/documents/snippets/model responses/credentials. Completed stage payloads stay in PostgreSQL. Activity attempts are capped at three, with one-to-five-second retry backoff, 270-second start-to-close and 15-second heartbeat timeout. Heartbeats run while bounded synchronous I/O executes off the event loop. The mission timer is separate from stage timeout.

Dispatch reconciliation starts workflows with the stable mission UUID and REJECT_DUPLICATE policy, then records acknowledgment. Repeating an ambiguous start is safe. Missing workflows can be redispatched; closed failed/cancelled/timed-out workflows reconcile terminal DB state. Cancellation fences the DB before requesting Temporal cancellation. Published results are not undone by a late cancellation request.

Live local tests exercised full completion, history replay, duplicate start/dispatch acknowledgment, transient retry across worker shutdown/restart, cancellation during synthesis, no-evidence workflow failure, per-source retry without rerunning its sibling, and lost publication acknowledgment without a duplicate result. Worker restart was graceful runtime replacement, **not a process kill or server-crash experiment**. External calls can repeat if a worker dies after provider success and before recording; exactly-once network/model execution is not claimed. Existing stage receipts and atomic publication prevent duplicate canonical artifacts.

## Synthetic fixture and real smoke

The Home Battery fixture starts with a saved installer quote and electricity-rate note, then fake public pricing/specification pages. Run 1 publishes v1. Run 2 changes a price, adds a source and changes recommendations/actions; it publishes v2 and meaningful changes. Concurrent runs finish in reverse order: publication v1 belongs to run 2, publication v2 belongs to run 1, and Current Brief remains run 2. PostgreSQL concurrency tests also allocate eight simultaneous mission sequences and retry one publication five times without duplicate actions/results.

Real Gemma/Ollama/Temporal/PostgreSQL smoke: **gemma4:e4b / Ollama 0.40.6**, two synthetic evidence records. Latest measured run: **40.8077 seconds** end to end, **37.5769 seconds** synthesis including **one repair**, exact citations valid, workflow completed and result published. It returned **two findings**, **zero entries in the optional claims array**, and **zero action candidates**. Answer, summary and recommendation are also cited statements. The model missed the source's explicit assessment task; action-extraction recall is not established. A preceding prompt run took 52.1911 / 48.7706 seconds with no repair and also missed actions. These are tiny smoke observations, not latency/quality guarantees. [Raw latest synthetic output](research_mission_smoke.json).

Real SerpApi smoke: **skipped — SERPAPI_API_KEY absent**. Fake-provider and HTTP contract tests cover permission, sanitization, bounds, duplicate URLs, unavailable search, failed fetch, partial coverage and discovery-only snippets. This is an implemented adapter with no live provider validation in this environment.

## Verification and limits

See [STATUS](STATUS.md) for final test counts and tool results. Upgrade 0003 → 0004 → 0003 → 0004 and schema-drift check passed against the isolated migration database; prior data/migrations remain intact. PostgreSQL remains **17.11**; pgvector is still optional.

No general entailment verification, evaluated semantic contradiction detector, universal PII sanitizer, multilingual evaluation, large-corpus/load benchmark, automatic fuzzy topic merging, or production Temporal service was added. Lexical AND-token matching can miss natural-language questions; configured semantic retrieval can improve recall. Evidence and context budgets can yield partial coverage. A missing source or transient search failure does not make a supported personal brief disappear. Privacy erasure/authentication, TabPFN, UI, hosting and connectors remain outside this task.

Primary implementation references: [Temporal Python SDK](https://github.com/temporalio/sdk-python), [Temporal local server](https://docs.temporal.io/cli/command-reference/server), [SerpApi search API](https://serpapi.com/search-api). Community review emphasized that provider side effects are not exactly-once merely because workflow history is durable: [Temporal finished my workflow exactly once and ran its first step four times](https://dev.to/remdore/temporal-finished-my-workflow-exactly-once-and-ran-its-first-step-four-times-59dh), including the author's clarification in comments about the external-call/DB-record crash window.
