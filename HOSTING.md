---
doc: RES-800
title: Hosting Guide
status: stable
depends_on: [RES-320, RES-321, RES-322]
referenced_by: []
---

# Hosting Guide

Deploy Resileos-QAI as a knowledge/query service: Titanos + residual substrate + FastAPI + Streamlit. It is not a next-token generative LLM. Answers come from the band store via `query` / `chain` / SPARQL.

## 1. What runs

| Component | Port | Entry point |
|---|---|---|
| FastAPI backend | 8000 (loopback) | `asgi:app` |
| Streamlit dashboard | 8501 (loopback) | `ui.py` |
| Titanos band store | in-process | `scripts/titanos.py` |
| Residual substrate | in-process | `resileos.substrate` |

Single process. The Titanos store is a module-level singleton. Keep `--workers 1` and one replica unless the store is externalized.

## 2. Quick start (Docker)

```bash
git clone https://github.com/jackyreaps/Resileos-QAI.git
cd Resileos-QAI
touch titanos_live_state.json
