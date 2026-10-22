# Catch Up ranking: implementation and evaluation

Task 4A, 2026-10-22 (Europe/Berlin), on checkpoint `0a54517`. Backend/library only.
Built with PriorLabs-TabPFN. This evaluation uses generic synthetic features, not personal feedback.

## Runtime and fallback

`build_catch_up(settings, tabpfn_path=...)` composes PostgreSQLRankingStore, CatchUp and an
optional local TabPFNRankingModel. Omitting the path disables model use. Missing package,
checkpoint, failed inference, invalid probabilities, sparse history or failed evaluation
leave an explicitly labeled BASELINE decision. No source is archived or deleted by ranking.
No model downloads happen as part of ordinary composition/ranking. No remote predictor,
credentials, GPU, UI, scheduler or new worker is required.

The optional extra pins `tabpfn==2.2.1`, using the public v2 classifier rather than assuming
access to newer gated models. The tested official checkpoint is
`Prior-Labs/TabPFN-v2-clf`, revision `f851f2a3c941544733b712d8c0f96dfae9b28862`, filename
`tabpfn-v2-classifier-finetuned-zk73skhh.ckpt`, **29,009,539 bytes**, SHA-256
`cf8c519c01eaf1613ee91239006d57b1c806ff5f23ac1aeb1315ba1015210e49`.
It resides in ignored `.local-tools/ranking`, not the repository. [Official model card](https://huggingface.co/Prior-Labs/TabPFN-v2-clf)
describes the Prior Labs license (Apache 2.0 with additional attribution); this is a
deliberately versioned v2 integration, not a claim of testing current v3 releases.

CPU inference uses two estimators, seed 42 and four Torch threads. Model identity includes
checkpoint hash, package/dependency versions and configuration. Telemetry is explicitly
disabled before importing TabPFN; Hugging Face offline mode is enabled. Only numeric features
and explicit labels enter the model. Dependency installation and the one public checkpoint
download were explicit development operations, separate from runtime.

## Features, feedback and user control

`catch-up-v1` fixes this vector order: source type (URL/PDF/TEXT/MARKDOWN = 0/1/2/3),
age in hours, extracted character length, duplicate capture count, source action flag,
raw deadline flag, exact topic/explicit-interest overlap, prior explicit opens, prior
resurfacings, analysis-missing flag. Missing interest overlap is -1; unknown analysis is
explicit, not an invented negative label. This slice does not implement semantic interest
similarity, authority estimates, domain/author frequency or mission-context features.

Candidate reads select the latest extraction before cutoff (including failures) and the
latest available analysis of that exact extraction. Content, analysis, captures and events
must be recorded before cutoff. Event occurrence must also precede cutoff. Immutable
observations retain IDs of source/extraction/analysis, features, duplicate grouping keys,
class probabilities, selected class, reasons, mode, model/version, context hash/event IDs
and the held-out evaluation when attempted. Features are never reconstructed for training.
Current visibility is always enforced; historical cutoff reads do not resurrect a source
which is currently archived or deletion-blocked.

The rules baseline prioritizes existing action/deadline evidence, penalizes duplicate
captures, recognizes explicit-interest matches, then uses recency/reference grouping.
Missing analysis shows ANALYSIS_PENDING; ingestion's existing analysis job stays responsible
for processing. No ranking-time inference creates new analyses or factual action proposals.

Only explicit FEEDBACK_LABELED supplies READ/KEEP/ACT/IGNORE targets. ITEM_OPENED,
ITEM_IGNORED, ITEM_ARCHIVED, ITEM_SAVED, ITEM_ACTED_ON, ITEM_RESURFACED and MISSION_USED_ITEM
are append-only context events. Even an explicit archive or acted-on event is not silently
converted into a target. Absence of feedback is never IGNORE. Corrections explicitly name
the superseded event; one current label per source is selected as of cutoff. Concurrent
corrections are serialized and stale siblings fail. Event IDs make exact retries idempotent.

Catch Up lists unreviewed active items. A direct `content_id` read can show a reviewed item
with its explicit class override. Overrides dominate all model/rule classes. A potential
deadline remains a visible flag and sorts first even under IGNORE; without an override it
also safeguards the displayed ACT class. Model probabilities are retained separately from
the safeguarded/overridden class. Actions/deadlines remain candidates, not factual guarantees.

## Personal eligibility and evaluation

No demo seeds enter production history. Training reads owner-scoped explicit labels linked
to immutable observations. Deleted/deletion-pending history is excluded. A candidate's raw
hash/source lineage is excluded from its context, including transitive duplicate aliases.
At most the latest 1,000 eligible examples enter inference. The 70/30 chronological split
uses feature cutoff; train labels must have been available before the first test cutoff.
Duplicate source/raw-content groups spanning the boundary are purged from training.

Personal mode needs at least 40 training examples with five per class, at least 20 held-out
examples with two per class, strictly higher macro-F1, no lower ACT recall, and no lower
top-5 usefulness than the rules baseline. Enough total labels alone is insufficient;
the held-out requirement makes the practical minimum larger than 40. Top-5 utility weights
READ/ACT=1, KEEP=0.5, IGNORE=0. Predictions retain the exact four-class order; absent classes
stay baseline. Evaluation uses raw classifier outputs, before deadline/override display rules.
These are conservative engineering gates, not statistical proof or calibrated confidence.
Per-request evaluation/refitting is explicit and may be too slow for a larger UI workload;
caching or background refresh requires measured follow-up rather than hidden inference.

## Reproduction and measurements

Install the optional extra with `rtk proxy .venv/Scripts/python.exe -m pip install -e '.[ranking]'`.
CPU Torch can be installed first from its official CPU wheel index to avoid GPU packages.
Provision the official checkpoint separately, verify the hash above, and run from repository root:

```powershell
rtk proxy .venv/Scripts/python.exe -m scripts.benchmark_ranking --model-path .local-tools/ranking/tabpfn-v2-classifier-finetuned-zk73skhh.ckpt
```

The script imports the synthetic fixture in tests/ranking_helpers.py. It does not read `.env`,
connect to PostgreSQL, label a user's sources or activate personal mode. [Raw results](ranking_benchmark_results.json)
include held-out features/labels/probabilities, training/test event identities, dependency
versions, counts, latency and repeat determinism. Source persistence and feedback behavior
are separately exercised against real PostgreSQL by tests/integration/test_ranking.py.

The fixture comprises 120 authored rows, 30 per class, in four intentionally simple scenario
families: substantial reading, reference material, explicit tasks and short/repetitive notices.
It is a separable synthetic integration fixture, not an unbiased relevance benchmark.
Split: **84 train / 36 test**, with **9 held-out examples per class**.

| Predictor | Macro-F1 | READ recall | KEEP recall | ACT recall | IGNORE recall | Top-5 usefulness |
|---|---:|---:|---:|---:|---:|---:|
| Rules baseline | 0.54447 | 0 | 1 | 1 | 0.44444 | 1 |
| Real local TabPFN v2 | 1 | 1 | 1 | 1 | 1 | 1 |

The initial cold import/fit/prediction took **28.5178 s**, repeated refit/prediction **0.9058 s**;
both predictions were identical. The final repeat against final code took **11.3296 s**
for cold import/fit/prediction and **0.9642 s** for a repeated refit; predictions again matched.
The raw JSON records this final repeat. This variation is another reason not to claim a
production latency distribution from two runs.
No percentile, memory, confidence interval, real-user generalization, calibration, or unbiased
quality claim is made. This fixture's improvement does not authorize PERSONAL mode for an
owner without their own qualifying labels and evaluation. Existing mission/retrieval limits
in RESEARCH_MISSION_BENCHMARK and RETRIEVAL_BENCHMARK remain in force.

## Persistence and remaining limits

Migration 0005 adds ranking_observation and user_interaction. Owner/content/extraction/analysis
and correction references are checked; insert guards reject stale labels or feedback preceding
its observation. Both tables reject ordinary update/delete. Existing migrations 0001–0004 are
unchanged. PostgreSQL remains canonical; no model state is a replacement for observations.

Feedback occurrence must follow the feature cutoff, and the database receipt must follow
the observation's database receipt. Receipt order compares one clock with itself rather
than comparing the app's occurrence clock to PostgreSQL's receipt clock. A regression test
covers immediate feedback whose occurrence timestamp precedes the DB observation receipt.

Feature/event reads currently favor clarity over high-volume query efficiency; history is
loaded before the inference cap. No authentication, erasure implementation, UI, historical
visibility reconstruction, automatic near-duplicate detection or production deployment is added.
Feedback may remain sensitive despite numeric features. Full deletion/backup retention remains
a separate prerequisite before real private data. Community research was attempted but the
installed DevRelay connector returned a sign-in-service error; no community consensus is claimed.
