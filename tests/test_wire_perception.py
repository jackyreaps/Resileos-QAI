# ──────────────────────────────────────────────────────────────────────
# 2026-11-09 additions — separated cycle via learn_fn
# Append these to the end of the existing test_wire_perception.py.
# ──────────────────────────────────────────────────────────────────────


def test_learn_fn_path_returns_harness_fields():
    """New separated path returns applied/verification/verdicts."""
    import warnings
    psyche = Psyche()
    learned = []
    def learn_fn(s, r, o):
        learned.append((s, r, o))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = wire_perception(psyche, _perceived(), learn_fn=learn_fn)
    assert "state" in out
    assert "rows" in out
    assert "judgment" in out
    assert "applied" in out
    assert "verification" in out
    assert "verdicts" in out


def test_learn_fn_path_captures_claims_not_direct_writes():
    """learn_fn is called only by apply(), never during propose."""
    import warnings
    psyche = Psyche()
    calls = []
    def learn_fn(s, r, o):
        calls.append((s, r, o))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = wire_perception(psyche, _perceived(), learn_fn=learn_fn)
    if out["applied"]:
        assert len(calls) >= 1
    else:
        assert calls == []


def test_learn_fn_path_includes_athena_in_verdicts():
    """The separated path adds verifiers + athena reviewers."""
    import warnings
    psyche = Psyche()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = wire_perception(
            psyche, _perceived(), learn_fn=lambda s, r, o: None
        )
    reviewers = [v["reviewer"] for v in out.get("verdicts", [])]
    assert "verifiers" in reviewers
    assert "athena" in reviewers


def test_learn_fn_path_unverified_by_default():
    """Without attached probe evidence, the cycle reports unverified."""
    import warnings
    psyche = Psyche()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = wire_perception(
            psyche, _perceived(), learn_fn=lambda s, r, o: None
        )
    v = out.get("verification", {})
    # The strict gate requires evidence on a mutation/cycle action_type.
    # A fresh perception has no probe evidence attached yet.
    assert v.get("verified") is False
    assert "evidence" in v.get("reason", "").lower() or \
           "apollo" in v.get("reason", "").lower()


def test_legacy_eat_fn_still_works():
    """Legacy path continues to work but returns only the old shape."""
    import warnings
    psyche = Psyche()
    eaten = []
    def eat_fn(claim):
        eaten.append(claim)
        return type("D", (), {"accepted": True})()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        out = wire_perception(psyche, _perceived(), eat_fn=eat_fn)
    assert "state" in out
    assert "rows" in out
    assert "judgment" in out
    # Legacy path does not return harness fields
    assert "applied" not in out
    assert "verification" not in out
