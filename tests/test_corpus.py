"""Tests for corpus loading and tokenization."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.corpus import (
    CharTokenizer, SPECIAL_TOKENS, PAD, UNK, BOS, EOS,
    load_corpus,
    KoineGreekSource, GutenbergSource, PlainTextSource, SyntheticSource,
)


GREEK_SAMPLE = "Ἐν ἀρχῇ ἦν ὁ λόγος, καὶ ὁ λόγος ἦν πρὸς τὸν θεόν."
ASCII_SAMPLE = "the quick brown fox jumps over the lazy dog"


# ── tokenizer fit / round-trip ──────────────────────────────────────────
def test_tokenizer_fit_produces_vocab():
    tok = CharTokenizer().fit(ASCII_SAMPLE)
    assert tok.is_fitted
    assert tok.vocab_size == 4 + len(set(ASCII_SAMPLE))


def test_tokenizer_ascii_roundtrip():
    tok = CharTokenizer().fit(ASCII_SAMPLE)
    ids = tok.encode(ASCII_SAMPLE)
    assert tok.decode(ids) == ASCII_SAMPLE


def test_tokenizer_greek_roundtrip_with_diacritics():
    tok = CharTokenizer(strip_diacritics=False).fit(GREEK_SAMPLE)
    ids = tok.encode(GREEK_SAMPLE)
    assert tok.decode(ids) == GREEK_SAMPLE


def test_tokenizer_greek_roundtrip_strip_diacritics():
    tok = CharTokenizer(strip_diacritics=True).fit(GREEK_SAMPLE)
    ids = tok.encode(GREEK_SAMPLE)
    decoded = tok.decode(ids)
    # Stripping removes combining marks but preserves base letters.
    assert "λόγος" in decoded or "λογος" in decoded
    assert len(ids) <= len(GREEK_SAMPLE)


def test_strip_diacritics_reduces_vocab():
    a = CharTokenizer(strip_diacritics=False).fit(GREEK_SAMPLE)
    b = CharTokenizer(strip_diacritics=True).fit(GREEK_SAMPLE)
    assert b.vocab_size < a.vocab_size


def test_unknown_char_maps_to_unk():
    tok = CharTokenizer().fit("abc")
    ids = tok.encode("abcdef")
    assert UNK in ids
    # Decoded text drops UNK when skip_special=True
    assert "d" not in tok.decode(ids)
    assert "e" not in tok.decode(ids)


def test_bos_eos_added_when_requested():
    tok = CharTokenizer().fit("abc")
    ids = tok.encode("ab", add_bos=True, add_eos=True)
    assert ids[0] == BOS
    assert ids[-1] == EOS


def test_bos_eos_skipped_in_decode():
    tok = CharTokenizer().fit("abc")
    ids = [BOS, 4, 5, EOS]  # 'a', 'b' assumed at 4, 5
    assert tok.decode(ids) == "ab"


def test_bos_eos_shown_in_decode_when_requested():
    tok = CharTokenizer().fit("abc")
    ids = [BOS, EOS]
    out = tok.decode(ids, skip_special=False)
    assert out == "<bos><eos>"


# ── tokenizer determinism ───────────────────────────────────────────────
def test_tokenizer_deterministic():
    a = CharTokenizer().fit(ASCII_SAMPLE)
    b = CharTokenizer().fit(ASCII_SAMPLE)
    assert a._chars == b._chars
    assert a.encode(ASCII_SAMPLE) == b.encode(ASCII_SAMPLE)


def test_tokenizer_save_load_roundtrip(tmp_path):
    a = CharTokenizer(strip_diacritics=True).fit(GREEK_SAMPLE)
    path = tmp_path / "tok.json"
    a.save(path)
    b = CharTokenizer.load(path)
    assert b.vocab_size == a.vocab_size
    assert b._chars == a._chars
    assert b.encode(GREEK_SAMPLE) == a.encode(GREEK_SAMPLE)


def test_tokenizer_encode_before_fit_raises():
    tok = CharTokenizer()
    with pytest.raises(RuntimeError, match="not fitted"):
        tok.encode("abc")


def test_tokenizer_load_rejects_mismatched_specials(tmp_path):
    path = tmp_path / "tok.json"
    path.write_text('{"strip_diacritics": false, "chars": ["a"], '
                    '"special_tokens": ["<x>"]}')
    with pytest.raises(ValueError, match="specials"):
        CharTokenizer.load(path)


# ── corpus loader ───────────────────────────────────────────────────────
def test_load_corpus_plain_text(tmp_path):
    p = tmp_path / "sample.txt"
    p.write_text("hello world\n")
    text = load_corpus(PlainTextSource(path=p), cache_dir=tmp_path)
    assert text == "hello world"


def test_load_corpus_synthetic_deterministic():
    src = SyntheticSource(alphabet="abc ", length=200, seed=1)
    a = load_corpus(src, cache_dir=Path("/tmp"))
    b = load_corpus(src, cache_dir=Path("/tmp"))
    assert a == b
    assert len(a) == 200
    assert set(a) <= set("abc ")


def test_load_corpus_synthetic_seed_sensitive():
    a = load_corpus(SyntheticSource(alphabet="abc", length=100, seed=1),
                    cache_dir=Path("/tmp"))
    b = load_corpus(SyntheticSource(alphabet="abc", length=100, seed=2),
                    cache_dir=Path("/tmp"))
    assert a != b


def test_load_corpus_truncation():
    src = SyntheticSource(alphabet="a", length=1000, seed=0)
    text = load_corpus(src, target_chars=100, cache_dir=Path("/tmp"))
    assert len(text) == 100


def test_load_corpus_koine_fallback(tmp_path):
    """When HF and remote are unavailable, the bundled Greek is used."""
    src = KoineGreekSource()
    text = load_corpus(src, target_chars=200, cache_dir=tmp_path)
    assert len(text) > 0
    # Greek codepoints present
    assert any("\u0370" <= c <= "\u03ff" or
               "\u1f00" <= c <= "\u1fff" for c in text)


def test_koine_source_caches(tmp_path):
    src = KoineGreekSource()
    a = src.fetch(tmp_path)
    files = list(tmp_path.glob("koine_greek_nt-*.txt"))
    assert len(files) == 1
    b = src.fetch(tmp_path)
    assert a == b


def test_gutenberg_source_raises_without_datasets(tmp_path):
    """If `datasets` is not installed, GutenbergSource raises clearly."""
    try:
        import datasets  # noqa: F401
        pytest.skip("datasets is installed; skipping fallback test")
    except ImportError:
        pass
    with pytest.raises(RuntimeError, match="Gutenberg source unavailable"):
        GutenbergSource().fetch(tmp_path)


# ── tokenizer + corpus integration ──────────────────────────────────────
def test_tokenizer_fits_on_koine_fallback(tmp_path):
    src = KoineGreekSource()
    text = load_corpus(src, target_chars=500, cache_dir=tmp_path)
    tok = CharTokenizer(strip_diacritics=False).fit(text)
    ids = tok.encode(text)
    assert tok.decode(ids) == text
    assert tok.vocab_size > 30
