---
doc: STUDIO-002
title: External samplers
status: draft — lookup on 2026-11-10, no weights downloaded
depends_on: [STUDIO-001, RES-201]
---

# External samplers

An external sampler proposes a `studio-codec/1` packet. It does not decode,
it does not call `learn`, and it does not touch the scar matrix. The Studio
mode reads `RESILEOS_EXTERNAL_SAMPLER`. Unset, `off`, `none`, and `disabled`
leave the sampler off. The only implementation in this repository is `fake`,
which builds a deterministic ±1 packet with per-component scales and does
not open a network connection. Any other name, including `p-h3-image`, stays
off and is not loaded.

No weights and no third-party sampler code are vendored here.

## What was checked

Looked up on 2026-11-10 from public pages. Nothing was downloaded.

There is no separate MiniMax release found under the name "H3-Image".
MiniMax publishes **MiniMax-H3**, a video and audio model that also accepts
images as conditions. **P-H3-Image** is Pruna's image model based on that
system. The notes below keep those two names apart.

### MiniMax-H3

- Code and architecture write-up: [github.com/MiniMax-AI/MiniMax-H3](https://github.com/MiniMax-AI/MiniMax-H3).
- Weights and the license FAQ: [huggingface.co/MiniMaxAI/MiniMax-H3](https://huggingface.co/MiniMaxAI/MiniMax-H3).
- License text used by the image distillation as well: [PrunaAI/P-H3-Image LICENSE](https://huggingface.co/PrunaAI/P-H3-Image/blob/main/LICENSE), which is the MiniMax H3 Community License. The GitHub README says MiniMax H3 is released under that agreement.

What the README states, in its own words:

- H3 generates video with stereo audio, up to 15 seconds, 24 fps. The shorter side defaults to 768 pixels. A 2K regenerate stage exists and is **not** in the open-source drop ("this module is not yet open-sourced").
- Two open checkpoints: `MiniMax-H3 Base FL2VA` and `MiniMax-H3 Base Ref2VA`, both BF16, described as CFG-distilled. Each repo holds a processor, tokenizer, text encoder, transformer, visual VAE, and audio VAE.
- The visual path is a VAE (spatial compression 16×, temporal 4×, 24 latent channels) plus a later patch of `1×2×2`. The README also says a ViT decoder is trained after the encoder.
- The generator is the H3-Omni-Transformer: a 33B dense single-stream transformer. About 13B of that is AdaLN. The README says those AdaLN outputs can be cached and need not be loaded for inference-only use, and that the full weights are released anyway.
- Attention and the FFN are shared across modalities. Modality-specific parameters sit in the input and output layers and in AdaLN.
- Positions are 3D multimodal RoPE over `(t, h, w)`. The public diffusers class describes the same three-axis rotary embedding: [transformer_minimax_h3.py](https://github.com/huggingface/diffusers/blob/main/src/diffusers/models/transformers/transformer_minimax_h3.py).
- Tokens from text, vision, and audio are one packed sequence. RoPE is applied before that sequence enters the transformer.
- The text encoder starts from Qwen3-VL-32B and passes layer-50 hidden states.
- H3-Context-IR, the hosted prompt preprocessor, is **not** in the open-source release.

The community license, as quoted on the P-H3-Image card and in the license file linked above, grants rights only outside the European Union, the United Kingdom, the Republic of Korea, and the United States, unless MiniMax grants a separate license. Products built on the works must show "Powered by MiniMax H3". This repository does not use the weights, so that obligation is not triggered here. Read the license before anyone does.

A revenue threshold is sometimes mentioned in secondary write-ups. It was not copied into this note, because the pages read for this lookup did not put a dollar figure in the excerpt that was checked. The license file is the source.

### P-H3-Image

- Model card: [huggingface.co/PrunaAI/P-H3-Image](https://huggingface.co/PrunaAI/P-H3-Image).
- Pruna's write-up: [pruna.ai/blog/oss-p-h3-image-launch](https://www.pruna.ai/blog/oss-p-h3-image-launch).
- Diffusers integration: [huggingface/diffusers pull 15171](https://github.com/huggingface/diffusers/pull/15171).

The model card (fetched 2026-11-10) says P-H3-Image is an image model based on MiniMax-H3: text-to-image and editing with 1 to 8 images, 8 sampling steps, no classifier-free guidance, best at about 8 megapixels. It lists a 33.1B-parameter transformer, a 4B text encoder, a VAE, and a prompt upsampler, about 100 GB in bf16, and about 83 GB of GPU memory at 8 MP without the upsampler (about 101 GB with it). A ComfyUI package, [PrunaAI/P-H3-Image-Comfy](https://huggingface.co/PrunaAI/P-H3-Image-Comfy), is where the card points for int8 and 4-bit files that run in less memory. The card's own lower-memory note for the bf16 pipeline is auto offload onto an 80 GB GPU.

Pruna's blog describes a different size: the timestep block (about 40% of H3's transformer) replaced by a smaller one, backbone from 33B to 20B parameters, smallest download 20 GB rather than 143 GB, and a new single-frame decoder because H3's video decoder is blurry on one frame. The diffusers pull says the transformer class is the existing `MiniMaxH3Transformer3DModel`, unchanged, and that the VAE is MiniMax-H3's encoder with a single-frame image decoder. Those three sources do not agree on whether the shipped transformer is 33.1B or 20B. This note does not pick a winner. The card is what the Hub page showed; the blog is what Pruna wrote about the distillation; the pull is what diffusers reviewed.

License, from the model card: the MiniMax H3 Community License, with the same territory exclusion and the "Powered by MiniMax H3" line. The card says the text encoder's Qwen3-VL-4B parts and the Qwen3.5-9B prompt upsampler are Apache 2.0. See the card's NOTICE, which was not vendored here.

P-H3-Image does not generate video. The card says so.

## How one would plug in

Not built. The contract is already the one `ExternalSampler.propose` uses:

1. The sampler, running in its own process if the weights are large, turns a prompt or a condition dict into a `studio-codec/1` packet with per-component scales, or into latents that an adapter folds into that packet.
2. Studio calls `decode` on the packet with whatever decoder is registered. Today that is the linear sum. A learned decoder would be the `learned_conv` slot, still outside `ResidualCore`.
3. The packet is gated (Hephaestus, residual consistency, Themis) and, if it passes, registered as a candidate. `learn` is not called.

A P-H3-style model does not natively emit bipolar residual factors. An adapter would have to encode its decoded image, or its VAE latent, with the studio codec. That adapter is the boundary. The DiT stays on the far side of it. Turning `RESILEOS_EXTERNAL_SAMPLER` to a Hub id must not be enough to download 100 GB; a future loader would be a separate, explicit step, and it would have to record the license territory before the first forward pass.

## Design notes, not a port

Three ideas are worth borrowing. None of them belong inside the scar update.

**Per-component scales.** The digits study already measured this. One scale for a whole rank-r product is a weak codec; one scale per rank-1 term is the stronger variant, and it is what the Studio mode stores. H3's own latent is a different object (24 channels, 16× spatial). The borrow is the idea that each component carries its own gain, which this codec now does. It is not a claim that bipolar scales match a VAE latent.

**RoPE-style positions, outside the core.** H3 puts 3D rotary positions on the packed token sequence before the transformer. If a future prior predicts residual codes on a grid, the positions belong in that prior, not in `ResidualCore`. The core codes one matrix. It does not need a rotary embedding to do that.

**AdaLN conditioning, outside the core.** H3 keeps modality and timestep conditioning in AdaLN branches, and says the shared attention block stays modality-agnostic. That split matches the rule already in force here: a prompt, a class id, or a timestep may condition the sampler, and the packet that comes back is still just factors and scales. The core does not learn a text embedding.

Packed sequences are how H3 mixes text, frames, and audio in one self-attention stream. A studio prior could pack a caption's tokens beside residual codes the same way. That packing is a property of the sampler's sequence, not of the control packet and not of Λ.
