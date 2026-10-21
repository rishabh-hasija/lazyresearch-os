# 0007: TabPFN predicts relevance, not research truth

## Status

Accepted as the requested design baseline on 2026-10-20 and approved by the user on 2026-10-21. Task 1A implements only the pure domain subset and minimal repository contracts; see STATUS.md. Acceptance is not a claim of implemented integrations or persistence.

## Context

The project requires a meaningful ranking role but initially has little user history. Clicks and system-selected citations are not reliable preference labels.

## Decision

Use TabPFN behind RankingModel for READ/KEEP/ACT/IGNORE probabilities from versioned pre-outcome features and explicit labels. Cold start uses a transparent baseline; generic seed labels are labeled as such. Proposed personal gate is 40 labels with 5 per class, subject to validation. Explicit user feedback and deadline safeguards override ranking.

## Alternatives considered

Claiming personalization from day one is misleading. Gemma-only triage lacks the intended feedback predictor. Training on system-generated labels creates a self-confirming loop.

## Consequences

Report chronological held-out macro-F1, class recall, top-k usefulness, latency, and class counts versus baseline. Prevent temporal leakage and group duplicate sources. Predictions never decide factual authority or execute actions.

## Future reconsideration triggers

Revisit label policy/thresholds after real feedback and evaluation; use baseline if evidence does not support improvement. Tinker remains an isolated later comparison.

See [Architecture](../ARCHITECTURE.md) and [Data model](../DATA_MODEL.md) for the shared contracts.

