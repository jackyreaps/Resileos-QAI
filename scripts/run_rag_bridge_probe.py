#!/usr/bin/env python3
"""RAG bridge probe (Path 1).

Does passing retrieved facts to a frozen model improve exact-match
accuracy on a relational task, compared to the model alone?

Three conditions measured on the same queries:
    1. store alone     — Titanos exact retrieval (the ceiling)
    2. model alone     — frozen decoder, no retrieval (parametric)
    3. model + store   — retrieved rows injected into prompt (RAG)

Metric: strict exact match on the gold answers in titanos-facts.json.

The probe answers the "frontier-adjacent" question directly: can
Resileos act as the memory layer for a rented model, or does the model
already know the facts? If store_accuracy is ~1.0 and model_alone is
near 0, the ceiling is the store and RAG is the bridge. If
model_plus_store ≈ model_alone, retrieval is not helping and the
prompt / model combination needs revision.

No training. Model is frozen. Greedy generation for determinism.

Usage:
    python scripts/run_rag_bridge_probe.py \
        --facts configs/titanos-facts.json \
        --decoder Qwen/Qwen2.5-0.5B \
        --out artifacts/report_rag_bridge.json

    # Smoke on 5 queries first:
    python scripts/run_rag_bridge_probe.py --limit 5
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
except ImportError as e:
    print(f"missing dependency: {e}", file=sys.stderr)
    print("install with: pip install torch transformers", file=sys.stderr)
    sys.exit(1)

from titanos import Titanos, TitanosConfig  # noqa: E402


# ── config loading ─────────────────────────────────────────────────────


def load_facts_config(path: Path) -> tuple[list[tuple], list[dict]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    facts = []
    for row in raw.get("facts", []):
        if isinstance(row, (list, tuple)) and len(row) == 3:
            s, r, o = (str(x).strip() for x in row)
            if s and r and o:
                facts.append((s, r, o))
    queries = list(raw.get("queries", []))
    return facts, queries


# ── store ──────────────────────────────────────────────────────────────


def build_store(facts: list[tuple]) -> Titanos:
    titan = Titanos(TitanosConfig(
        dim=10000, m=100, n=100, r=8, n_loops=12, seed=1337,
    ))
    titan.learn_many(facts)
    return titan


def store_answer(titan: Titanos, query: dict) -> list[str]:
    """Exact retrieval via ask_list. Single-value and multi-value both."""
    s = query["subject"]
    r = query["relation"]
    inv = bool(query.get("inverse", False))
    try:
        return titan.ask_list(s, r, inverse=inv)
    except Exception:
        return []


def store_exact_match(rows: list[str], expected: str) -> bool:
    if not rows:
        return False
    exp = expected.strip().lower()
    return any(exp == row.strip().lower() for row in rows)


# ── prompts ────────────────────────────────────────────────────────────


def _humanize_relation(r: str) -> str:
    return r.replace("_", " ")


def build_prompt_model_alone(query: dict) -> str:
    s = query["subject"]
    r = _humanize_relation(query["relation"])
    if query.get("inverse", False):
        q = f"What has {r} pointing at {s}?"
    else:
        q = f"What is {s}'s {r}?"
    return (
        f"Question: {q}\n"
        f"Answer with just the entity name, nothing else.\n"
        f"Answer:"
    )


def build_prompt_with_store(query: dict, rows: list[str]) -> str:
    s = query["subject"]
    r = _humanize_relation(query["relation"])
    if rows:
        facts_str = "\n".join(f"  - {row}" for row in rows)
    else:
        facts_str = "  (no facts retrieved)"
    if query.get("inverse", False):
        q = f"What has {r} pointing at {s}?"
    else:
        q = f"What is {s}'s {r}?"
    return (
        f"Retrieved facts:\n{facts_str}\n\n"
        f"Question: {q}\n"
        f"Answer with just the entity name, nothing else.\n"
        f"Answer:"
    )


# ── generation and extraction ──────────────────────────────────────────


@torch.no_grad()
def generate(
    model,
    tokenizer,
    prompt: str,
    device: torch.device,
    max_new_tokens: int = 8,
) -> str:
    inputs = tokenizer(prompt, return_tensors="pt").to(device)
    out = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        do_sample=False,
        num_beams=1,
        pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
    )
    new_tokens = out[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def extract_answer(text: str) -> str:
    if not text.strip():
        return ""
    line = text.strip().splitlines()[0]
    return line.strip().strip("\"'.,!?;:")


def is_match(pred: str, expected: str) -> bool:
    if not pred:
        return False
    return pred.strip().lower() == expected.strip().lower()


# ── main ───────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description="RAG bridge probe")
    ap.add_argument("--facts", default="configs/titanos-facts.json")
    ap.add_argument("--decoder", default="Qwen/Qwen2.5-0.5B")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--max-new-tokens", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--out", default="artifacts/report_rag_bridge.json"
    )
    args = ap.parse_args()

    if args.device == "auto":
        device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )
    else:
        device = torch.device(args.device)

    facts_path = Path(args.facts)
    if not facts_path.exists():
        print(f"facts not found: {facts_path}", file=sys.stderr)
        return 1
    facts, queries = load_facts_config(facts_path)
    if not queries:
        print(f"no queries in {facts_path}", file=sys.stderr)
        return 1
    if args.limit:
        queries = queries[: args.limit]
    print(f"loaded {len(facts)} facts, {len(queries)} queries")

    print("building Titanos store...")
    titan = build_store(facts)
    print(f"  stored: {titan.stats()['facts']} facts")

    print(f"loading model {args.decoder} on {device}...")
    tokenizer = AutoTokenizer.from_pretrained(args.decoder)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        args.decoder, torch_dtype=torch.float32
    ).to(device)
    model.eval()
    for p in model.parameters():
        p.requires_grad_(False)
    print(f"  vocab: {model.config.vocab_size}")

    store_correct = 0
    alone_correct = 0
    rag_correct = 0
    per_query = []

    n = len(queries)
    for i, q in enumerate(queries):
        rows = store_answer(titan, q)
        s_ok = store_exact_match(rows, q["expected"])
        if s_ok:
            store_correct += 1

        prompt_alone = build_prompt_model_alone(q)
        pred_alone = extract_answer(
            generate(
                model, tokenizer, prompt_alone, device,
                args.max_new_tokens,
            )
        )
        a_ok = is_match(pred_alone, q["expected"])
        if a_ok:
            alone_correct += 1

        prompt_store = build_prompt_with_store(q, rows)
        pred_store = extract_answer(
            generate(
                model, tokenizer, prompt_store, device,
                args.max_new_tokens,
            )
        )
        r_ok = is_match(pred_store, q["expected"])
        if r_ok:
            rag_correct += 1

        per_query.append({
            "subject": q["subject"],
            "relation": q["relation"],
            "inverse": bool(q.get("inverse", False)),
            "expected": q["expected"],
            "store_rows": rows,
            "store_correct": bool(s_ok),
            "model_alone_pred": pred_alone,
            "model_alone_correct": bool(a_ok),
            "model_store_pred": pred_store,
            "model_store_correct": bool(r_ok),
        })

        if (i + 1) % 5 == 0 or i == n - 1:
            print(
                f"  [{i+1}/{n}]  store={store_correct}  "
                f"alone={alone_correct}  rag={rag_correct}"
            )

    store_acc = store_correct / n
    alone_acc = alone_correct / n
    rag_acc = rag_correct / n
    delta = rag_acc - alone_acc

    if delta > 0.05:
        verdict = "retrieval helps: model+store beats model alone"
    elif delta < -0.05:
        verdict = (
            "retrieval hurts: model+store is worse than model alone"
        )
    else:
        verdict = "no measurable retrieval effect"

    report = {
        "probe": "rag_bridge",
        "decoder": args.decoder,
        "facts_path": str(facts_path),
        "n_facts": len(facts),
        "n_queries": n,
        "store_accuracy": store_acc,
        "model_alone_accuracy": alone_acc,
        "model_plus_store_accuracy": rag_acc,
        "retrieval_delta": delta,
        "verdict": verdict,
        "per_query": per_query,
        "notes": [
            "store alone = exact retrieval from ask_list (ceiling)",
            "model alone = frozen decoder, parametric knowledge only",
            "model + store = retrieved rows injected into prompt",
            "retrieval_delta = rag_accuracy - alone_accuracy",
            "strict exact match on stripped first line of output",
            "generation is greedy (do_sample=False) for determinism",
        ],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))

    print()
    print(f"store alone:        {store_correct}/{n}  ({store_acc:.1%})")
    print(f"model alone:        {alone_correct}/{n}  ({alone_acc:.1%})")
    print(f"model + store:      {rag_correct}/{n}  ({rag_acc:.1%})")
    print(f"retrieval delta:    {delta:+.1%}")
    print(f"verdict: {verdict}")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
