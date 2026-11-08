"""Tests for the credit ledger."""
from resileos.ui.credits import CreditLedger, earn_for_work, spend_for_use


def test_earn_then_spend():
    led = CreditLedger()
    assert led.earn("ada", 5, reason="work")["ok"]
    assert led.balance("ada") == 5
    assert led.spend("ada", 2, reason="use")["ok"]
    assert led.balance("ada") == 3


def test_spend_blocks_when_empty():
    led = CreditLedger()
    out = led.spend("ada", 1)
    assert out["ok"] is False


def test_no_transfer():
    led = CreditLedger()
    led.earn("ada", 5)
    out = led.transfer("ada", "bea", 1)
    assert out["ok"] is False
    assert led.balance("ada") == 5
    earn_for_work("bea", "fix gate", amount=2)
    out = spend_for_use("bea", 1, what="query")
    assert out["ok"] is True
