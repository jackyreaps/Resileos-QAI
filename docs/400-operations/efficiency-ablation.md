---
doc: RES-405
title: Efficiency Ablation (Framework-Native vs NLL)
status: stable
depends_on: [RES-315, RES-401]
referenced_by: []
---

# Efficiency Ablation (Framework-Native vs NLL)

Hardened Roadmap item 1.1 — **BLOCKING** for v2.0.0 large-run scope.

Same decoder, same carrier, same task. Two training modes:

| Mode | Loss |
|------|------|
| `nll` | cross-entropy only |
| `framework` | CE + λ_R·recovery + λ_coh·coherence + λ_res·residue |

Three reported factors (not interchangeable):

| Symbol | Meaning | Toy reliability |
|--------|---------|-----------------|
| `k_steps` | steps_nll / steps_framework | Reliable |
| `k_flops_est` | FLOPs_nll / FLOPs_framework (analytic) | Use in roadmap equation |
| `k_wall_toy` | wall_nll / wall_framework | **Unreliable** (Python-bound) |

Roadmap equation (production data cost `D` measured separately):

```text
Total compute ≈ (1.2e24 * (1 + D)) / k_flops_est
