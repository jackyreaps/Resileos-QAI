"""Local compositional smoke — no live server required.

Demonstrates the shape of the claim using an in-memory store.
Replace with the live bench_compositional.py once the host is up.
"""
from __future__ import annotations


def test_simple_chain():
    store = {
        ("alice", "parent_of"): "bob",
        ("bob", "parent_of"): "carol",
    }

    def ask(s, r):
        return store.get((s, r))

    # 2-hop composition: grandparent
    parent = ask("alice", "parent_of")
    grand = ask(parent, "parent_of") if parent else None
    assert grand == "carol"

    # reverse: who is grandparent of carol
    # (simple reverse scan for demo)
    grandparent = None
    for (s, r), o in store.items():
        if r == "parent_of" and o == "bob":
            grandparent = s
    assert grandparent == "alice"


if __name__ == "__main__":
    test_simple_chain()
    print("local composition smoke passed")
