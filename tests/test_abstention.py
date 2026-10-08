"""RES-302 state machine + RES-303 precedence."""
from resileos.abstention import (
    AbstentionInputs, AbstentionThresholds, route_signals,
    CONTINUE, REPULSE, CLEANUP, ABSTAIN,
)

TH = AbstentionThresholds(E_sat=1.0, tau_sat=0.9, tau_low=0.1)


def test_volume_failure_abstains():
    assert route_signals(AbstentionInputs(0.5, 0, 0.0, False), TH) == ABSTAIN


def test_sigma1_wins():
    assert route_signals(AbstentionInputs(0.5, 0, 0.0, True), TH, "CLEANUP") == CLEANUP


def test_high_sharpness_cleans():
    assert route_signals(AbstentionInputs(0.95, 0, 0.0, True), TH) == CLEANUP


def test_parity_repels():
    assert route_signals(AbstentionInputs(0.5, 1, 0.0, True), TH) == REPULSE


def test_low_sharpness_abstains():
    assert route_signals(AbstentionInputs(0.05, 0, 0.0, True), TH) == ABSTAIN


def test_default_continues():
    assert route_signals(AbstentionInputs(0.5, 0, 0.0, True), TH) == CONTINUE
