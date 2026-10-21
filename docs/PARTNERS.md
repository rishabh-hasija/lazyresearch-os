# Partner responsibilities and replacement plan

Target responsibilities with PostgreSQL and local Ollama/Gemma source analysis implemented. Other integrations remain planned. Partner use must improve the product and be evaluated; category eligibility is not an architectural reason. Provider behavior, licensing, hardware, quotas, and pricing must be checked again when selecting exact packages. Original design references were consulted on 2026-10-20; Task 2A's measured runtime results are in GEMMA_BENCHMARK.md.

## Gemma via AIProcessor

Responsibility: summaries, structured topics/entities/claims, actions/deadlines, and research synthesis; image understanding later. Value: reduces reading effort while producing evidence-linked outputs. Receives bounded source extracts, question, evidence IDs, and processing instructions. Local inference keeps processing on the selected host, but does not make a Render-hosted database local. Remote inference discloses those inputs and requires a separately permitted provider policy.

Task 2A selects **gemma4:e4b** through Ollama 0.40.6 after an approved 6.58 GB download and actual local testing. [The benchmark](GEMMA_BENCHMARK.md) records initial failures, final 7/7 schema/locator smoke success, latency, uncertain memory accounting and an installed gemma3:4b comparison. AI_PROVIDER/AI_MODEL/AI_ENDPOINT select configuration; only Ollama is currently implemented. The AIProcessor returns validated application-shaped source analysis, with no synthesis capability yet. Runtime-specific compact evidence IDs resolve to exact supplied chunk locators; unknown IDs and invalid citations fail. Only one structural repair is allowed per chunk. If inference fails, originals/prior analyses remain readable and the operation records a safe failure. Future lexical retrieval and prior research briefs will remain independent when implemented. Never substitute fabricated summaries.

## TabPFN via RankingModel

Responsibility: predict READ/KEEP/ACT/IGNORE probabilities from versioned tabular features and labeled context, improving relevance ordering as usable feedback accumulates. Receives features, labels, and model configuration; not whole documents by default. Behavioral counts can still be sensitive. Prefer a feasible local adapter; remote inference requires explicit data-routing review.

[Prior Labs documentation](https://docs.priorlabs.ai/overview) describes tabular prediction through in-context learning and API/scikit-learn-style interfaces. That is not a guarantee of personalization or accuracy on this task. DATA_MODEL.md defines cold start, labels, leakage controls, and evaluation. If removed or ineligible, the transparent baseline still provides Catch Up grouping and deadline visibility. Exact package/model/license selection is deferred.

## SerpApi via SearchProvider

Responsibility: current public search to fill gaps and refresh mission evidence. Value: avoids treating saved personal sources as the current state of the world. Receives sanitized search queries, locale/filter parameters, and API credentials; never full private documents or mailbox identifiers by default. Queries themselves may reveal interests. Explicit permission and query preview are the proposed controls.

The [search API](https://serpapi.com/search-api) supplies search results; source fetching and evidence persistence remain our separate responsibilities. Snippets are discovery hints, not verified page content. Replace with another SearchProvider or disable public research. Personal-only missions can continue with an explicit current-public-information gap. SerpApi remains demo-critical; fallback behavior is resilience, not a claim that integration was completed.

## Temporal via WorkflowEngine

Responsibility: durable, multi-stage Research Missions with per-source activities, retries, cancellation, bounded time, and recovery; schedules later. Value: a worker restart need not discard successful research stages. Receives opaque mission/processing IDs and small orchestration metadata; large content stays in PostgreSQL. Workflow history retention and visibility are privacy considerations even for IDs. Never put raw documents or credentials into history/search attributes.

Use deterministic workflow code and idempotent activities as described in [Temporal documentation](https://docs.temporal.io/workflow-definition). Replace with another durable engine through the application boundary if needed; no promise of a drop-in history migration. If unavailable, saved content and prior results remain accessible, new missions remain queued/blocked and recover through dispatch reconciliation. Do not silently claim durable execution via an in-memory background task. Ordinary reads and action edits do not need Temporal.

## Render for public hosting

Responsibility: host web/UI/API and potentially the same-codebase worker, enabling public demo access. Receives application code/configuration and any request data processed there; logs must exclude source payloads/secrets. A public demo must use isolated synthetic data or approved authentication before private uploads are enabled.

[Render service documentation](https://render.com/docs/service-types) separates web and worker execution roles. Deployment plans, persistent processes, and inference resource costs need validation. Replace with another compatible host/container runtime; local development remains possible if Render is removed. DATABASE_URL points to any supported PostgreSQL provider; Render does not own the persistence contract.

## PostgreSQL and pgvector

Responsibility: PostgreSQL is canonical for sources, generated versions, missions, actions, feedback, and job receipts. Transactions protect result publication and idempotency. It receives private content and behavioral data, so use TLS, scoped access, protected credentials, backup policy, and deletion controls. Local PostgreSQL, Neon, Supabase, Railway, or another compatible provider can supply the database without provider SDKs; compatibility must be tested rather than presumed identical.

pgvector is a derived semantic retrieval adapter. It receives vectors, chunk IDs, and owner-scoped metadata. Embeddings are sensitive derived data. [Its documentation](https://github.com/pgvector/pgvector) distinguishes exact and approximate search and filtering trade-offs. Without pgvector, lexical retrieval remains; without PostgreSQL, writes and missions stop rather than treating exports as a replacement database. Moving away from PostgreSQL is a deliberate storage migration, not a current abstraction goal.

## Tinker: optional experiment only

Responsibility if later authorized: fine-tune a small content-triage classifier and compare it with a zero-shot baseline. Potential value is measurable triage quality/cost improvement. It would receive consented, minimized training examples and labels; no personal content is sent for training by default. Exact model support, licensing, and retention must be researched before an experiment; no operational compatibility is claimed here.

Measure accuracy/macro-F1, class recall, latency, and cost on the same held-out split and hardware/provider basis. Keep experiment outputs isolated from production ranking until evaluated. It is not a dependency, not a roadmap prerequisite, and removing it changes no MVP capability.
