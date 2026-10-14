"""Deterministic character-level tokenizer. No external tokenizer library.

Vocab is the sorted set of codepoints in the fitted text, prefixed by special
tokens. Indices are stable across machines and Python versions.

Greek support:
    strip_diacritics=False keeps breathings, accents, subscripts (vocab ~200-300 for Koine Greek)
    strip_diacritics=True NFD-normalizes and drops combining marks (vocab ~30-50 for Koine Greek)

Round-trip is exact in either mode: decode(encode(t)) == t.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Iterable

import numpy as np

SPECIAL_TOKENS = ("<pad>", "<unk>", "<bos>", "<eos>")
PAD, UNK, BOS, EOS = 0, 1, 2, 3
_NUM_SPECIAL = 4


class CharTokenizer:
    """Character-level tokenizer with deterministic vocab ordering.

    Fit once on a training text; encode/decode unlimited times.
    """

    def __init__(self, strip_diacritics: bool = False) -> None:
        self.strip_diacritics = bool(strip_diacritics)
        self._chars: list[str] = []          # sorted codepoints, index
        self._char_to_id: dict[str, int] = {}
        self._fitted = False

    # ── normalization ────────────────────────────────────────────────
    def _norm(self, text: str) -> str:
        if not self.strip_diacritics:
            return text
        decomposed = unicodedata.normalize("NFD", text)
        return "".join(
            c for c in decomposed if unicodedata.category(c) != "Mn"
        )

    # ── fitting ─────────────────────────────────────────────────────
    def fit(self, text: str) -> "CharTokenizer":
        normalized = self._norm(text)
        # Sorted unique codepoints.
        self._chars = sorted(set(normalized))
        self._char_to_id = {c: i + _NUM_SPECIAL for i, c in enumerate(self._chars)}
        self._fitted = True
        return self

    # ── properties ──────────────────────────────────────────────────
    @property
    def vocab_size(self) -> int:
        return _NUM_SPECIAL + len(self._chars)

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def id_to_char(self, token_id: int) -> str:
        if token_id < _NUM_SPECIAL:
            return SPECIAL_TOKENS[token_id]
        idx = token_id - _NUM_SPECIAL
        if not (0 <= idx < len(self._chars)):
            raise IndexError(f"token_id {token_id} out of range")
        return self._chars[idx]

    # ── encode / decode ─────────────────────────────────────────────
    def encode(self, text: str, add_bos: bool = False, add_eos: bool = False) -> list[int]:
        if not self._fitted:
            raise RuntimeError("tokenizer not fitted; call fit() first")
        normalized = self._norm(text)
        out: list[int] = []
        if add_bos:
            out.append(BOS)
        for c in normalized:
            out.append(self._char_to_id.get(c, UNK))
        if add_eos:
            out.append(EOS)
        return out

    def decode(self, ids: Iterable[int], skip_special: bool = True) -> str:
        out: list[str] = []
        for i in ids:
            i = int(i)
            if i < _NUM_SPECIAL:
                if not skip_special:
                    out.append(SPECIAL_TOKENS[i])
                continue
            idx = i - _NUM_SPECIAL
            if 0 <= idx < len(self._chars):
                out.append(self._chars[idx])
        return "".join(out)

    # ── batch helpers ────────────────────────────────────────────────
    def encode_batch(self, texts: Iterable[str]) -> list[list[int]]:
        return [self.encode(t) for t in texts]

    def decode_batch(self, batch: Iterable[Iterable[int]], skip_special: bool = True) -> list[str]:
        return [self.decode(ids, skip_special=skip_special) for ids in batch]
