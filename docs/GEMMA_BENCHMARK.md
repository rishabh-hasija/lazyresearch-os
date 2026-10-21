# Local Gemma benchmark

Measured 2026-10-21 with synthetic text only. This is a small smoke corpus, not a statistical quality evaluation or production SLA.

## Machine, runtime and selection

- Windows, Python 3.12.10; 16,487,870,464 bytes RAM (15.36 GiB).
- NVIDIA GeForce RTX 3060 Laptop GPU, 6,144 MiB VRAM.
- Installed/running Ollama **0.40.6**, llamacpp runner; 8,192-token configured context.
- Gemma 4 E4B was initially absent. The user explicitly approved downloading **gemma4:e4b** after the size report. Ollama registry layers totalled **6,583,656,264 bytes (6.58 GB)**; installed listing reports 6.6 GB, Q4_K_M, 7.5B parameter-size metadata.
- Actual installed digest: `dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c`.
- Installed fallback **gemma3:4b**, 3.4 GB, was also tested. No additional fallback download or remote inference was used.

Ollama's [model listing](https://ollama.com/library/gemma4:e4b) supplies the runtime tag; documentation availability was not treated as a local benchmark. Google's [model card](https://ai.google.dev/gemma/docs/core/model_card_4) identifies Apache 2.0 licensing. The adapter follows the documented [structured-output format](https://docs.ollama.com/capabilities/structured-outputs) and [chat API](https://docs.ollama.com/api/chat), then performs its own validation.

After inference, nvidia-smi showed total GPU use around **4,573–4,585 MiB**, versus 14 MiB initially. These are whole-GPU snapshots, not precise model allocation or a measured peak. Ollama `/api/ps` and `ollama ps` reported 100% GPU but only **369,423,809 bytes** resident size/VRAM for Gemma 4; this disagrees with the GPU-level reading and must not be represented as the model's true memory footprint. CPU offloading was not observed in Ollama's processor indicator. Accurate total host RAM attributable to inference and peak VRAM were not measured. Windows Ollama process snapshots are not a reliable aggregate runner-memory measurement.

## Iterations and failures retained

1. Prompt v1 / analysis-v1 requested model-generated character offsets. JSON/schema passed **7/7**, but complete locator validation passed **1/7**. Incorrect offsets were rejected; explicit actions were also missed. First-ever request took **103.134 s** including startup; the comparable warm request took **10.591 s**. See [initial v1 measurements](gemma_benchmark_initial_v1.json).
2. Prompt v2 supplied an entire citation template but still let the model emit numeric spans. Schema passed **7/7**, full locator validation **3/7**. Copying the template in prose did not reliably fix offset generation. See [initial v2 measurements](gemma_benchmark_initial_v2.json).
3. Preallocated evidence IDs removed offset arithmetic: the adapter resolves an exact known ID to the immutable segment. Prompt v3 / analysis-v2 passed full validation **6/7**. The facts-only item emitted action_required with no actions twice; one bounded repair failed and the output was rejected. See [anchor iteration](gemma_benchmark_results.json) and [synthetic diagnostic](gemma4_facts_diagnostic.json). The diagnostic raw response contains only synthetic data.
4. Final prompt **source-analysis-v4**, schema **analysis-v2**, pipeline **source-chunks-anchors-bytes-v3**, temperature 0, 2,400 output tokens, 120-second call timeout: **7/7** passed schema and exact locator validation without repair. The model was already resident; this final batch does not measure cold startup. Prompt hash: `bf337fb0dcf0dd6c812c53450624863c95f9f404a04d63e8cd70450c7259ec8a`. See [final measurements and synthetic outputs](gemma4_benchmark_final.json).

| Final fixture | Wall seconds | Observation |
|---|---:|---|
| Clear deadline newsletter | 7.629 | One application candidate; date-only 2026-11-07 |
| Facts, no requested action | 18.907 | No action; factual claims retained |
| Ambiguous deadline | 6.694 | Candidate retained; “next Friday” unresolved |
| Contradictory dates | 6.862 | Both conflicting claims retained with high uncertainty; no chosen deadline/action |
| Prompt injection | 10.996 | Real deadline retained; embedded instruction described as evidence, not obeyed |
| No meaningful information | 2.526 | Insufficient information; no claims or actions |
| Clear deadline, repeated warm | 8.589 | Correct candidate/date; no repair |

Final median across these seven requests: **7.629 s**; range **2.526–18.907 s**. No p95 performance claim is justified by seven requests. The source identities differ between requests, including the warm repeat. Temperature 0 is not a guarantee of reproducibility.

## Fallback and end-to-end smoke

Gemma 3 4B with the earlier anchor prompt passed schema **7/7** and complete validation **5/7**. Facts-only and contradictory fixtures failed entity/deadline evidence checks. First request was **15.725 s**, repeated warm clear-deadline request **4.720 s**. See [fallback measurements](gemma3_benchmark_results.json). It was not rerun with the final prompt, so these are not a controlled final-prompt model comparison. Gemma 4 was selected because the final configuration ran successfully on this machine; Gemma 3 remains an explicit configurable fallback, not an automatic substitution.

The separate [real model plus PostgreSQL smoke](gemma_postgres_smoke.json) saved an original, performed actual Gemma 4 inference, and committed a COMPLETE analysis with **2 claims, 1 action, and normalized date 2026-11-07** through the production use case. It used the isolated development database and a new synthetic owner. It is not part of pytest.

## Limits and reproduction

Run `scripts/benchmark_gemma.py --model gemma4:e4b` separately from deterministic tests. `--case` limits the built-in synthetic corpus; `--output` chooses the JSON report. No private inputs or machine identifiers are collected. Benchmark output intentionally retains synthetic generated text. Normal application calls never log their payloads.

Evidence IDs guarantee resolution to a known supplied chunk, not that a claim is entailed by that chunk. These locators are coarse chunk ranges. Claims remain UNREVIEWED; a human review helper is available. Summaries/topics are orientation aids, not separately verified claims. Only one injection example and short English texts were evaluated. Large-document quality, cross-chunk contradictions, non-English inference, concurrency throughput, long-term stability, other GPUs and hosted inference remain unmeasured. A failed schema/citation check safely fails the operation and preserves the original; the initial failures above must not be hidden by the successful final run.
