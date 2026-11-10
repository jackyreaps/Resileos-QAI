"""Streamlit panel for the residual codec mode. Logic lives in service.py."""
from __future__ import annotations

from typing import Any, Callable

import numpy as np


def _up(image: np.ndarray, scale: int = 8) -> np.ndarray:
    uint8 = np.clip(np.rint(np.asarray(image, dtype=np.float64) * 255.0), 0, 255).astype(np.uint8)
    return np.repeat(np.repeat(uint8, scale, axis=0), scale, axis=1)


def _show_gate(st: Any, gate: dict[str, Any]) -> None:
    heph = gate["hephaestus"]
    themis = gate["themis"]
    consistency = gate["residual_consistency"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Hephaestus", "pass" if heph.get("verified") else "fail")
    c2.metric("Residual consistency", "pass" if consistency.get("consistent") else "fail")
    c3.metric("Themis", "pass" if themis.get("verified") else "fail")
    st.caption(heph.get("reason", ""))
    st.caption(consistency.get("reason", ""))
    st.caption(themis.get("reason", ""))
    with st.expander("Verdicts"):
        st.json(
            {
                "well_formed": gate["well_formed"],
                "packet_hash": gate["packet_hash"],
                "learned": gate["learned"],
                "scar_matrix_updated": gate["scar_matrix_updated"],
                "hephaestus": heph,
                "residual_consistency": consistency,
                "themis": themis,
            }
        )


def render_residual_codec(st: Any, *, on_candidate: Callable[[dict[str, Any], np.ndarray], None] | None = None) -> None:
    """Residual codec mode. Coding only. Samples are candidates."""
    from resileos.studio.codecs import CodecUnavailable, codec_names
    from resileos.studio.external_sampler import resolve_external_sampler
    from resileos.studio.service import propose_external, round_trip, sample_toy_prior, study_prior_report

    st.subheader("Residual codec")
    st.markdown(
        "The residual stack is the coding layer. The encoder and the decoder "
        "live outside the core. A round trip does not call learn and does not "
        "update the scar matrix. Sampled images are candidates, not facts."
    )
    names = codec_names()
    codec_name = st.selectbox(
        "Codec",
        names,
        index=names.index("pca_component") if "pca_component" in names else 0,
        help="pca_component is the digits PCA encoder with per-component scales. learned_conv is the empty drop-in.",
    )
    if codec_name == "learned_conv":
        st.info("learned_conv is not trained. The interface is there so a conv encoder and decoder can replace the PCA pair later.")

    st.markdown("#### Encode and decode")
    st.caption(
        "The picture is projected to 8×8 grayscale. PSNR and the single-window "
        "SSIM below are on that projection. Bases are the PCA axes fit on the "
        "digits train split (seed 0, 36 images per class held out)."
    )
    source = st.radio("Source", ["Holdout digit", "Upload"], horizontal=True)
    image = None
    if source == "Holdout digit":
        label = st.selectbox("Digit class", list(range(10)), index=0)
        if st.button("Encode and decode", type="primary", key="codec_round"):
            from resileos.studio.codecs import open_codec

            try:
                image = open_codec("pca_component").holdout_matrix(int(label))  # type: ignore[attr-defined]
                st.session_state["codec_result"] = round_trip(image, codec_name=codec_name)
            except CodecUnavailable as exc:
                st.session_state.pop("codec_result", None)
                st.error(str(exc))
        if st.session_state.get("codec_result") is not None and source == "Holdout digit":
            _show_round_trip(st, st.session_state["codec_result"])
    else:
        upload = st.file_uploader("Image", type=["png", "jpg", "jpeg"], key="codec_upload")
        if st.button("Encode and decode upload", type="primary", key="codec_up_btn") and upload is not None:
            from PIL import Image

            image = np.asarray(Image.open(upload).convert("RGB"))
            try:
                st.session_state["codec_result"] = round_trip(image, codec_name=codec_name)
            except CodecUnavailable as exc:
                st.session_state.pop("codec_result", None)
                st.error(str(exc))
        if st.session_state.get("codec_result") is not None and source == "Upload":
            _show_round_trip(st, st.session_state["codec_result"])

    st.divider()
    st.markdown("#### Sample new codes")
    study = study_prior_report()
    if study.get("available"):
        st.markdown(
            f"**Toy prior.** {study['label']} "
            f"On the digits holdout this prior's codec reconstructed at "
            f"**{study['holdout_reconstruction_psnr']:.2f} dB** "
            f"(global SSIM **{study['holdout_reconstruction_global_ssim']:.3f}**). "
            f"Same-class nearest training image: **{study['same_class_nearest_train_rate']:.4f}**. "
            f"Exact training copies: **{study['exact_train_copies']}**. "
            f"16 components explained **{study['explained_variance_ratio']:.3f}** of the code variance. "
            f"Source: `{study['source']}`."
        )
        st.caption(study["note"])
    else:
        st.warning(study.get("note", "Study numbers unavailable."))
    sample_label = st.selectbox("Class to sample", list(range(10)), index=3, key="toy_class")
    sample_seed = st.number_input("Sample seed", min_value=0, max_value=10_000, value=0, step=1, key="toy_seed")

    def _draw_sample() -> None:
        drawn = sample_toy_prior(
            int(st.session_state["toy_class"]),
            seed=int(st.session_state["toy_seed"]),
        )
        st.session_state["toy_sample_result"] = drawn
        if drawn.get("candidate") is not None and on_candidate is not None:
            on_candidate(drawn["candidate"], drawn["image"])

    st.button("Sample new codes", key="toy_sample_btn", on_click=_draw_sample)
    drawn = st.session_state.get("toy_sample_result")
    if isinstance(drawn, dict):
        st.image(_up(drawn["image"]), caption="CANDIDATE. Toy prior. Not a fact.", width=256)
        packet = drawn["packet"]
        st.write(
            f"Packet `{packet['version']}` · {packet['logical_bits']} bits · "
            f"{packet['packed_bytes']} packed bytes · scales per layer {packet['scales_per_layer']}"
        )
        _show_gate(st, drawn["gate"])
        candidate = drawn["candidate"]
        if candidate is None:
            st.error("Not registered. Hephaestus or Themis did not pass, and learn was not called.")
        else:
            st.success(
                f"Registered `{candidate['asset_id']}` as a candidate. "
                f"learned={candidate['learned']}."
            )

    st.divider()
    st.markdown("#### External sampler")
    sampler = resolve_external_sampler()
    status = sampler.status()
    if status["enabled"]:
        st.warning(f"External sampler `{status['name']}` is on. {status['reason']}")
        def _propose() -> None:
            proposed = propose_external()
            st.session_state["external_result"] = proposed
            if proposed.get("candidate") and on_candidate is not None:
                on_candidate(proposed["candidate"], proposed["image"])

        st.button("Propose a packet", key="ext_propose", on_click=_propose)
        proposed = st.session_state.get("external_result")
        if isinstance(proposed, dict) and proposed.get("image") is not None:
            st.image(_up(proposed["image"]), caption="CANDIDATE from the external sampler.", width=256)
            _show_gate(st, proposed["gate"])
            if proposed.get("candidate"):
                st.success(
                    f"Registered `{proposed['candidate']['asset_id']}` as a candidate. "
                    f"learned={proposed['candidate']['learned']}."
                )
    else:
        st.info(
            f"External sampler is off. {status['reason']}. "
            "Set RESILEOS_EXTERNAL_SAMPLER=fake to use the in-repo stand-in. "
            "No weights are loaded. See docs/studio/external-samplers.md."
        )


def _show_round_trip(st: Any, result: dict[str, Any]) -> None:
    left, right = st.columns(2)
    with left:
        st.image(_up(result["projected"]), caption="Projected 8×8, shown 8×", width=256)
    with right:
        st.image(_up(result["decoded"]), caption="Decoded from the packet", width=256)
    metrics = result["metrics"]
    packet = result["packet"]
    psnr = metrics["psnr"]
    c1, c2, c3 = st.columns(3)
    c1.metric("PSNR (this image)", "exact" if psnr is None else f"{psnr:.2f} dB")
    c2.metric("Global SSIM", f"{metrics['global_ssim']:.3f}")
    c3.metric("Bits", f"{packet['logical_bits']}")
    st.caption(
        f"{packet['packed_bytes']} packed bytes including the 14-byte header. "
        f"Per-component scales: {packet['scales_per_layer']}. "
        f"learned={result['learned']}. scar_matrix_updated={result['scar_matrix_updated']}. "
        f"{metrics['note']}"
    )
    _show_gate(st, result["gate"])
