# Agent instructions

## Read first

Read docs/PRODUCT.md, docs/ARCHITECTURE.md, docs/DATA_MODEL.md, docs/STATUS.md, docs/NEXT.md, and relevant docs/ADRS files before changes. These documents must support both Codex and Claude Code without conversation history.

Honor the user's environment instruction at `C:\Users\risha.RISHABH\.codex\RTK.md` where available: prefix shell commands with `rtk` (use `rtk proxy` for unsupported commands). On another machine, do not invent that file's contents or require this personal path for application operation.

## Boundaries

- Use a modular monolith. Domain imports no web framework, ORM, partner SDK, network, or filesystem implementation.
- Application owns use cases and ports; adapters implement ports and depend inward. Bootstrap alone chooses implementations. Keep partner SDKs in infrastructure.
- Preserve source provenance. Never overwrite original content with generated output. Keep processing versions and immutable research results.
- Every action must retain source evidence. Do not execute external actions without a separate authorized feature/task.
- Keep PostgreSQL provider neutral, configured by DATABASE_URL. Render hosting must not require Render Postgres.
- Make only changes needed for the authorized task; avoid unrelated refactors, speculative interfaces, microservices, and dependencies.
- Design phase permits documentation and minimal metadata only. Implementation starts only on a subsequent user-authorized task after architecture approval.

## Model-selection guard

Each task must state recommended Codex model, reasoning effort, and Claude Code model. Use the names in docs/ROADMAP.md as project recommendations, not claims of tool availability.

If the active model is reliably known and materially differs, stop before editing, identify active and recommended models, briefly explain suitability and whether continuing is reasonable, and ask: "Would you like me to continue with the current model, or switch to the recommended model?" Wait for the answer. If identity is not reliably available, state that, do not guess, and continue. Never claim to switch the parent model without an actual supported action.

## Handoff and verification

Every implementation task updates docs/STATUS.md and docs/NEXT.md. STATUS records what actually happened; NEXT records what should happen next. Before ending, run relevant tests and available lint/type checks, record exact outcomes and unresolved issues, and update both documents. Mark unavailable checks as not run. Do not claim a check passed without running it. Keep feature claims explicitly planned until verified. Do not commit or push unless explicitly requested.
