"""
Rheology coordinate interface for the RES-601 §7 metric bridge.

LOCKED. The bridge itself requires three items resolved (RES-601 §7):

    1. Explicit identification of the coordinates x
    2. Derivation of Re_ε(x) and G(x) from the rheology layer
    3. Positive-definiteness verification

This module defines the interface that item 1 must fill. Until a concrete
subclass implements `map_state_to_coordinates`, `BridgeMetricHead.forward`
cannot be unlocked, and any attempt to bypass this interface would be
invention rather than implementation.

See docs/600-qdter/non-dual-adaptation.md §7 for the source specification.
"""
from __future__ import annotations

import torch


class RheologyCoordinates:
    """
    Interface for the rheology layer state → coordinate map x.

    Subclasses must override:

        map_state_to_coordinates(state) -> torch.Tensor   [B, T, D]

    The output tensor is the coordinate x on which the RES-601 §7 metric
    is defined. The metric bridge cannot be instantiated without a concrete
    subclass of this interface.
    """

    def __init__(self, hidden_dim: int) -> None:
        self.hidden_dim = hidden_dim

    def map_state_to_coordinates(self, state: torch.Tensor) -> torch.Tensor:
        raise NotImplementedError(
            "RheologyCoordinates.map_state_to_coordinates is not implemented. "
            "Requires: explicit identification of the coordinates x from the "
            "rheology layer. See RES-601 §7 item 1. Without this map, "
            "BridgeMetricHead remains locked."
        )

    def re_epsilon(self, coords: torch.Tensor) -> torch.Tensor:
        """
        Re_ε(x) as a function of coordinates. Requires the local velocity
        scale |u(x)| and length/viscosity scales, not just the global locks
        (T_=1/3584, ε=1/64, z_x=4). See RES-601 §7 item 2.
        """
        raise NotImplementedError(
            "RheologyCoordinates.re_epsilon is not implemented. Requires: "
            "derivation of Re_ε(x) from the rheology layer, including the "
            "local velocity scale. Global Route A numbers define the tick "
            "and lock values but not the spatial field. See RES-601 §7 item 2."
        )

    def g_field(self, state: torch.Tensor) -> torch.Tensor:
        """
        G(x) as a function of state. Requires: identification of G with a
        specific monitor (scar energy |Λ|, residual flux F_res, or ΔS) or
        an explicit endocrinal composition. See RES-601 §7 item 2.
        """
        raise NotImplementedError(
            "RheologyCoordinates.g_field is not implemented. Requires: "
            "identification of G with a specific monitor or endocrinal "
            "composition, and derivation of (Ψ_B − Ψ_A). See RES-601 §7 "
            "item 2."
        )

    def M_E(self, state: torch.Tensor) -> torch.Tensor:
        """
        Endocrinal matrix M_E. Axiom C in RES-600 defines M_E as a scalar
        field G·Ψ_B/(Ψ_B − Ψ_A). If a matrix-valued M_E is required, its
        shape and source must be documented explicitly.
        """
        raise NotImplementedError(
            "RheologyCoordinates.M_E is not implemented. Axiom C in RES-600 "
            "defines M_E as a scalar field. If a matrix-valued M_E is "
            "required, its shape and derivation must be documented."
        )
