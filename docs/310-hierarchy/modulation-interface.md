doc: RES-315
title: Modulation Interface
status: draft
depends_on: RES-310, RES-311, RES-312, RES-313, RES-314
referenced_by: (none yet)

# Modulation Interface

The carrier (`carrier.py`) is a trainable interface between the frozen
substrate and a downstream model. It emits a "modulation tensor of
caller-declared shape." That description is a stub. This document is the
specification.

It defines what the carrier modulates, in which downstream model, under what
training loop, and what the substrate state contributes. It is the last spec in
the 310-series because it depends on all five others: the hierarchy supplies
the packets, the streaming state supplies the running context, the mask stack
supplies the multi-resolution view, the capacity law says what is
distinguishable, and the error bound says how often the distinctions are
correct.

## 1. The consumer

The modulation interface is defined against a **frozen downstream model**. The
model is not specified here — it could be a transformer, an SSM, a diffusion
model, anything with a modulation surface. The interface is:

    modulate(model, stream_hv, stack_hv) -> model_with_modulation

The model must expose at least one modulation surface. A modulation surface is
a point in the model's forward pass where an additive bias or multiplicative
gate can be applied to an activation tensor of known shape `(batch, seq,
d_model)`.

Common surfaces:

| Surface | Shape | Typical use |
|---------|-------|-------------|
| Embedding bias | `(1, 1, d_model)` | Global context injection |
| Per-layer gate | `(1, 1, d_model)` | Layer-wise modulation |
| Attention bias | `(1, heads, seq, seq)` | Attention pattern modulation |
| KV prefix | `(1, n_prefix, d_model)` | Prefix-tuning |

The interface supports the first three. KV prefix is out of scope because it
requires the model to accept a prefix, which is a model-specific capability.

## 2. The modulation tensor

The carrier maps `(stream_hv, stack_hv)` to a modulation tensor of the declared
surface shape. The mapping is:

    mod = Carrier(stream_hv, stack_hv)

`Carrier` is a small MLP:

    Input:  concat(Re(stream_hv), Im(stream_hv),
                   Re(stack_hv), Im(stack_hv))       shape (4 * dim,)
    Hidden: 2 layers, width 4 * dim, GELU
    Output: shape declared by surface

The carrier is the only trainable component. The substrate is frozen. The
downstream model is frozen. Only the carrier's weights change.

## 3. The training loop

The carrier is trained by gradient descent on a task loss. The substrate's
outputs are treated as fixed features. The loop is:

    for batch in dataloader:
        tokens, targets = batch
        packets = encoder.push_many(tokens)
        for p in packets:
            stream_state.update(p)
        stack_hv = mask_stack.encode(stream_state.readout())
        mod = carrier(stream_state.readout(), stack_hv)
        logits = downstream_model(tokens, modulation=mod)
        loss = task_loss(logits, targets)
        loss.backward()
        optimizer.step()   # updates carrier only

The substrate's forward pass is inside `torch.no_grad()`. The encoder,
streaming state, and mask stack are all non-differentiable with respect to the
carrier's input. The carrier learns to read the substrate's features, not to
change them.

## 4. What the modulation means

The modulation tensor is an additive bias or multiplicative gate at a specific
point in the model. It is *not* a replacement for the model's own
representations. It is a perturbation that depends on the substrate's view of
the stream.

Whether this perturbation improves the model's task performance is an empirical
question. The interface does not claim it does. The claim is narrower: the
substrate's state is available to the model as a modulation signal, and the
carrier learns to use it.

## 5. The trillion-token question

RES-313 establishes that the composed system cannot carry trillion
distinguishable items in a single hypervector. `C_total` is bounded by
`C(dim)`, at most a few hundred. So what does the modulation *do* at trillion
scale?

The answer is: it does not carry items. It carries a **projection**. The
streaming state is a running bundle of the stream's packets. Its capacity is
bounded, which means it is a lossy summary — a sketch. The carrier's job is to
learn a projection from that sketch to a modulation tensor that improves the
downstream model's task.

At trillion scale, the sketch is not a memory. It is a summary statistic. The
modulation is not "look up token 10^9." It is "here is a low-dimensional
signature of the current discourse segment, adjust the model's behavior
accordingly."

This is a weaker claim than "trillion-token modulation." It is the claim that
survives the capacity law. It is also the claim that is testable: train a
carrier on a downstream task with substrate modulation and without it, and
measure the difference.

## 6. Non-claims

- No speedup claim. The substrate is a side-channel, not a replacement for the
  model's own forward pass.
- No quality claim. The modulation may help, hurt, or be neutral. The interface
  is agnostic.
- No trillion-token recall claim. RES-313 rules that out.
- No architectural claim. The carrier is an MLP. It is not claimed to be
  optimal.
- No training-loop claim. The loop in §3 is one way to train the carrier.
  Others may work better.

## 7. The minimal experiment

The interface is defined, but untested. The minimal experiment that would
validate it:

1. Choose a small downstream model (e.g. a 2-layer transformer, `d_model =
   256`).
2. Choose a task (e.g. next-token prediction on a small corpus).
3. Train the model to convergence without modulation. Record the loss.
4. Freeze the model. Train a carrier with modulation. Record the loss.
5. Compare.

If the modulated loss is lower, the interface provides signal. If it is not,
the substrate's state is not useful to this model on this task.

The experiment is small. It is not a trillion-token test. It is the first test
of whether the modulation path is informative at all.

## 8. Open questions

- **Which surface?** Embedding bias is the least invasive, but also the least
  expressive. Per-layer gating is more expressive but changes the model's
  internal dynamics. Which is right depends on the task.
- **Carrier capacity.** The carrier is an MLP with `O(dim^2)` parameters. Is
  that enough to project a bounded sketch into a useful modulation? Or does the
  projection need a learned dictionary?
- **The sketch's content.** What does `stream_hv` actually contain after a
  trillion tokens? RES-313 says at most a few hundred distinguishable items.
  Which items? The most recent? The most frequent? The most task-relevant? The
  state does not decide. The carrier learns to read whatever is there.
- **The negative result.** If the minimal experiment shows no improvement, the
  modulation interface is not useful. That is a valid outcome. It would mean
  the substrate's state, however well-behaved, does not carry task-relevant
  information at the scale the downstream model can use.
