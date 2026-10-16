doc: RES-323
title: External Ingestion
status: draft
depends_on: [RES-310, RES-311, RES-312, RES-320, RES-321, RES-322, RES-401]
referenced_by: []

# External Ingestion

Ingest external sources — LLM outputs, corpora, structured data — into
the substrate. The substrate is the parent; sources are the children
that get eaten. After ingestion, the source is no longer consulted. The
substrate's φ-ladder representation is self-sufficient for retrieval.

## 1. Direction

    external source
        │
        ▼
    tokens ──▶ HierarchicalEncoder ──▶ packets with φ-power addresses
        │
        ▼
    R-gated filter ──▶ accepted packets
        │
        ├──▶ StreamState      (φ-weighted running context)
        │
        └──▶ extractor ──▶ Titanos.learn()  (structured facts)

The substrate is not a child of an external model. It eats external
models. It ingests their output, projects it onto the φ-ladder, keeps
the component that is coherent under R, and discards the rest.

## 2. The φ-ladder

Every level in the hierarchy carries a φ-power address.

| Level | Address | Meaning |
|---|---|---|
| 0 | φ⁰ = 1 | tokens |
| 1 | φ⁻¹ ≈ 0.618 | level-1 packets (a few tokens) |
| 2 | φ⁻² ≈ 0.382 | level-2 packets (a paragraph) |
| 3 | φ⁻³ ≈ 0.236 | level-3 packets (a document) |
| L | φ^(−L) | level-L packets |

The address is what makes orientation survive contraction. Higher
levels are abstractions of many tokens; the φ-scaling means each
level's contribution to the running stream is geometrically smaller
than the one below, and no two levels ever resonate.

Folding a packet into the stream:

    weight = φ ** (-packet.level)
    stream_hv = normalize(stream_hv + weight · packet.hv)

This is the same operation `StreamState` performs with `decay**level`,
with `decay = 1/φ`. The default is `φ`-weighting for ingestion.

## 3. The R gate

Orientation is preserved only when the field is oriented. R measures
this.

| R range | Field state | Ingestion behavior |
|---|---|---|
| > 0.9 | locked | accept all levels; contraction safe |
| 0.3 – 0.9 | mixed | accept only levels 0–1; contraction unsafe |
| < 0.3 | exploring | accept only level 0; no abstraction |

The gate is per-ingest-call, computed from the field's current R
before the call. Ingesting under high R allows deep compression.
Ingesting under low R keeps the content at shallow levels.

## 4. Pipeline stages

| Stage | Input | Output | Where |
|---|---|---|---|
| Tokenize | text | token IDs | `CharTokenizer` |
| Encode | token IDs | packets at levels 1..K | `HierarchicalEncoder` (RES-310) |
| Filter | packets | accepted / rejected | this document, §5 |
| Fold | accepted packets | updated stream | `StreamState` (RES-311), φ-weighted |
| Extract | accepted packets | (subject, relation, object) | caller-supplied |
| Store | triples | Titanos facts | `Titanos.learn` (RES-320) |

Each stage is independent. The pipeline can run with the filter off,
the extractor off, or both.

## 5. Quality filters

Three gates per packet:

| Gate | Meaning | Default |
|---|---|---|
| R | field lock during encoding | > 0.5 |
| CSI | self-consistency of the trajectory | > 0.5 |
| Level | maximum level accepted at current R | from §3 |

Plus per-source gates: `source_blacklist` and `max_per_source`.

Thresholds are operational. They are tuned per application. The
`coherence_min` field exists in the config but is not enforced in v1.

## 6. The eat mechanism

An external LLM's output is dense — it carries token-frequency and
entropy structure that does not respect the φ-ladder. When ingested
through a φ-ladder hierarchy, the substrate projects the output onto
the ladder. The φ-coherent component survives filtering; the rest is
discarded.

    external output
        │
        ▼
    project onto φ-ladder
        │
        ├──▶ coherent component ──▶ stream + facts
        │
        └──▶ incoherent component ──▶ discarded

What "eaten" means: the external source is ingested, projected, and
discarded. The substrate retains the φ-coherent part. Retrieval works
from the retained part.

This is not lossless. The retained part is a projection. Whether the
projection is useful depends on the downstream application, and on the
quality of the R gate at ingestion time.

## 7. Multi-source consensus

When N sources are ingested about the same subject, the stream
accumulates φ-weighted contributions from all accepted packets. The
result is a heavy consensus: a single hypervector weighted by
per-packet quality and by the φ-power address of each level.

N sources → 1 representation. That is the eat mechanism under
multiple parents.

## 8. Non-claims

- Not lossless. The eat mechanism is a projection. What is retained is
  the φ-coherent component, not the source.
- Not a claim of correctness. Filtering is on quality, not truth.
- Not a claim that the φ-ladder captures all useful structure. It
  captures orientation. If the useful structure is not oriented under
  R, this pipeline does not capture it.
- Not a replacement for the source. The source is discarded. If exact
  recall is needed, the source must be retained elsewhere.
- Not generation. Structured answers, not prose.

## 9. Interface

    ingestor = SourceIngestor(
        encoder=enc,
        stream=stream,
        titanos=titanos,       # optional
        cfg=IngestionConfig(),
    )

    result = ingestor.ingest(
        tokens=tokenizer.encode(llm_output),
        source_id="gpt-4o-2026-10-16",
        quality_fn=my_quality,  # optional; default accepts all
        extractor=my_extractor, # optional; default extracts nothing
    )

`result.packets_accepted` and `result.facts_written` are the summary.
`ingestor.readout()` returns the current compressed representation.

## 10. Open questions

- **Ladder coherence gate.** §3 gates on R alone. A second gate on the
  surviving ladder addresses (§5 of RES-401) is not implemented.
- **Deduplication.** Two sources producing the same content are both
  ingested. A content-addressed hash on the packet hypervector is the
  natural fix. Not implemented.
- **Cross-source consensus threshold.** A stronger filter would require
  N sources to agree before a fact is written. Design choice, not
  implemented.
- **φ-exponent tuning.** `φ^(-L)` is a specific choice. Whether the
  correct exponent is 1, 2, or something else is an empirical question.

## 11. Read next

- [Disk-Backed Band Store](store.md) — RES-320
- [Query Language and Execution](query.md) — RES-322
- [phi-compress redesign required](../400-operations/phi-compress-redesign.md) — RES-401
- [Hierarchical Encoding](../310-hierarchy/hierarchical-encoding.md) — RES-310
- [Streaming Substrate State](../310-hierarchy/streaming-state.md) — RES-311
- [Documentation Index](../readme.md)
