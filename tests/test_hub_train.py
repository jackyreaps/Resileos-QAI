from resileos.answer.hub_train import (
    DEFAULT_WORKSPACE_FACTS,
    open_hub_workbench,
    seed_default_hubs,
    train_hub,
)


def test_seed_workspace_hub():
    wb = open_hub_workbench(seed=False)
    n = seed_default_hubs(wb)
    assert n >= len(DEFAULT_WORKSPACE_FACTS)
    rows = wb.ask_rows("world:materials", "status")
    assert "workspace" in rows


def test_hub_prefix_required():
    wb = open_hub_workbench(seed=False)
    try:
        train_hub(wb, [("Zeus", "domain", "sky")])
        assert False, "should require prefix"
    except ValueError:
        pass
