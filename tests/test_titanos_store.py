"""Tests for DiskBandStore (RES-320)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.titanos import DiskBandStore


def test_store_rejects_small_dimension(tmp_path):
    with pytest.raises(ValueError, match="dimension must be"):
        DiskBandStore(tmp_path, dimension=4)


def test_store_creates_data_dir(tmp_path):
    d = tmp_path / "nested" / "dir"
    with DiskBandStore(d, 16):
        pass
    assert d.exists()


def test_band_view_writes_persist(tmp_path):
    with DiskBandStore(tmp_path, 8) as store:
        v = store.band_view("rel")
        v[:] = np.arange(8, dtype=np.int32)
        store.flush()
    with DiskBandStore(tmp_path, 8) as store2:
        v2 = store2.read_band("rel")
        assert np.array_equal(v2, np.arange(8, dtype=np.int32))


def test_band_view_inplace_accumulate(tmp_path):
    with DiskBandStore(tmp_path, 8) as store:
        v = store.band_view("rel")
        v += np.ones(8, dtype=np.int32)
        v += np.ones(8, dtype=np.int32)
        assert np.all(v == 2)


def test_append_and_iterate_facts(tmp_path):
    with DiskBandStore(tmp_path, 8) as store:
        store.append_fact(1, 2, 3)
        store.append_fact(4, 5, 6)
        store.flush()
    with DiskBandStore(tmp_path, 8) as store2:
        facts = list(store2.iter_facts())
        assert facts == [(1, 2, 3), (4, 5, 6)]


def test_append_facts_batch(tmp_path):
    with DiskBandStore(tmp_path, 8) as store:
        n = store.append_facts([(1, 2, 3), (4, 5, 6), (7, 8, 9)])
        assert n == 3
        assert store.fact_count() == 3


def test_fact_count_persists(tmp_path):
    with DiskBandStore(tmp_path, 8) as store:
        store.append_fact(1, 1, 1)
        store.flush()
    with DiskBandStore(tmp_path, 8) as store2:
        assert store2.fact_count() == 1


def test_metadata_dimension_mismatch_raises(tmp_path):
    with DiskBandStore(tmp_path, 8) as store:
        store.append_fact(1, 1, 1)
        store.flush()
    with pytest.raises(RuntimeError, match="dimension"):
        DiskBandStore(tmp_path, 16)


def test_read_only_rejects_writes(tmp_path):
    with DiskBandStore(tmp_path, 8) as store:
        store.band_view("rel")[:] = 1
        store.flush()
    with DiskBandStore(tmp_path, 8, read_only=True) as store2:
        with pytest.raises(PermissionError):
            store2.append_fact(1, 2, 3)


def test_relations_listing(tmp_path):
    with DiskBandStore(tmp_path, 8) as store:
        store.band_view("a")
        store.band_view("b")
        assert set(store.relations()) == {"a", "b"}


def test_write_band_rejects_wrong_shape(tmp_path):
    with DiskBandStore(tmp_path, 8) as store:
        with pytest.raises(ValueError, match="shape"):
            store.write_band("rel", np.zeros(4, dtype=np.int32))


def test_safe_name_handles_special_chars(tmp_path):
    with DiskBandStore(tmp_path, 8) as store:
        v = store.band_view("has/property")
        v[:] = 1
    files = list(tmp_path.glob("band_*.bin"))
    assert len(files) == 1


def test_rebuild_from_wal(tmp_path):
    with DiskBandStore(tmp_path, 8) as store:
        store.append_facts([(1, 1, 2), (2, 1, 3)])
        store.flush()
    ev = {
        1: np.ones(8, dtype=np.int32),
        2: np.array([1, -1] * 4, dtype=np.int32),
        3: np.array([-1, 1] * 4, dtype=np.int32),
    }
    rv = {1: np.array([1, 1, -1, -1, 1, 1, -1, -1], dtype=np.int32)}
    with DiskBandStore(tmp_path, 8) as store2:
        n = store2.rebuild_from_wal(ev, rv, {1: "rel"})
        assert n == 2
        band = store2.read_band("rel")
        expected = (ev[1] * rv[1] * ev[2]) + (ev[2] * rv[1] * ev[3])
        assert np.array_equal(band, expected.astype(np.int32))
