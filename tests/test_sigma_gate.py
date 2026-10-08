"""RES-303 gate triggers and priority."""
from resileos.sigma import SigmaGate, SigmaAction


def test_no_fire_when_nominal():
    g = SigmaGate(E_sigma=1.0, k=3)
    assert g.evaluate(scar_energy=0.1, mu=0, volume_ok=True) == SigmaAction.NONE


def test_scar_saturation_fires_cleanup():
    g = SigmaGate(E_sigma=1.0, k=3)
    assert g.evaluate(scar_energy=1.5, mu=0, volume_ok=True) == SigmaAction.CLEANUP


def test_volume_streak_fires():
    g = SigmaGate(E_sigma=1.0, k=3)
    for _ in range(4):
        a = g.evaluate(scar_energy=0.1, mu=0, volume_ok=False)
    assert a == SigmaAction.CLEANUP
