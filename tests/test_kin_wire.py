"""Wiring + mouth policy unit tests (no FastAPI app required)."""
from __future__ import annotations

from resileos.kin.bundle import build_kin_bundle
from resileos.kin.mouth_policy import should_render_prose
from resileos.kin.wiring import get_kin_bundle, mouth_allowed_from_last_cycle


def test_mouth_default_without_cycle():
    # reset bundle policy by building fresh module state is process-global;
    # ensure cycle clears: call with no prior policy
    b = get_kin_bundle()
    b.last_policy = None
    assert should_render_prose(False) is False
    assert should_render_prose(True, default_if_no_policy=True) is True
    assert should_render_prose(True, default_if_no_policy=False) is False


def test_mouth_follows_metis_after_cycle():
    b = get_kin_bundle()
    # low hits → allow_mouth False
    b.cycle(
        metrics={
            "hits": 1,
            "misses": 20,
            "teaches": 0,
            "sessions": 5,
            "hit_rate": 0.05,
        },
        agency_group=None,
        apply_policy=False,
    )
    assert b.last_policy is not None
    assert b.last_policy.allow_mouth is False
    assert should_render_prose(True, default_if_no_policy=True) is False
    # high hits → allow_mouth True
    b.cycle(
        metrics={
            "hits": 20,
            "misses": 1,
            "teaches": 5,
            "sessions": 3,
            "hit_rate": 0.95,
        },
        agency_group=None,
        apply_policy=False,
    )
    assert b.last_policy.allow_mouth is True
    assert mouth_allowed_from_last_cycle() is True
    assert should_render_prose(True) is True


def test_studio_eat_helper():
    from resileos.kin.studio_eat import post_eat

    calls = []

    def api_post(path, body):
        calls.append((path, body))
        return 200, {"action": "accept"}

    code, body = post_eat(api_post, "Zeus domain sky", user_id="u1", preview=True)
    assert code == 200
    assert calls[0][0] == "/eat/preview"
    assert calls[0][1]["user_id"] == "u1"
