---
doc: STUDIO-002
title: External samplers
status: corrected — MiniMax-H3-Image card checked 2026-11-10
depends_on: [STUDIO-001, RES-201]
---

# External samplers

An external sampler proposes a `studio-codec/1` packet. It does not call
`learn`, and it does not touch the scar matrix. The Studio mode reads
`RESILEOS_EXTERNAL_SAMPLER`. Unset, `off`, `none`, and `disabled` leave the
sampler off.

Two names are implemented, and neither downloads weights:

- `fake` builds a deterministic ±1 packet in process. No network.
- `minimax_api` is a stub for the hosted MiniMax-H3-Image API. It stays off
  unless that name is set **and** `MINIMAX_API_KEY` is set. A key alone does
  nothing. The stub asks for `b64_json`, re-encodes the pixels with the
  residual codec, and returns only the packet. Studio then treats that
  packet as a candidate.

Any other name, including `p-h3-image`, stays off.

## Correction

An earlier draft of this note said there was no separate MiniMax release
named H3-Image. That was wrong. **MiniMax-H3-Image** is its own model:
[huggingface.co/MiniMaxAI/MiniMax-H3-Image](https://huggingface.co/MiniMaxAI/MiniMax-H3-Image).
MiniMax-H3 is the video model. P-H3-Image is Pruna's separate distillation.
They are three different things.

Nothing below was downloaded. The figures are from the model card, the
community license, and the platform image-generation guides, read on
2026-11-10.

## MiniMax-H3-Image

Card: [MiniMaxAI/MiniMax-H3-Image](https://huggingface.co/MiniMaxAI/MiniMax-H3-Image).
License file: [LICENSE](https://huggingface.co/MiniMaxAI/MiniMax-H3-Image/blob/main/LICENSE).

It is one checkpoint for text-to-image and for editing with reference
images. The card says it is distilled to 6 sampling steps (6 NFEs) with no
classifier-free guidance, and that it generates images of about 16
megapixels directly, without an upscaler. The sizes it lists around that
point run from 4096×4096 (1:1) to 6272×2688 (21:9). It also says the
effective working range is about 4 MP to 20 MP, with the best results
around 16 MP.

Architecture, as the card states it:

- Diffusion transformer: 33.1B parameters, dense, single-stream, 50 layers,
  hidden size 5376, 56 attention heads, FFN size 14336, 3D multimodal RoPE.
  Same block family as the H3-Omni-Transformer, without the audio layers.
  Weights are BF16. The embedding, timestep, and output layers are FP32.
- Image VAE: a CNN encoder and a 2D ViT decoder (24 layers), 16× spatial
  downsampling, 24 latent channels. The DiT patchifies that latent with a
  2×2 patch, so each transformer token covers 32×32 pixels.
- Text encoder: the Qwen3-VL text encoder from MiniMax-H3, unchanged. The
  DiT reads hidden states from its 50th layer. It is not in the H3-Image
  repository. `model_index.json` loads it from `MiniMaxAI/MiniMax-H3`,
  folder `text_encoder/`.
- Optional prompt expander: [MiniMax-H3-Image-PE](https://huggingface.co/MiniMaxAI/MiniMax-H3-Image-PE).
  The card lists it as NVFP4, 17.9 GB. The hosted API can expand prompts
  through H3-Image-Context-IR instead. That expander is a separate call.

The text prompt and any reference images are encoded into one packed
sequence for that single-stream transformer. The transformer predicts the
target latent. The VAE decodes it.

### Weights

From the model card's own tables, not from a download:

| Piece | Where | Size on the card |
|---|---|---|
| MiniMax-H3-Image checkpoint | `MiniMaxAI/MiniMax-H3-Image` | 68.65 GB |
| of which the DiT (`transformer/`) | same repo | 66.28 GB |
| of which the VAE | same repo | 2.34 GB |
| Text encoder | `MiniMaxAI/MiniMax-H3`, `text_encoder/` | 66.7 GB |
| Optional PE | `MiniMaxAI/MiniMax-H3-Image-PE` | 17.9 GB |

About 69 GB for the image checkpoint, plus about 67 GB for the text
encoder. This repository does not vendor either.

The card says to serve it with SGLang, vLLM-Omni, diffusers, or ComfyUI.
Local servers it documents expose `POST /v1/images/generations` and
`POST /v1/images/edits`. The response shape it shows puts the PNG in
`data[0].b64_json`. The Studio stub asks for that field and does not
follow a returned URL.

### Community license

The card releases the checkpoint under the **MiniMax-H3-Image Community
License Agreement** (license date November 10, 2026). The same agreement
covers MiniMax-H3-Image-PE.

"Excluded Territories" in that license are the European Union, the United
Kingdom, the Republic of Korea, and the United States of America.
"Applicable Territory" is the world outside that list. The grant of rights
is only inside the Applicable Territory. Section V.4 says you may not use,
reproduce, modify, distribute, or display the works **or any of their
outputs or results** outside the Applicable Territory, and that such use
is not authorized by the agreement.

A separate license for the excluded territories is requested through the
application form linked from the card and from Section IV of the license:
[platform.minimax.io/license](https://platform.minimax.io/license).
Without that separate license, use of the weights or of their outputs in
those territories is not authorized by the community agreement.

Section IV also says a separate written authorization is required if
annualized revenue of you and your affiliates exceeds 1 million USD, or if
you provide a hosted service to third parties. That is a term of the
license, not a terms-of-service ruling about the public API.

### Hosted API, separately

The card points at a hosted API:

- Global: [platform.minimax.io](https://platform.minimax.io)
- China: [platform.minimax.cn](https://platform.minimax.cn)
- Image guide (English): [platform.minimax.io/docs/guides/image-generation](https://platform.minimax.io/docs/guides/image-generation)
- Image guide (Chinese): [platform.minimax.cn/docs/guides/image-generation](https://platform.minimax.cn/docs/guides/image-generation)

Those guides describe `POST /v1/images/generations` and
`POST /v1/images/edits` on `api.minimax.io` and `api.minimax.cn`, for the
model id `MiniMax-H3-Image`. They are product documentation. They are not
the community license, and this note does not treat them as permission to
use the weights.

The hosted API is a different route, governed by the platform's own terms.
The owner has to read those terms before anyone sends a prompt or stores
an image. This note does not say the platform terms allow use in the
United States, or in any other excluded territory, or anywhere else.

The community license's own definition of "Hosted Service" includes APIs.
That does not settle what the platform contract says. Both documents have
to be read. This repository's stub does not send a request unless the
operator sets the opt-in and a key, and even then the tests never call
the network.

## What the stub does

`RESILEOS_EXTERNAL_SAMPLER=minimax_api` is the opt-in. `MINIMAX_API_KEY`
is required as well. Either one alone leaves the sampler off, and
`propose` raises before any socket. `MINIMAX_API_BASE` is the host
(`https://api.minimax.io` or `https://api.minimax.cn` are the ones the
guides show). If the base is unset and no test double was injected, no
request is sent.

The call, when it happens, is one JSON POST to
`{MINIMAX_API_BASE}/v1/images/generations` with `response_format` of
`b64_json`. The PNG or JPEG bytes are decoded in process and passed
through the PCA per-component codec. The packet from that encode is the
only value returned. Studio decodes the packet, gates it with Hephaestus,
residual consistency, and Themis, and registers it as a candidate.
`learn` is not called. The scar matrix is not updated. A URL in the
response is not fetched.

This is not a 16-megapixel client. It does not download the 69 GB
checkpoint or the text encoder. It does not start SGLang, vLLM, diffusers,
or ComfyUI.

## MiniMax-H3 and P-H3-Image

Kept so the names stay distinct. Neither is MiniMax-H3-Image.

**MiniMax-H3** ([GitHub](https://github.com/MiniMax-AI/MiniMax-H3),
[weights](https://huggingface.co/MiniMaxAI/MiniMax-H3)) generates video
with stereo audio. Its README describes a visual VAE, a 33B single-stream
transformer, 3D RoPE, AdaLN, and a packed text/vision/audio sequence. Its
license is the MiniMax H3 Community License, a different document from the
H3-Image community license.

**P-H3-Image** ([card](https://huggingface.co/PrunaAI/P-H3-Image),
[Pruna's blog](https://www.pruna.ai/blog/oss-p-h3-image-launch)) is Pruna's
image model based on MiniMax-H3. The card describes 8 steps and no
classifier-free guidance, and lists a 33.1B transformer. The blog describes
a smaller backbone. Those two pages disagree. The card says the license is
the MiniMax H3 Community License. Setting `RESILEOS_EXTERNAL_SAMPLER` to
`p-h3-image` does not load it.

## Design notes, not a port

Three ideas are worth borrowing. None of them belong inside the scar update.

**Per-component scales.** The digits study measured this. One scale for a
whole rank-r product is a weak codec. One scale per rank-1 term is what
the Studio mode stores. H3-Image's latent is a different object: 24
channels, 16× spatial, then a 2×2 patch. The borrow is the gain per
component, not a claim that bipolar scales match that VAE.

**RoPE, outside the core.** H3-Image uses 3D multimodal RoPE on the packed
sequence, the same position scheme as H3. If a future prior predicts
residual codes on a grid, the positions belong in that prior. The core
codes one matrix.

**AdaLN and prompts, outside the core.** H3 keeps timestep and modality
conditioning in AdaLN and leaves the shared block modality-agnostic.
H3-Image keeps the prompt in the text encoder and the packed sequence.
A prompt may condition the sampler. The packet that comes back is factors
and scales. The core does not learn a text embedding.

Packed sequences are how those models mix text and image tokens in one
self-attention stream. A studio prior could pack a caption beside residual
codes the same way. That packing is a property of the sampler, not of the
control packet and not of Λ.
