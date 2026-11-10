"""Round trip and toy sampling for the Studio residual-codec mode.

Numbers for a live image are computed here. The toy-prior caption is read
from the digits study file, not recomputed and not invented.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if _SCRIPTS.is_dir() and str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from resileos.studio.candidates import register_candidate
from resileos.studio.codecs import PcaComponentCodec, open_codec, packet_summary
from resileos.studio.external_sampler import resolve_external_sampler
from resileos.studio.gate import gate_studio_packet
from studio.codec import decode
from studio.prior import code_vector, decode_code, fit_class_conditional, sample_code

_STUDY = _SCRIPTS / "studio" / "outputs" / "metrics.json"
_PRIOR: dict[str, Any] | None = None


def global_ssim(original: np.ndarray, recon: np.ndarray, peak: float = 1.0) -> float:
    """Single-window SSIM. Same formula as scripts/studio/measure.py."""
    x = np.asarray(original, dtype=np.float64).ravel()
    y = np.asarray(recon, dtype=np.float64).ravel()
    n = x.size
    mu_x = float(x.mean())
    mu_y = float(y.mean())
    var_x = float(np.sum((x - mu_x) ** 2) / (n - 1))
    var_y = float(np.sum((y - mu_y) ** 2) / (n - 1))
    cov = float(np.sum((x - mu_x) * (y - mu_y)) / (n - 1))
    c1 = (0.01 * peak) ** 2
    c2 = (0.03 * peak) ** 2
    num = (2 * mu_x * mu_y + c1) * (2 * cov + c2)
    den = (mu_x**2 + mu_y**2 + c1) * (var_x + var_y + c2)
    return float(num / den)


def image_metrics(original: np.ndarray, recon: np.ndarray) -> dict[str, Any]:
    mse = float(np.mean((np.asarray(original) - np.asarray(recon)) ** 2))
    if mse <= 0.0:
        psnr = None
    else:
        psnr = float(10.0 * np.log10(1.0 / mse))
    return {
        "mse": mse,
        "psnr": psnr,
        "global_ssim": global_ssim(original, recon),
        "note": "PSNR is 10 log10(1 / mse) on this 8x8 projection. Global SSIM is one window, the whole image.",
    }


def study_prior_report() -> dict[str, Any]:
    """The per-component toy prior numbers from the digits study file."""
    if not _STUDY.is_file():
        return {
            "available": False,
            "note": "scripts/studio/outputs/metrics.json is missing; no study numbers to show.",
        }
    data = json.loads(_STUDY.read_text(encoding="utf-8"))
    block = data["prior_component_after_sweep"]
    recon = block["test_reconstruction"]
    return {
        "available": True,
        "label": "Toy class-conditional PCA prior. Not a generative model.",
        "source": "scripts/studio/outputs/metrics.json prior_component_after_sweep",
        "config": block["config"],
        "holdout_reconstruction_psnr": recon["psnr_from_mean_mse"],
        "holdout_reconstruction_global_ssim": recon["global_ssim_mean"],
        "same_class_nearest_train_rate": block["same_class_nearest_train_rate"],
        "exact_train_copies": block["exact_train_copies"],
        "explained_variance_ratio": block["explained_variance_ratio"],
        "mean_sample_psnr_vs_class_mean_image": block["mean_sample_psnr_vs_class_mean_image"],
        "samples_per_class_in_the_study": block["samples_per_class"],
        "note": (
            "These figures are the digits holdout run. They are not a score "
            "for the sample drawn below."
        ),
    }


def _pca() -> PcaComponentCodec:
    codec = open_codec("pca_component")
    if not isinstance(codec, PcaComponentCodec):
        raise TypeError("pca_component codec was replaced")
    codec.ensure()
    return codec


def _digits_prior() -> dict[str, Any]:
    global _PRIOR
    if _PRIOR is not None:
        return _PRIOR
    codec = _pca()
    assert codec.images is not None and codec.labels is not None and codec.train_idx is not None
    packets = [codec.encode_matrix(codec.images[int(i)]) for i in codec.train_idx]
    codes = np.stack([code_vector(packet) for packet in packets])
    labels = codec.labels[codec.train_idx]
    model = fit_class_conditional(codes, labels, n_components=16)
    _PRIOR = {"model": model, "template": packets[0]}
    return _PRIOR


def round_trip(image: np.ndarray, *, codec_name: str = "pca_component") -> dict[str, Any]:
    """Project, encode to a per-component packet, decode, measure, gate."""
    codec = open_codec(codec_name)
    projected = project_for(codec, image)
    packet = codec.encode_matrix(projected)
    decoded = codec.decode(packet)
    gate = gate_studio_packet(packet)
    return {
        "codec": codec.name,
        "projected": projected,
        "decoded": decoded,
        "metrics": image_metrics(projected, decoded),
        "packet": packet_summary(packet),
        "gate": gate,
        "status": "round_trip",
        "learned": False,
        "scar_matrix_updated": False,
    }


def project_for(codec: Any, image: np.ndarray) -> np.ndarray:
    if hasattr(codec, "project"):
        return codec.project(image)
    from resileos.studio.codecs import project_gray

    return project_gray(image)


def sample_toy_prior(
    label: int,
    *,
    seed: int = 0,
    register: bool = True,
) -> dict[str, Any]:
    """Draw one code from the class-conditional PCA prior and decode it.

    The sample is a candidate when the gate passes. learn is not called.
    """
    fitted = _digits_prior()
    rng = np.random.default_rng(int(seed) + 17 * int(label))
    from studio.prior import packet_from_code

    code = sample_code(fitted["model"], int(label), rng)
    image = decode_code(fitted["template"], code)
    packet = packet_from_code(fitted["template"], code)
    gate = gate_studio_packet(packet)
    candidate = None
    if register and gate["hephaestus"]["verified"] and gate["themis"]["verified"]:
        candidate = register_candidate(
            kind="image",
            path=f"candidate://toy-prior/class-{int(label)}",
            title=f"CANDIDATE toy prior class {int(label)}",
            world_id="studio",
            note="toy prior sample; not a fact; learn was not called",
        )
    return {
        "codec": "pca_component",
        "label": int(label),
        "image": image,
        "packet": packet_summary(packet),
        "gate": gate,
        "candidate": candidate,
        "study": study_prior_report(),
        "status": "candidate" if candidate else "not_registered",
        "learned": False,
        "scar_matrix_updated": False,
    }


def propose_external(
    *,
    condition: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    register: bool = True,
) -> dict[str, Any]:
    """Ask the configured external sampler for a packet. Off by default."""
    sampler = resolve_external_sampler(env)
    status = sampler.status()
    if not sampler.enabled:
        return {
            "enabled": False,
            "sampler": status,
            "candidate": None,
            "learned": False,
            "scar_matrix_updated": False,
        }
    packet = sampler.propose(condition=condition)
    image = decode(packet)
    gate = gate_studio_packet(packet)
    candidate = None
    if register and gate["hephaestus"]["verified"] and gate["themis"]["verified"]:
        candidate = register_candidate(
            kind="image",
            path=f"candidate://external/{sampler.name}",
            title=f"CANDIDATE external sampler {sampler.name}",
            world_id="studio",
            note="external sampler packet; not a fact; learn was not called",
        )
    return {
        "enabled": True,
        "sampler": status,
        "image": image,
        "packet": packet_summary(packet),
        "gate": gate,
        "candidate": candidate,
        "status": "candidate" if candidate else "not_registered",
        "learned": False,
        "scar_matrix_updated": False,
    }
