# Resileos-QAI

Resileos-QAI: a layered architecture for residual compression and generative hypervector dynamics, with a gated quantum backend.

## What this is

Resileos-QAI is a low-compute knowledge graph engine. It ingests `(subject, relation, object)` facts, stores them in a compressed hypervector representation, and answers multi-hop relational queries — **without calling an external LLM**.

**Why it's cheap to run:** the classical core uses Vector Symbolic Architecture operations (element-wise binding, bundling, and cleanup) instead of transformer attention. A $5/month instance handles what would otherwise require GPU infrastructure.

**What it is not:** a general-purpose language model, a quantum computer, or a trillion-token retrieval system. It is a memory layer that returns exact answers or abstains — it does not invent. See [RES-313](docs/310-hierarchy/capacity-law.md) for explicit non-goals.
