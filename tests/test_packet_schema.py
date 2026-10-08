"""RES-201 schema + RES-202 canonicalization."""
import numpy as np
import pytest

from resileos.packet import Packet, canonical_json, packet_hash, encode_exponent


def make_packet():
    r, m, n = 4, 8, 8
    return Packet(
        version="1.0.0",
        Ub=np.sign(np.random.default_rng(0).standard_normal((m, r))),
        Vb=np.sign(np.random.default_rng(1).standard_normal((n, r))),
        row_s_k=np.zeros(m, dtype=np.int16),
        col_s_k=np.zeros(n, dtype=np.int16),
        lat_s_k=np.zeros(r, dtype=np.int16),
        Lambda=np.zeros((r, r), dtype=np.float32),
        mu=0, DeltaS=0.5, F_res=0.0,
        volume=1.0, volume_ok=True,
        rank=1, schedule_index=0,
    )


def test_hash_is_deterministic():
    p = make_packet()
    assert packet_hash(p) == packet_hash(p)
    assert len(packet_hash(p)) == 64


def test_canonical_json_excludes_hash():
    p = make_packet()
    s = canonical_json(p)
    assert "packet_hash" not in s


def test_exponent_clamp():
    assert encode_exponent(100.0) == 16
    assert encode_exponent(-100.0) == -16
    assert encode_exponent(0.0) == 0
