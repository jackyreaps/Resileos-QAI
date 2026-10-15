def boundary_codimension(step_fn, cfg) -> float:
    """Estimate n - d_b in the full state space.

    Sample random pairs at separation delta, measure P(straddle) = fraction
    where the two endpoints land in different basins. For a boundary of
    dimension d_b, P(straddle) ~ delta^(n - d_b). Fit log P vs log delta.

    Returns the codimension n - d_b. Codim -> 0 means the boundary fills
    the space (sheath). Codim ~ 1 means it is a thin surface (constraint).

    If no pair straddles at any delta, there is no boundary in the sampled
    volume. Codimension is maximal: the return is cfg.n_dims, not 0. The
    previous implementation returned ~0 in this case because the flooring
    step forced every P to the same value and the slope of a constant is 0.
    """
    rng = np.random.default_rng(cfg.seed + 3)
    deltas = np.asarray(cfg.codim_deltas, dtype=float)
    raw_counts: list[int] = []
    ps: list[float] = []
    for d in deltas:
        straddles = 0
        for _ in range(cfg.codim_pairs):
            a = rng.uniform(-1.0, 1.0, size=cfg.n_dims)
            u = rng.standard_normal(cfg.n_dims)
            u /= np.linalg.norm(u) + 1e-12
            b = a + d * u
            if int(step_fn(a)) != int(step_fn(b)):
                straddles += 1
        raw_counts.append(straddles)
        ps.append(straddles / cfg.codim_pairs)

    # No boundary observed at any scale. Codimension is the full space.
    if all(c == 0 for c in raw_counts):
        return float(cfg.n_dims)

    ps_arr = np.array(ps, dtype=float)
    floor = 1.0 / (2.0 * cfg.codim_pairs)
    ps_arr = np.maximum(ps_arr, floor)
    slope, _ = np.polyfit(np.log(deltas), np.log(ps_arr), 1)
    return float(slope)
