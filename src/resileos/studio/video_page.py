"""Studio video page. A sibling of the residual codec panel.

Top to bottom: a prompt and spec box, Draft / Verify / Upscale, a Hades
panel, and an output strip. The page calls the Forge legion. It compresses
and checks frames that were supplied. It does not generate video.

Upscale stays disabled until Verify returns verified or inconclusive.
A prompt with no frames and no packet is UNAVAILABLE. Mouth stays off
unless the sequence is verified. Only a verified sequence is a candidate.
"""
from __future__ import annotations

from typing import Any

SECTIONS = ("prompt", "stages", "hades", "output")

VIDEO_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Studio clip</title>
<link rel="stylesheet" href="/assets/fonts/fonts.css">
<link rel="stylesheet" href="/assets/site.css">
<link rel="stylesheet" href="/assets/chat-ui.css">
<style>
  main.studio-clip {
    --chip-bg: rgba(124, 92, 255, 0.14);
    --shadow: 0 24px 70px rgba(0, 0, 0, 0.45);
    max-width: 880px; margin: 0 auto; padding: 24px 16px 48px; display: flex; flex-direction: column; gap: 16px;
  }
  main.studio-clip .btn-label { cursor: pointer; font: inherit; }
  main.studio-clip > section { max-width: none; margin: 0; padding: 16px 18px; }
  main.studio-clip h1 { font-size: 1.8rem; margin: 0; }
  main.studio-clip h2 { font-size: 1.15rem; margin: 0 0 8px; }
  main.studio-clip p { margin: 0; }
  main.studio-clip label { display: block; font-size: 0.85rem; margin: 10px 0 4px; }
  main.studio-clip textarea, main.studio-clip input[type="text"], main.studio-clip input[type="password"] { width: 100%; font: inherit; padding: 8px; }
  main.studio-clip textarea { min-height: 72px; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
  main.studio-clip button:disabled { opacity: 0.45; cursor: not-allowed; }
  .frames, .timeline { display: flex; gap: 8px; flex-wrap: wrap; align-items: flex-end; }
  canvas { width: 96px; height: 96px; image-rendering: pixelated; background: var(--surface, #101623); border: 1px solid var(--border, #243049); }
  figure { margin: 0; }
  figcaption { font-size: 0.75rem; color: var(--muted, #8b97b0); }
  pre { white-space: pre-wrap; word-break: break-word; font-size: 0.8rem; }
  .muted { color: var(--muted, #8b97b0); font-size: 0.9rem; }
</style>
</head>
<body>
<main class="studio-clip">
  <header>
    <h1>Studio clip</h1>
    <p class="muted">Compresses and checks frames you supply. It does not generate video.</p>
  </header>
  <section id="prompt" class="card">
    <h2>Prompt / spec</h2>
    <label for="spec">Spec</label>
    <textarea id="spec" placeholder="Describe the clip you already have"></textarea>
    <label for="context">Context, one item per line</label>
    <textarea id="context" placeholder="Supplied context. Hermes ranks this list."></textarea>
    <label for="key">API key</label>
    <input id="key" type="password" autocomplete="off">
    <label for="frames">Frames</label>
    <input id="frames" type="file" accept="image/*" multiple>
    <label for="packet">Residual packet</label>
    <input id="packet" type="file" accept="application/json,.json">
    <div class="row"><button id="scene" class="btn-label" type="button">Run scene steps</button></div>
    <p class="muted">Scene steps are stubs: geometry, lighting and materials, then camera and animation. No generator is called.</p>
  </section>
  <section id="stages" class="card">
    <h2>Stages</h2>
    <div class="row">
      <button id="draft" class="btn-label" type="button">Draft</button>
      <button id="verify" class="btn-label" type="button">Verify</button>
      <button id="upscale" class="btn-label" type="button" disabled>Upscale</button>
    </div>
    <p id="stage-note" class="muted"></p>
  </section>
  <section id="hades" class="card">
    <h2>Hades</h2>
    <p>Checkpoint <span id="ckpt-id">—</span></p>
    <p>Lesson <span id="lesson">—</span></p>
    <p>Residual hash <span id="hash">—</span></p>
    <div class="row">
      <button id="checkpoint" class="btn-label" type="button">Checkpoint</button>
      <button id="restore" class="btn-label" type="button">Restore fresh</button>
    </div>
    <pre id="fresh" class="codebox"></pre>
  </section>
  <section id="output" class="card">
    <h2>Output</h2>
    <h2>Keyframe timeline</h2>
    <div class="timeline" id="timeline"></div>
    <p id="cost-meter" class="muted">Reused frames —. Frames that would need a generative call —.</p>
    <div class="frames" id="previews"></div>
    <p><span id="badge" class="badge">no residual yet</span></p>
    <p id="mouth" class="muted">Mouth off</p>
    <p id="candidate" class="muted">No promotable candidate</p>
    <p id="url" class="muted"></p>
    <div class="row"><button id="download" class="btn-label" type="button">Download packet</button></div>
    <h2>Control history</h2>
    <pre id="history"></pre>
  </section>
</main>
<script>
const state = { sequence: null, frames: null, history: [], checkpoint: null, upscale: false };
const $ = (id) => document.getElementById(id);

function headers() {
  const h = { "Content-Type": "application/json", "Accept": "application/json" };
  const key = $("key").value.trim();
  if (key) h["X-API-Key"] = key;
  return h;
}

function contextItems() {
  return $("context").value.split(/\n/).map((line) => line.trim()).filter(Boolean);
}

async function readFrames(files) {
  const frames = [];
  for (const file of files) {
    frames.push(await sample(file));
  }
  return frames;
}

function sample(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = 8;
      canvas.height = 8;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0, 8, 8);
      const data = ctx.getImageData(0, 0, 8, 8).data;
      const frame = [];
      for (let y = 0; y < 8; y++) {
        const row = [];
        for (let x = 0; x < 8; x++) {
          const i = (y * 8 + x) * 4;
          const gray = (0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2]) / 255;
          row.push(Math.round(gray * 10000) / 10000);
        }
        frame.push(row);
      }
      resolve(frame);
    };
    img.onerror = () => reject(new Error("frame"));
    img.src = URL.createObjectURL(file);
  });
}

async function readPacket(file) {
  const text = await file.text();
  return JSON.parse(text);
}

function paintInto(host, frames, captions) {
  host.replaceChildren();
  (frames || []).forEach((frame, index) => {
    const canvas = document.createElement("canvas");
    const n = frame.length || 8;
    canvas.width = n;
    canvas.height = frame[0] ? frame[0].length : n;
    const ctx = canvas.getContext("2d");
    const image = ctx.createImageData(canvas.width, canvas.height);
    for (let y = 0; y < frame.length; y++) {
      for (let x = 0; x < frame[y].length; x++) {
        const value = Math.max(0, Math.min(255, Math.round(frame[y][x] * 255)));
        const i = (y * canvas.width + x) * 4;
        image.data[i] = image.data[i + 1] = image.data[i + 2] = value;
        image.data[i + 3] = 255;
      }
    }
    ctx.putImageData(image, 0, 0);
    if (captions) {
      const figure = document.createElement("figure");
      const caption = document.createElement("figcaption");
      caption.textContent = captions[index] || "";
      figure.appendChild(canvas);
      figure.appendChild(caption);
      host.appendChild(figure);
    } else {
      host.appendChild(canvas);
    }
  });
}

function paint(preview) {
  paintInto($("previews"), preview, null);
}

function show(body) {
  if (body.sequence) state.sequence = body.sequence;
  if (Array.isArray(body.history)) state.history = body.history;
  if (body.checkpoint_id) {
    state.checkpoint = {
      id: body.checkpoint_id,
      lesson: body.lesson || "",
      hash: body.residual_hash || body.packet_hash || ""
    };
  }
  if (body.stage === "verify") state.upscale = Boolean(body.upscale_enabled);
  $("upscale").disabled = !state.upscale;
  $("ckpt-id").textContent = state.checkpoint ? state.checkpoint.id : "—";
  $("lesson").textContent = body.lesson || (state.checkpoint ? state.checkpoint.lesson : "—");
  $("hash").textContent = body.residual_hash || body.packet_hash || (state.checkpoint ? state.checkpoint.hash : "—");
  const badge = body.badge || {};
  const bits = body.bits_per_frame || {};
  $("badge").textContent = body.outcome
    ? (body.outcome + " · energy " + (badge.energy ?? "—") + " · consistency " + (badge.consistency_score ?? "—") + " · base " + (bits.base ?? "—") + " bits · delta " + (bits.mean_delta ?? "—"))
    : (body.status || "no residual yet");
  $("mouth").textContent = body.mouth ? "Mouth on" : "Mouth off";
  $("candidate").textContent = body.candidate && body.candidate.asset_id
    ? ("Candidate " + body.candidate.asset_id)
    : "No promotable candidate";
  $("url").textContent = body.url ? body.url : "";
  $("history").textContent = JSON.stringify(state.history, null, 2);
  $("stage-note").textContent = body.detail || body.reason || body.status || "";
  paint(body.preview || []);
  const stills = (body.keyframes || []).map((item) => item.frame);
  const captions = (body.keyframes || []).map((item) => "keyframe " + item.index);
  paintInto($("timeline"), stills, captions);
  const cost = body.cost || {};
  const reused = cost.reused_frames == null ? "—" : cost.reused_frames;
  const generative = cost.generative_frames == null ? "—" : cost.generative_frames;
  $("cost-meter").textContent = "Reused frames " + reused + ". Frames that would need a generative call " + generative + ".";
}

async function post(stage) {
  const framesInput = $("frames").files;
  if (framesInput && framesInput.length) state.frames = await readFrames(framesInput);
  let sequence = state.sequence;
  if ($("packet").files && $("packet").files[0] && stage === "draft") {
    sequence = await readPacket($("packet").files[0]);
    state.sequence = sequence;
  }
  const payload = {
    prompt: $("spec").value,
    stage: stage,
    context: contextItems(),
    history: state.history
  };
  if (state.frames) payload.frames = state.frames;
  if (sequence && stage !== "draft") payload.sequence = sequence;
  if (stage === "draft" && sequence && !(state.frames && state.frames.length)) payload.sequence = sequence;
  const response = await fetch("/api/v1/studio/video", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(payload)
  });
  const body = await response.json();
  show(body);
}

$("draft").addEventListener("click", () => post("draft"));
$("verify").addEventListener("click", () => post("verify"));
$("upscale").addEventListener("click", () => { if (!$("upscale").disabled) post("upscale"); });
$("download").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(state.sequence || {}, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "clip-packet.json";
  link.click();
});
$("restore").addEventListener("click", async () => {
  const id = state.checkpoint ? state.checkpoint.id : "";
  const response = await fetch("/api/v1/studio/video/restore", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ checkpoint_id: id })
  });
  const body = await response.json();
  $("fresh").textContent = JSON.stringify(body.fresh || {}, null, 2);
  $("lesson").textContent = body.lesson || "—";
  $("hash").textContent = body.residual_hash || "—";
});
$("checkpoint").addEventListener("click", async () => {
  const response = await fetch("/api/v1/studio/video/checkpoint", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      prompt: $("spec").value,
      frames: state.frames,
      sequence: state.sequence
    })
  });
  const body = await response.json();
  if (body.checkpoint_id) {
    state.checkpoint = { id: body.checkpoint_id, lesson: body.lesson || "", hash: body.residual_hash || "" };
    $("ckpt-id").textContent = body.checkpoint_id;
  }
  $("lesson").textContent = body.lesson || "—";
  $("hash").textContent = body.residual_hash || "—";
  $("stage-note").textContent = body.detail || body.status || "";
});
$("scene").addEventListener("click", async () => {
  const response = await fetch("/api/v1/studio/video/scene", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ script: $("spec").value })
  });
  const body = await response.json();
  const steps = body.steps || [];
  if (steps.length && steps[steps.length - 1].checkpoint_id) {
    const last = steps[steps.length - 1];
    state.checkpoint = { id: last.checkpoint_id, lesson: last.lesson || "", hash: last.residual_hash || "" };
    $("ckpt-id").textContent = last.checkpoint_id;
    $("lesson").textContent = last.lesson || "—";
    $("hash").textContent = last.residual_hash || "—";
  }
  $("fresh").textContent = JSON.stringify(steps.map((step) => ({
    legion: step.legion,
    checkpoint_id: step.checkpoint_id,
    residual_hash: step.residual_hash,
    executor: step.executor
  })), null, 2);
  $("stage-note").textContent = body.note || "";
});
</script>
</body>
</html>
"""


def render_video_page(st: Any) -> None:
    """Streamlit sibling of the codec panel. Same stages, same legion."""
    import json

    import numpy as np

    st.subheader("Studio clip")
    st.caption("Compresses and checks frames you supply. It does not generate video.")

    prompt = st.text_area("Prompt / spec", key="clip_spec", height=80)
    context_text = st.text_area(
        "Context, one item per line",
        key="clip_context",
        height=68,
        help="Hermes ranks this supplied list.",
    )
    uploads = st.file_uploader(
        "Frames",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="clip_frames",
    )
    packet_file = st.file_uploader("Residual packet", type=["json"], key="clip_packet")
    enabled = bool(st.session_state.get("clip_upscale_enabled"))
    draft_col, verify_col, upscale_col = st.columns(3)
    do_draft = draft_col.button("Draft", key="clip_draft")
    do_verify = verify_col.button("Verify", key="clip_verify")
    do_upscale = upscale_col.button("Upscale", key="clip_upscale", disabled=not enabled)

    st.markdown("**Hades**")
    st.write("Checkpoint", st.session_state.get("clip_checkpoint_id") or "—")
    st.write("Lesson", st.session_state.get("clip_lesson") or "—")
    st.write("Residual hash", st.session_state.get("clip_hash") or "—")
    check_col, restore_col = st.columns(2)
    do_checkpoint = check_col.button("Checkpoint", key="clip_checkpoint")
    if restore_col.button("Restore fresh", key="clip_restore"):
        from resileos.studio.sequence_stage import restore_clip_checkpoint

        restored = restore_clip_checkpoint(str(st.session_state.get("clip_checkpoint_id") or ""))
        st.session_state["clip_fresh"] = restored
    if st.session_state.get("clip_fresh"):
        st.json(st.session_state["clip_fresh"].get("fresh") or {})

    stage = "draft" if do_draft else "verify" if do_verify else "upscale" if do_upscale else "checkpoint" if do_checkpoint else ""
    if stage:
        from resileos.kin.studio_tools import run_forge_video

        frames = None
        if uploads:
            from PIL import Image

            frames = [np.asarray(Image.open(item).convert("RGB")) for item in uploads]
        sequence = st.session_state.get("clip_sequence")
        if packet_file is not None and stage == "draft" and not frames:
            sequence = json.loads(packet_file.getvalue().decode("utf-8"))
        context = [line.strip() for line in context_text.splitlines() if line.strip()]
        if stage == "checkpoint":
            from resileos.studio.sequence_stage import checkpoint_verified_clip

            result = checkpoint_verified_clip(
                prompt=prompt,
                frames=frames,
                sequence=sequence if isinstance(sequence, dict) else None,
            )
        else:
            result = run_forge_video(
                prompt,
                stage=stage,
                frames=frames,
                clip=True,
                sequence=sequence if isinstance(sequence, dict) else None,
                context=context,
                clip_history=st.session_state.get("clip_history"),
            )
        st.session_state["clip_result"] = result
        if isinstance(result.get("sequence"), dict):
            st.session_state["clip_sequence"] = result["sequence"]
        if isinstance(result.get("history"), list):
            st.session_state["clip_history"] = result["history"]
        if result.get("checkpoint_id"):
            st.session_state["clip_checkpoint_id"] = result["checkpoint_id"]
            st.session_state["clip_lesson"] = result.get("lesson")
            st.session_state["clip_hash"] = result.get("residual_hash")
        if stage == "verify":
            st.session_state["clip_upscale_enabled"] = bool(result.get("upscale_enabled"))
        if result.get("candidate"):
            st.session_state["clip_candidate"] = result["candidate"]

    result = st.session_state.get("clip_result")
    st.markdown("**Output**")
    if not isinstance(result, dict):
        st.caption("Decoded previews appear here after Draft.")
        return
    previews = result.get("preview") or []
    keyframes = result.get("keyframes") if isinstance(result.get("keyframes"), list) else []
    if keyframes:
        st.markdown("**Keyframe timeline**")
        st.image(
            [np.asarray(item.get("frame"), dtype=np.float64) for item in keyframes if isinstance(item, dict)],
            caption=[f"keyframe {item.get('index')}" for item in keyframes if isinstance(item, dict)],
            width=96,
        )
    if previews:
        st.image(
            [np.asarray(frame, dtype=np.float64) for frame in previews],
            caption=[f"frame {index}" for index in range(len(previews))],
            width=96,
        )
    badge = result.get("badge") if isinstance(result.get("badge"), dict) else {}
    bits = result.get("bits_per_frame") if isinstance(result.get("bits_per_frame"), dict) else {}
    st.write(
        f"{result.get('outcome') or result.get('status')} · "
        f"energy {badge.get('energy')} · consistency {badge.get('consistency_score')} · "
        f"base {bits.get('base')} bits · delta {bits.get('mean_delta')}"
    )
    cost = result.get("cost") if isinstance(result.get("cost"), dict) else {}
    st.write(
        f"Reused frames {cost.get('reused_frames', '—')}. "
        f"Frames that would need a generative call {cost.get('generative_frames', '—')}."
    )
    st.write("Mouth on" if result.get("mouth") else "Mouth off")
    candidate = st.session_state.get("clip_candidate")
    if isinstance(candidate, dict) and result.get("sequence_verified"):
        st.write(f"Candidate {candidate.get('asset_id')}")
    elif result.get("sequence_verified") and isinstance(result.get("candidate"), dict):
        st.write(f"Candidate {result['candidate'].get('asset_id')}")
    else:
        st.write("No promotable candidate")
    if result.get("url"):
        st.write(result["url"])
    packet = st.session_state.get("clip_sequence")
    if isinstance(packet, dict):
        st.download_button(
            "Download packet",
            data=json.dumps(packet).encode("utf-8"),
            file_name="clip-packet.json",
            mime="application/json",
            key="clip_download",
        )
    st.markdown("**Control history**")
    st.json(st.session_state.get("clip_history") or [])


__all__ = ["SECTIONS", "VIDEO_HTML", "render_video_page"]
