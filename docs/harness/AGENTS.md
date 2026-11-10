# AGENTS.md — Standing instructions for the Resileos harness
# Auto-discovered / JIT loaded into control packets.

## Core invariants
- Residual core is deterministic. Harness never mutates it directly.
- Control packets are the sole interface.
- Verify-on-stop is mandatory before closing a turn that touched scars or tools.

## Tool preference
1. residual_consistency or Apollo for verification
2. decision_fanout + confidence_route for bounded questions
3. leCore route for external capabilities
4. Escalate only when confidence < 0.7 or risk = ask

## Stop conditions
- verified == true AND budget_remaining.steps > 0
- or explicit abstain / deny
