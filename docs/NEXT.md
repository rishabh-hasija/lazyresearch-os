# Next task: 4A — Catch Up ranking with TabPFN and honest cold start

Tasks 1A, 1B, 2A, 2B and 3A are implemented and validated. Task 3A changes are unstaged and uncommitted on checkpoint **4db9100**. Wait for the user's next task instruction; do not begin 4A automatically.

**Recommended Codex: GPT-6.1 Sol, Medium. Alternative Claude Code: Claude Sonnet 5.** Apply AGENTS.md's model-selection guard; do not guess identity or claim to switch the parent model.

Read AGENTS, README, PRODUCT, ARCHITECTURE, DATA_MODEL, PARTNERS, ROADMAP, STATUS and RESEARCH_MISSION_BENCHMARK, plus ADR 0007 and relevant existing boundaries. Task 4A should introduce honest ranking/cold-start behavior only under the next brief, preserving ingestion, analysis, scoped retrieval and durable missions. Do not fold UI, hosting, authentication, connectors or exports into ranking without authorization.

Preserve immutable originals, analyses, chunks, research evidence/results/actions; owner scope; lexical fallback; explicit public permission; citation validity versus UNREVIEWED support; and request-order Current Brief versus publication-order version. PostgreSQL 17.11 remains canonical. Head migration is **0004**; do not rewrite 0001–0004. All Task 3A validation and known limitations are in STATUS and RESEARCH_MISSION_BENCHMARK.

Local Ollama 0.40.6 has gemma4:e4b and qwen3-embedding:latest. Temporal SDK 1.34.0 is installed; ignored .local-tools holds CLI 1.9.1 and a running localhost-only dev server at 127.0.0.1:7233. scripts/research_worker.py starts the application worker/reconciler explicitly; no production worker service was installed. Real SerpApi smoke was skipped for missing credentials. Do not request or reveal secrets just to run deterministic ranking tests.

Research limitations to preserve honestly: heuristic conflict/change detection, simple query sanitization, AND-token lexical recall, bounded evidence coverage, external calls potentially repeating across crash windows, and the real Gemma smoke missing an explicit action. No factual entailment proof or general action-recall claim. Citation validation passed. No generic agent framework.

Keep prior tests passing, add meaningful ranking tests/evaluation from the forthcoming brief, run PostgreSQL integration/lint/format/types, document exact outcomes, and leave changes unstaged unless instructed otherwise. Do not commit, push or amend by default.
