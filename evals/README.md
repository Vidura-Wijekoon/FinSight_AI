# Evaluation harness

The test suite verifies that the pipeline runs. This verifies that it is
*right* — that retrieval surfaced the correct source, and that the answer is
grounded in it. Those fail separately, and only one of them is visible from a
passing test.

This is a working skeleton, not an evaluation platform. It measures a single
fixture document with twenty queries.

## Current baseline

| Metric | Value | Ceiling |
|--------|-------|---------|
| precision@4 | 0.3125 | 0.3281 |
| recall@4 | 0.9375 | 1.0 |
| MRR | 0.9375 | 1.0 |
| recall@4, simple lookup | 0.8750 | 1.0 |
| recall@4, multi-hop | 1.0000 | 1.0 |
| recall@4, numeric | 1.0000 | 1.0 |

Reproducible across repeated runs. Measured after the fix to
`KNOWN_LIMITATIONS.md` item 19 — this harness found, on its first run, that
every stored vector was the embedding of the empty string, making retrieval an
arbitrary tie-break. The figures before that fix were precision@4 0.25,
recall@4 0.75 and MRR 0.4271.

No threshold is set yet; see "Setting the threshold" below.

## Running it

```bash
python evals/run_eval.py                    # retrieval metrics only
python evals/run_eval.py --with-generation  # adds generation metrics
python evals/run_eval.py --no-write         # do not write a report file
```

Retrieval metrics need only the embedding model, so they run in CI. Generation
metrics need a local 7B model through Ollama, which a standard GitHub runner
cannot host — no GPU and insufficient disk — so they are local-only and
deliberately not gated.

Reports are written to `evals/results/` and are gitignored. Each records the
golden set content hash, entry count, top-k, embedding model, generation model
and chunking parameters, so a number can always be traced to what produced it.

## The golden set

`golden_set.jsonl`, twenty entries against `tests/fixtures/sample_document_Q3.txt`:

| Category | Count | Tests |
|----------|-------|-------|
| `simple_lookup` | 8 | A fact stated verbatim in one chunk |
| `multi_hop` | 4 | A fact requiring two or more chunks |
| `numeric` | 4 | A figure that must be computed, never stated |
| `abstention` | 4 | A question the document cannot answer |

`expected_source_ids` were derived by chunking the fixture at 512/50 and reading
which chunk holds each fact. They are not estimates.

Seven `expected_answer` fields are marked **`TODO_VERIFY`** — every multi-hop and
numeric entry. Those answers require arithmetic or interpretation not present in
the document, and fabricating them would make the harness worse than not having
one. Retrieval metrics do not depend on them. Generation metrics that compare
answer text are not meaningful until they are filled in by a human.

## Metrics

**Retrieval**, against `expected_source_ids`:

- **precision@k** — proportion of returned chunks that are relevant. Divided by
  k, not by the number returned, so returning fewer than k is penalised.
- **recall@k** — proportion of relevant chunks that were returned.
- **MRR** — reciprocal rank of the first relevant chunk, 0 if none appears.

Recall is also broken out per category, because a system can look acceptable in
aggregate while failing entirely on one query shape.

**On reading precision@k.** It is bounded by how many relevant chunks exist. A
query with one relevant chunk cannot exceed 0.25 at k=4. Across this golden set
the ceiling is **0.328**, not 1.0. A threshold must be set relative to that
ceiling; comparing the figure to 1.0 will read as catastrophic when it is not.
Recall@k and MRR are the more informative headline numbers here.

**Generation**, local only:

- **citation presence rate** — proportion of answerable queries whose answer
  contains at least one `[Chunk X]` marker.
- **citation accuracy** — of the chunks actually cited, the proportion that are
  in `expected_source_ids`.
- **out-of-range citations** — count of citations naming a chunk number that was
  never supplied. The pipeline drops these silently; see limitation 15.
- **abstention accuracy** — proportion of abstention queries the model declined.
- **false abstention rate** — proportion of *answerable* queries it declined.
  Reported alongside abstention accuracy on purpose: a model that refuses
  everything scores 1.0 on the first metric, and this is what exposes it.

Abstention entries have no relevant chunk, so precision and recall are undefined
rather than zero for them. They are excluded from retrieval aggregates and
counted as `unscored_queries`; scoring them as zero would penalise correct
behaviour.

## No LLM-as-judge, deliberately

Every metric here is deterministic and reproducible. Judged metrics —
faithfulness, answer relevance — are the intended next step, and they are not in
this package because they need care that a skeleton cannot carry.

When they are added, **the judge must be a different model family from the
generator.** A model scoring its own output exhibits self-preference bias and
rates its own generations more highly than a neutral judge does. Using Qwen to
judge Qwen would produce numbers that improve as the system gets worse at
disagreeing with itself.

## Setting the threshold

The threshold is **0.29** and the CI job gates on it.

The arithmetic behind that number, since a round figure would have been a guess:
the measured value is 0.3125 against a ceiling of 0.3281. One query losing its
relevant chunk from the top four costs `0.25 / 16 = 0.0156`, giving 0.2969. Two
gives 0.2813. A floor of 0.29 therefore tolerates one query slipping — enough
headroom for the embedding model behaving slightly differently on Linux than on
the Windows machine this was measured on — and fails on two.

Once a Linux CI run confirms the baseline, raise it to **0.31**. That leaves the
gate tight enough to catch a single-query regression, which is what you
ultimately want from it.

While the threshold is `null` the harness reports the number and exits 0.
