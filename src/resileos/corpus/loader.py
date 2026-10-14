"""
Corpus sources for pipeline scale tests.

Priority order:
    1. Koine Greek New Testament (default for the pipeline runner)
    2. Project Gutenberg via HuggingFace datasets
    3. Local plain-text file
    4. Synthetic deterministic text

Network sources are cached under CACHE_DIR_DEFAULT so runs are
reproducible. If a network source is unavailable, load_corpus falls
back to the bundled Greek excerpt.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

import numpy as np


CACHE_DIR_DEFAULT = Path(
    os.environ.get("RESILEOS_CACHE", Path.home() / ".cache" / "resileos")
) / "corpus"


# ── bundled fallback ────────────────────────────────────────────────────
# Opening of the Gospel of John in Koine Greek (SBLGNT-style).
# Used when a network source is unavailable so the pipeline runner
# always has real Greek to work with.
_BUNDLED_GREEK_JOHN_1 = (
    "Ἐν ἀρχῇ ἦν ὁ λόγος, καὶ ὁ λόγος ἦν πρὸς τὸν θεόν, "
    "καὶ θεὸς ἦν ὁ λόγος. οὗτος ἦν ἐν ἀρχῇ πρὸς τὸν θεόν. "
    "πάντα δι' αὐτοῦ ἐγένετο, καὶ χωρὶς αὐτοῦ ἐγένετο οὐδὲ ἕν. "
    "ὃ γέγονεν ἐν αὐτῷ ζωὴ ἦν, καὶ ἡ ζωὴ ἦν τὸ φῶς τῶν ἀνθρώπων· "
    "καὶ τὸ φῶς ἐν τῇ σκοτίᾳ φαίνει, καὶ ἡ σκοτία αὐτὸ οὐ κατέλαβεν. "
    "Ἐγένετο ἄνθρωπος ἀπεσταλμένος παρὰ θεοῦ, ὄνομα αὐτῷ Ἰωάννης· "
    "οὗτος ἦλθεν εἰς μαρτυρίαν ἵνα μαρτυρήσῃ περὶ τοῦ φωτός, "
    "ἵνα πάντες πιστεύσωσιν δι' αὐτοῦ. οὐκ ἦν ἐκεῖνος τὸ φῶς, "
    "ἀλλ' ἵνα μαρτυρήσῃ περὶ τοῦ φωτός. Ἦν τὸ φῶς τὸ ἀληθινόν, "
    "ὃ φωτίζει πάντα ἄνθρωπον, ἐρχόμενον εἰς τὸν κόσμον. "
    "ἐν τῷ κόσμῳ ἦν, καὶ ὁ κόσμος δι' αὐτοῦ ἐγένετο, "
    "καὶ ὁ κόσμος αὐτὸν οὐκ ἔγνω. εἰς τὰ ἴδια ἦλθεν, "
    "καὶ οἱ ἴδιοι αὐτὸν οὐ παρέλαβον. ὅσοι δὲ ἔλαβον αὐτόν, "
    "ἔδωκεν αὐτοῖς ἐξουσίαν τέκνα θεοῦ γενέσθαι, "
    "τοῖς πιστεύουσιν εἰς τὸ ὄνομα αὐτοῦ, οἳ οὐκ ἐξ αἱμάτων "
    "οὐδὲ ἐκ θελήματος σαρκὸς οὐδὲ ἐκ θελήματος ἀνδρὸς "
    "ἀλλ' ἐκ θεοῦ ἐγεννήθησαν. Καὶ ὁ λόγος σὰρξ ἐγένετο "
    "καὶ ἐσκήνωσεν ἐν ἡμῖν, καὶ ἐθεασάμεθα τὴν δόξαν αὐτοῦ, "
    "δόξαν ὡς μονογενοῦς παρὰ πατρός, πλήρης χάριτος καὶ ἀληθείας."
)


def _cache_key(name: str, variant: str = "") -> str:
    h = hashlib.sha256(f"{name}|{variant}".encode("utf-8")).hexdigest()[:16]
    return f"{name}-{h}.txt"


def _read_cache(path: Path) -> Optional[str]:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def _write_cache(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ── sources ─────────────────────────────────────────────────────────────
class CorpusSource(Protocol):
    name: str
    def fetch(self, cache_dir: Path) -> str: ...


@dataclass
class KoineGreekSource:
    """
    Koine Greek New Testament.

    Tries HuggingFace datasets first (a public SBLGNT-shaped corpus),
    falls back to the bundled Gospel of John excerpt if unavailable.
    """
    name: str = "koine_greek_nt"
    hf_dataset: str = "scrollmapper/bible_datasets"
    hf_config: str = "greek_sblgnt"

    def fetch(self, cache_dir: Path) -> str:
        path = cache_dir / _cache_key(self.name, self.hf_config)
        cached = _read_cache(path)
        if cached is not None:
            return cached

        text = self._try_hf()
        if text is None:
            text = self._try_remote_url()
        if text is None:
            text = _BUNDLED_GREEK_JOHN_1

        _write_cache(path, text)
        return text

    def _try_hf(self) -> Optional[str]:
        try:
            from datasets import load_dataset  # type: ignore
        except ImportError:
            return None
        try:
            ds = load_dataset(self.hf_dataset, self.hf_config,
                              split="train")
            key = "text" if "text" in ds.column_names else ds.column_names[0]
            return "\n".join(str(row[key]) for row in ds)
        except Exception:
            return None

    def _try_remote_url(self) -> Optional[str]:
        try:
            import urllib.request
        except ImportError:
            return None
        # Public domain SBLGNT raw text; URL is stable but may move.
        url = ("https://raw.githubusercontent.com/"
               "eliranwong/OpenGNT/master/"
               "OpenGNT_full/OpenGNT_full.txt")
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception:
            return None


@dataclass
class GutenbergSource:
    """Project Gutenberg English corpus via HuggingFace datasets."""
    name: str = "gutenberg"
    hf_dataset: str = "incredible45/Gutenberg-BookCorpus-Cleaned-Data-English"
    index: int = 0

    def fetch(self, cache_dir: Path) -> str:
        path = cache_dir / _cache_key(self.name, str(self.index))
        cached = _read_cache(path)
        if cached is not None:
            return cached

        text = self._try_hf()
        if text is None:
            # Nothing to fall back to for English; the pipeline runner
            # should use KoineGreekSource as the default if this fails.
            raise RuntimeError(
                "Gutenberg source unavailable; install `datasets` or "
                "use KoineGreekSource / PlainTextSource")
        _write_cache(path, text)
        return text

    def _try_hf(self) -> Optional[str]:
        try:
            from datasets import load_dataset  # type: ignore
        except ImportError:
            return None
        try:
            ds = load_dataset(self.hf_dataset, split="train")
            row = ds[self.index]
            key = "context" if "context" in row else list(row.keys())[0]
            return str(row[key])
        except Exception:
            return None


@dataclass
class PlainTextSource:
    """Load a local UTF-8 text file."""
    path: Path
    name: str = "plain_text"

    def fetch(self, cache_dir: Path) -> str:
        return Path(self.path).read_text(encoding="utf-8")


@dataclass
class SyntheticSource:
    """
    Deterministic synthetic text over a small alphabet.

    Useful when network access is unavailable and you want a controlled
    sequence for reproducibility. Character distribution is uniform.
    """
    alphabet: str = "abcdefghijklmnopqrstuvwxyz "
    length: int = 10000
    seed: int = 0
    name: str = "synthetic"

    def fetch(self, cache_dir: Path) -> str:
        rng = np.random.default_rng(self.seed)
        chars = np.array(list(self.alphabet))
        idx = rng.integers(0, len(chars), size=self.length)
        return "".join(chars[idx].tolist())


# ── top-level loader ────────────────────────────────────────────────────
def load_corpus(source: CorpusSource | None = None,
                target_chars: Optional[int] = None,
                cache_dir: Optional[Path] = None,
                ) -> str:
    """
    Fetch and optionally truncate a corpus.

    Default source is KoineGreekSource. Truncation is deterministic:
    the first `target_chars` characters, after normalization of line
    endings.
    """
    if source is None:
        source = KoineGreekSource()
    cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR_DEFAULT

    text = source.fetch(cache_dir)
    # Normalize line endings and strip trailing whitespace for
    # deterministic truncation.
    text = text.replace("\r\n", "\n").replace("\r", "\n").rstrip()

    if target_chars is not None and len(text) > target_chars:
        text = text[:target_chars]
    return text


__all__ = [
    "CorpusSource",
    "KoineGreekSource", "GutenbergSource",
    "PlainTextSource", "SyntheticSource",
    "load_corpus",
    "CACHE_DIR_DEFAULT",
]
