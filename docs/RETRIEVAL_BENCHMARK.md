# Retrieval benchmark and embedding smoke

Measured locally on 2026-10-21 with synthetic text only. This is a small labeled fixture, not a general retrieval-quality claim.

## Environment and actual embedding smoke

Existing PostgreSQL **17.11** and Ollama **0.40.6** were reused. Installed dedicated embedding model: **qwen3-embedding:latest**, **4,676,805,193 bytes** (4.7 GB), Q4_K_M, reporting a 7.6B/8B model and embedding capability. Actual installed digest: `64b933495768fbd3b87c20583d379728a07471e0c66733a9df87cd1901b3c44b`. No model download or silent model substitution occurred. The generative Gemma AIProcessor remains separate.

Actual vectors had **4,096 dimensions**. Single first request: **28.6491 s**, including model loading. A subsequent warm batch of three: **0.7176 s** total. Runtime vector norms ranged from **0.999999726** to **1.000000490**, consistent with unit normalization on these samples. The adapter explicitly normalizes and validates vectors itself and records the normalization mode as l2-v1. See [raw smoke measurements](embedding_smoke.json). These sample norms do not establish a universal runtime guarantee. Memory attributable to the embedding model was not measured.

The adapter uses Ollama's documented [embed API](https://docs.ollama.com/api/embed), bounded inputs/batches/timeouts, and `truncate=false`. Query instructions use the explicit versioned “Retrieve relevant saved source passages” prefix; documents receive no query prefix. The [Ollama model listing](https://ollama.com/library/qwen3-embedding) describes the dedicated model family. Provider responses do not cross the application port.

pgvector was initially absent from the vanilla postgres:17 container. Installed **postgresql-17-pgvector 0.8.7-1.pgdg13+1** in the existing isolated container: 274 KB package, 774 KB installed, no server upgrade or replacement database. Migration 0003 enabled extension **0.8.7** in public. Native `public.vector` storage and exact cosine insert/query succeeded for the actual 4,096-dimensional vectors. No approximate vector index was added. Container package changes are ephemeral; a newly created vanilla container needs the package installed again or remains lexical-only. The shared extension is intentionally retained on downgrade.

## Fixture and method

Evaluation uses **13 owned documents**, **16 owned chunks**, and **12 labeled queries**. A second owner has a matching private distractor. Corpus includes exact identifiers/dates, overlapping energy topics, near-duplicate solar documents, paraphrases with few shared words, unrelated distractors, and a long maintenance document spanning four chunks. Labels are expected relevant document identities. They are available alongside the corpus in `scripts/benchmark_retrieval.py`; raw results are [machine-readable JSON](retrieval_benchmark_results.json).

Chunking: deterministic 1,000-character windows, 150-character overlap, page boundaries respected, chunk IDs pinned to owner/extraction/chunker configuration/range. Lexical: PostgreSQL generated tsvector + GIN, **simple** dictionary with plain-token AND queries and ts_rank_cd proximity ranking. No stemming or stopword removal; punctuation still follows PostgreSQL's native parser. Query text is a bound value passed through plainto_tsquery, not raw tsquery/SQL syntax.

Vector: exact cosine distance within the requested owner, collections, current extraction, chunker version and full embedding namespace. Hybrid: **RRF k=60**, `sum(1/(60+rank))`. Both SQL candidate paths cap chunks per source before candidate limits; final fusion caps again and deduplicates chunk IDs. Result limit **5**, per-source cap **2**, candidate budget **30** for this run. Stable UUID tie ordering is used. No synthesis, learned ranking or score calibration.

Recall@5 is the fraction of labeled relevant documents found among the first five returned chunks. MRR uses the chunk position of the first relevant document. Diversity is the number of distinct ContentItem IDs among those chunks; near-duplicate documents remain distinct. Latency includes actual query embedding/SQL/fusion as applicable, but excludes ingestion/chunk indexing. Modes ran sequentially; cache/order effects and sample size preclude speed superiority claims between vector and hybrid.

| Mode | Recall@5 | MRR | Mean source diversity | Mean query seconds |
|---|---:|---:|---:|---:|
| Lexical only | 0.667 | 0.667 | 0.750 | 0.0143 |
| Vector only | 1.000 | 1.000 | 4.750 | 0.5388 |
| Hybrid | 1.000 | 1.000 | 4.750 | 0.4834 |

Lexical missed the paraphrases, including “pet napping by hearth” and “overnight stored energy”; its exact dates/identifiers remained searchable. Both semantic modes found the labeled relevant documents. Hybrid tied vector on these metrics; it did not demonstrate additional accuracy. More returned sources also includes distractors, so diversity alone is not relevance. No cross-owner row appeared. All **16 chunk embeddings** were successfully generated/persisted; bounded workflow time **7.6017 s**, with no failed chunks. The real smoke is separate from deterministic pytest.

**Decision:** keep fast, model-independent lexical retrieval as the default. Vectors/hybrid are explicitly enabled when semantic recall is useful; their measured cost was much higher on this fixture. No automatic embedding-model fallback.

## Reproduction and limits

Export DATABASE_URL and run `scripts/benchmark_retrieval.py` through the documented Python environment. It creates fresh synthetic owner scopes in the configured database, indexes the built-in corpus, generates real local embeddings, runs all three modes and writes the JSON report. It does not load .env or download models. The separate unit/integration suite uses fake embeddings and real PostgreSQL, never mandatory Ollama inference.

The fixture was authored with known semantic paraphrases and is too small for generalization or tuning claims. No held-out production corpus, multilingual retrieval, ANN, scaling/load benchmark, cross-encoder reranking or statistical confidence intervals were evaluated. Native parser behavior and AND semantics limit lexical fuzzy/plural/substring matching. Chunk boundaries can divide phrases. Retrieval is not factual entailment. New extractions require explicit indexing; stale extraction chunks are excluded even before reindexing. Historical source snapshots remain separate active ContentItems until their retrieval visibility is changed; lineage collapsing is not implemented. Visibility flags suppress retrieval but do not erase originals or implement privacy deletion/authentication.
