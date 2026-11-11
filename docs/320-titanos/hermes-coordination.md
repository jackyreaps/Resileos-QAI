# Hermes coordination

Clotho, Lachesis, Atropos, and Harmonia sit under Hermes (`src/resileos/kin/moirai.py`). They are not a separate Kin.

- Clotho registers a process group or a cancel callback for work Hermes owns.
- Lachesis expands another legion or a deeper cycle only when expected gain exceeds budget cost. It tracks active control packets and residual hashes.
- Atropos, on stop, sends the session interrupt and terminates the owned process group. `stop_requested` and `fully_stopped` are different. Hades checkpoints a stopped owner only after the group is fully stopped and residual consistency holds.
- Harmonia shares a residual step when residual-hash or control-packet prefix overlap is at least 0.8. A shared step is accepted only after residual consistency and `verify_on_stop`.

A pure-Python legion uses the cancel registry when it has no process group. A stopped child and grandchild must not write after the cut.
