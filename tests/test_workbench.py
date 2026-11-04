"""Advanced-project workbench mouth."""
from resileos.answer.workbench import open_workbench, parse_fact_line


def test_parse_variants():
    assert parse_fact_line("a, b, c") == ("a", "b", "c")
    assert parse_fact_line("(a, b, c)") == ("a", "b", "c")
    assert parse_fact_line("a -> c : b") == ("a", "b", "c")
    assert parse_fact_line("# comment") is None


def test_workbench_ingest_and_answer():
    wb = open_workbench(
        backend="structured",
        seed_facts=[("eps", "equals", "1/64"), ("residual_floor", "minimum", "5")],
    )
    r = wb.answer("eps", "equals")
    assert not r.empty
    assert "1/64" in r.rows
    assert "1/64" in r.answer_text
    empty = wb.answer("nope", "missing")
    assert empty.empty


def test_ingest_lines():
    wb = open_workbench(backend="structured")
    n = wb.ingest_lines(["F5, kernel_dim, 5", "# x", "Bridge_B1 -> conditional : status"])
    assert n == 2
    assert "5" in wb.ask_rows("F5", "kernel_dim")
