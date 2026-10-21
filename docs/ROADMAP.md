# Five-day implementation roadmap

The user approved the architecture and stack on 2026-10-21. Slices 1A/1B/2A/2B are implemented and verified; 3A is the single next task. Days below are relative workdays, not a deadline promise. Resolve remaining gates at the start of each affected slice; STATUS.md records what actually exists. Further slices require a subsequent task instruction.

## Model policy

Use the user's project names consistently: architecture/ambiguous design = **GPT-6 Astra, Medium**, alternative **Claude Opus 5**; normal feature development = **GPT-6.1 Sol, Medium**, alternative **Claude Sonnet 5**. These are recommendations from the brief, not a verified list of selectable models. Small mechanical documentation/test edits can use a lower-cost suitable available model (for Claude, Haiku where available); do not invent an exact version. For cross-layer failures, use GPT-6.1 Sol High or GPT-6 Astra Medium / Claude Opus 5 only when justified. Every slice follows AGENTS.md's active-model guard.

## Day 1 — Foundations, then durable source capture

### 1A: Domain and port contract foundation (completed)

- Objective: implement only pure identity, snapshot/provenance, lifecycle, and versioning invariants plus minimal application-owned contract types; approve backend stack before creating metadata.
- Expected files/modules: pyproject.toml if Python approved; src/lazyresearch/domain/{content,research,actions}.py; ports/{content,research,actions}.py as needed for exercised contracts; tests/domain/; STATUS.md and NEXT.md.
- Prerequisites: architecture approval, stack/tooling decision, review of the concurrency and deletion policies. No secrets or providers required.
- Acceptance: original snapshots cannot be mutated; illegal state transitions rejected; publication retry/concurrency rules represented without database or SDK dependencies; actions require provenance; scope types explicit. Do not create every proposed interface speculatively.
- Validation: focused domain tests for mutation, invalid transitions, repeated publication decisions, stale-run Current Brief selection, and missing action provenance; import-boundary check; configured lint/type checks.
- Models: GPT-6.1 Sol / Medium; Claude Sonnet 5. The agreed rules make this bounded implementation, not open-ended architecture.

### 1B: Persistent intake and source adapters (completed)

- Objective: save batches of URLs, text PDFs, TXT/Markdown, and pasted text before AI; preserve receipts and duplicate history.
- Expected modules: infrastructure/persistence/, infrastructure/sources/, application/ingestion/, migrations/, tests/integration/; minimal API intake only after contract tests.
- Prerequisites: 1A, PostgreSQL version/tool choice, source size/time limits, real-data retention/auth decisions if private data is used.
- Acceptance: valid siblings survive invalid entries, raw bytes survive parser/model failure, duplicate retries do not multiply snapshots, changed URL produces a new snapshot, pending processing survives restart.
- Validation: real PostgreSQL transaction/uniqueness tests; mixed batch with encrypted PDF, redirect/private-address rejection, duplicate race, source update, worker lease recovery. No need for AI yet.
- Models: GPT-6.1 Sol / Medium; Claude Sonnet 5. Well-defined persistence and adapter work; escalate only a demonstrated concurrency/security defect.

## Day 2 — Processing, retrieval, and action candidates

### 2A: Configurable Gemma processing and evidence extraction (completed)

- Objective: benchmark candidate model and implement validated analysis/actions against saved snapshots.
- Expected modules: infrastructure/ai/, application/processing/, domain/analysis.py, bootstrap/config.py, tests/contracts/ai/, processing fixtures.
- Prerequisites: 1B; hardware/runtime/license check; local/remote permission and latency budget. Select Gemma 4 E4B only if measurements support it.
- Acceptance: invalid structured output is bounded/rejected, model/prompt revisions recorded, reprocessing adds versions, actions retain spans, failures leave originals usable.
- Validation: synthetic known-deadline/contradiction fixtures; malformed output, timeout, cancellation, prompt-injection fixture; real-model smoke with latency/memory recorded separately from deterministic tests.
- Models: GPT-6.1 Sol / Medium; Claude Sonnet 5. Adapter implementation follows known contracts; hardware ambiguity may require a bounded GPT-6 Astra Medium / Claude Opus 5 design review before changes.

### 2B: Lexical and optional vector retrieval (completed)

- Objective: retrieve authorized evidence with stable source locators and a working lexical fallback.
- Expected modules: application/retrieval/, ports/vector_store.py, ports/embedding_provider.py, infrastructure/vector/, chunk/extraction persistence, retrieval fixtures.
- Prerequisites: 1B/2A, embedding model selection, extraction mappings.
- Acceptance: exact versioned citations, cross-owner exclusion, semantic-disabled operation, incompatible embeddings never mixed, deleted sources excluded.
- Validation: recall on labeled questions, wrong-owner and wrong-version fixtures, absent pgvector, chunk boundary checks, model-space migration scenario.
- Models: GPT-6.1 Sol / Medium; Claude Sonnet 5. Standard feature development; avoid approximate-index tuning until measured need.

## Day 3 — Durable Research Missions and immutable results

### 3A: End-to-end mission engine

- Objective: combine personal retrieval, permitted SerpApi search, source processing, contradiction-aware synthesis, actions, immutable publication, and change comparison under Temporal.
- Expected modules: application/research/, infrastructure/search/, infrastructure/workflows/, bootstrap/worker.py, research persistence, tests/workflows/ and publication tests.
- Prerequisites: Day 2; sanitized query policy/budgets, Temporal runtime decision, frozen mission inputs, dispatch reconciliation.
- Acceptance: first and second runs preserve results/evidence; unsupported citations rejected; partial source failures visible; restart resumes without duplicate published results/actions; older concurrent run cannot replace newer Current Brief; private-only mode performs no public search.
- Validation: worker kill after source processing and before publication acknowledgement; retry/cancellation race; two concurrent runs finishing out of order; unavailable search and zero evidence; replay compatibility; wrong source/version citation; claim-support review on a small real mission. Separate deterministic fixtures from live external smoke tests.
- Models: GPT-6 Astra / Medium; Claude Opus 5. This slice combines transaction, workflow, provenance, and concurrency invariants and deserves stronger design/debugging capacity. Keep ordinary adapter subwork at the normal feature tier if isolated in later tasks.

## Day 4 — Catch Up, feedback, and application experience

### 4A: Ranking with honest cold start

- Objective: expose baseline ranking and a real, evaluated TabPFN predictor using versioned features and explicit labels.
- Expected modules: application/relevance/, infrastructure/ranking/, interaction persistence, evaluation fixtures/report.
- Prerequisites: analysis/actions, feature cutoff/label policy, consented or synthetic labeled data, TabPFN package/resource verification.
- Acceptance: baseline visibly labeled; generic seed predictions not called personal; exact four-class output; deadline visibility and user overrides preserved; no future-data leakage.
- Validation: chronological grouped split against baseline; macro-F1, per-class recall, top-k usefulness, latency; absent-class/small-history tests; ITEM_ARCHIVED and MISSION_USED_ITEM not silently assigned positive/negative labels.
- Models: GPT-6.1 Sol / Medium; Claude Sonnet 5. Bounded integration with explicit evaluation; do not spend frontier capacity on routine metrics plumbing.

### 4B: Minimal readable UI/API

- Objective: make batch intake, progress, Catch Up, research briefs/history/diffs, source citations, and action review usable.
- Expected modules: api/, ui/, bootstrap/web.py, UI/API integration tests.
- Prerequisites: stack selection, Day 1-3 contracts, 4A for ranking display; public-demo auth policy.
- Acceptance: originals distinguish saved/processing/failed; partial missions are labeled; citations open exact evidence; Current Brief and historical publication versions are distinct; corrections/status changes work; no external actions execute.
- Validation: browser walkthrough of PRODUCT journeys, keyboard navigation, empty/error/partial states, owner isolation and unauthorized reads, cancellation display; record screenshots only when implementation exists.
- Models: GPT-6.1 Sol / Medium; Claude Sonnet 5. Ordinary UI/API development; scope is intentionally narrow.

## Day 5 — Render demo, recovery verification, and handoff

### 5A: Deploy and verify a reproducible demo

- Objective: host approved demo on Render with independent PostgreSQL and a verified worker/inference path; document factual capabilities.
- Expected files/modules: deployment configuration, operational instructions, demo fixtures, smoke/recovery checks, README/STATUS/NEXT updates. Markdown/JSON export adapters only if core acceptance is already met.
- Prerequisites: core slices pass; hosting/worker/inference budget and connectivity verified; synthetic public demo or tested private-data auth; backup/retention decisions.
- Acceptance: URL/PDF/text ingestion, Gemma, TabPFN, SerpApi mission, provenance/actions, history/diff, Temporal recovery, and public Render experience all demonstrated. No integration labeled complete solely because a mock passes. DB portability configuration contains no Render-only requirement.
- Validation: hosted smoke; restart worker/web separately; verify old results persist; fresh install and upgrade rehearsal; restore exercise; no secrets in logs/repository; demo claim-support sample and measured limits.
- Models: GPT-6.1 Sol / Medium; Claude Sonnet 5. Escalate complex cross-layer failures to GPT-6.1 Sol High or GPT-6 Astra Medium / Claude Opus 5. Small final docs can use a lower-cost suitable available model / Claude Haiku where available.

## Dependency path and schedule cuts

1A -> 1B -> 2A/2B -> 3A -> 4B -> 5A; 4A depends on 2A plus interaction data and joins before 5A. These are sequencing relationships, not authorization to spawn agents or begin later tasks automatically.

Cut stretch in this order: (1) Tinker, (2) Gmail, (3) RSS/newsletters, (4) scheduled Temporal jobs, (5) image/screenshot ingestion, (6) PDF export. Defer polished collections, advanced ranking tuning, and export implementation before compromising core integrity. Keep URL/PDF/pasted-text ingestion, Gemma, Research Missions, citations/provenance, SerpApi, meaningful TabPFN role, Render deployment, and action extraction. Keep durable on-demand missions; scheduled jobs are a different scope.

If core still exceeds five days, reduce demo corpus, UI polish, and concurrency, or report incompleteness honestly; do not relabel mocks as integrations. No deadline justifies dropping isolation or source integrity.

## Challenge scheduling discovery

The DevRelay event data confirms the active [Week 3 challenge](https://dev.to/events/challenges/hacktoberfest-week3-2026-10-19) and user registration. Its structured end time was 2026-10-25 06:59 UTC (07:59 Europe/Berlin), while prose said October 25 at 11:59 PM PDT, which corresponds to October 26 07:59 Europe/Berlin. This conflict must be checked with organizers before relying on the later time; use the earlier bound for planning. The five relative days are not a guarantee of fitting the challenge window. No registration, submission, or publication was performed.
