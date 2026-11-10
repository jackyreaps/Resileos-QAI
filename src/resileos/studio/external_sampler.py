"""External samplers. Off unless RESILEOS_EXTERNAL_SAMPLER is set.

The only object that crosses this boundary is a studio-codec/1 packet.
A sampler does not call learn and does not touch the scar matrix.
``fake`` builds a packet locally. ``minimax_api`` is a stub: it stays off
unless that name is set and MINIMAX_API_KEY is set, and a returned image
is re-encoded by the residual codec before anything else sees it.
This module does not download weights.
"""
from __future__ import annotations

import base64
import io
import json
import os
import urllib.request
from typing import Any, Callable, Mapping, Protocol

import numpy as np

from studio.codec import logical_bits

Post = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


class SamplerOff(RuntimeError):
    """propose() was called while the external sampler is disabled."""


class ExternalSampler(Protocol):
    """Propose a residual packet, or refuse because the sampler is off."""

    name: str
    enabled: bool

    def propose(self, *, condition: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return one studio-codec/1 packet with per-component scales."""


class DisabledExternalSampler:
    name = "off"
    enabled = False

    def __init__(self, reason: str = "RESILEOS_EXTERNAL_SAMPLER is unset") -> None:
        self.reason = reason

    def propose(self, *, condition: dict[str, Any] | None = None) -> dict[str, Any]:
        del condition
        raise SamplerOff(self.reason)

    def status(self) -> dict[str, Any]:
        return {"enabled": False, "name": self.name, "reason": self.reason}


class FakeExternalSampler:
    """In-repo stand-in. Deterministic ±1 factors, no weights, no network."""

    name = "fake"
    enabled = True
    reason = "in-repo fake sampler; not a generative model"

    def propose(self, *, condition: dict[str, Any] | None = None) -> dict[str, Any]:
        seed = 0
        if condition and condition.get("seed") is not None:
            seed = int(condition["seed"])
        rng = np.random.default_rng(seed)
        rank = 2
        m = n = 8
        layers = []
        for _ in range(1):
            ub = np.sign(rng.standard_normal((m, rank))).astype(np.float32)
            vb = np.sign(rng.standard_normal((rank, n))).astype(np.float32)
            ub[ub == 0] = 1.0
            vb[vb == 0] = 1.0
            scales = [float(x) for x in rng.normal(0.0, 0.05, size=rank)]
            layers.append({"Ub": ub, "Vb": vb, "scale": scales})
        return {
            "version": "studio-codec/1",
            "shape": [m, n],
            "rank": rank,
            "n_layers": 1,
            "scale_mode": "component",
            "basis": "external-fake",
            "layers": layers,
            "logical_bits": logical_bits(m, n, rank, 1, "component"),
        }

    def status(self) -> dict[str, Any]:
        return {"enabled": True, "name": self.name, "reason": self.reason}


class MiniMaxApiSampler:
    """Hosted MiniMax-H3-Image stub. Pixels are re-encoded into a packet.

    Off unless ``RESILEOS_EXTERNAL_SAMPLER=minimax_api`` and
    ``MINIMAX_API_KEY`` are both set. ``post`` is the HTTP call. Tests pass
    a fake. The default posts with urllib and is not used by the tests.
    """

    name = "minimax_api"
    enabled = True

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "",
        post: Post | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._post = post
        self.reason = (
            "minimax_api stub; returned images are re-encoded into a residual "
            "packet and registered only as candidates"
        )

    def propose(self, *, condition: dict[str, Any] | None = None) -> dict[str, Any]:
        prompt = str((condition or {}).get("prompt") or "").strip()
        if not prompt:
            raise SamplerOff("minimax_api needs a prompt; no request was sent")
        if self._post is None and not self._base_url:
            raise SamplerOff("MINIMAX_API_BASE is unset; no request was sent")
        payload = {
            "model": "MiniMax-H3-Image",
            "prompt": prompt,
            "n": 1,
            "response_format": "b64_json",
            "size": str((condition or {}).get("size") or "1024x1024"),
        }
        url = f"{self._base_url}/v1/images/generations"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        post = self._post or _http_post
        body = post(url, headers, payload)
        image = _image_from_response(body)
        from resileos.studio.codecs import open_codec

        codec = open_codec("pca_component")
        packet = codec.encode_matrix(codec.project(image))
        packet["basis"] = "minimax_api-reencoded"
        return packet

    def status(self) -> dict[str, Any]:
        return {"enabled": True, "name": self.name, "reason": self.reason}


def _http_post(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    """Real POST. Tests never call this; they pass their own ``post``."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _image_from_response(body: dict[str, Any]) -> np.ndarray:
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise SamplerOff("minimax_api response had no image; nothing was registered")
    item = data[0]
    if item.get("error"):
        raise SamplerOff("minimax_api reported an image error; nothing was registered")
    encoded = item.get("b64_json")
    if not isinstance(encoded, str) or not encoded:
        raise SamplerOff("minimax_api stub accepts b64_json only; a url was not fetched")
    from PIL import Image

    raw = base64.b64decode(encoded)
    return np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"))


def resolve_external_sampler(
    env: Mapping[str, str] | None = None,
    *,
    post: Post | None = None,
) -> DisabledExternalSampler | FakeExternalSampler | MiniMaxApiSampler:
    """Off by default. ``fake`` is local. ``minimax_api`` also needs an API key."""
    source = os.environ if env is None else env
    raw = str(source.get("RESILEOS_EXTERNAL_SAMPLER", "")).strip().lower()
    if raw in ("", "off", "none", "disabled"):
        return DisabledExternalSampler()
    if raw == "fake":
        return FakeExternalSampler()
    if raw == "minimax_api":
        key = str(source.get("MINIMAX_API_KEY", "")).strip()
        if not key:
            return DisabledExternalSampler(
                reason=(
                    "RESILEOS_EXTERNAL_SAMPLER=minimax_api but MINIMAX_API_KEY "
                    "is unset; the sampler stays off and no request is sent"
                )
            )
        return MiniMaxApiSampler(
            api_key=key,
            base_url=str(source.get("MINIMAX_API_BASE", "")).strip(),
            post=post,
        )
    return DisabledExternalSampler(
        reason=f"unknown external sampler {raw!r} was not loaded; weights are not vendored"
    )
