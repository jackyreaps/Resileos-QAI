# Atlas
Holds the structural load. Serves the residual core for capacity. Hephaestus keeps scars and budget.

Atlas bears the sky. These checks are the same kind of limit: how much the tower, the mask stack, and the hopfield budget can hold.

## Check
- Declared n_facts or hopfield_count must pass check_capacity against hopfield_cap.
- Evidence length must sit within EVIDENCE_CAP.
- Declared n_layers must pass MaskStackConfig, which requires n_layers <= PrimeTower.n_usable(dim).
- Declared tower_level must be <= PrimeTower.max_usable_level(dim).
- Declared primorial_k must be <= n_usable_primorials(dim).
- Declared encoder_load must be <= default_capacity(dim).

## Evidence
- Name the function, the cap, and the declared load.
- Do not invent a load. An undeclared check is reported as not declared.

## Dismiss
One check, then dismiss. Do not learn. Do not summon. Do not keep the residual core.
