# Chroma orientation and compression

The Human Belt is five chroma channels: two dyadic (black, white) and
three triadic (red, blue, yellow). A compact code packs belt, scale
level, residual bin, and those five weights into a small struct
(`CODE_BYTES`). Variations are produced by rotating the belt,
permuting the triadic axes, and stepping hue with 2π·frac(step·φ).
An optional pass also walks the four orientation scales. No frame is
rendered during expand.

The point is more variation at less cost than storing or painting a
naive frame for each palette. `measure_variations` compares code
bytes and counted expand ops against naive frame bytes and pixel
writes, and records real timings. This path does not add a video
provider; video stays `UNAVAILABLE` with `url` null when no provider
is configured.

Studio and visual paths still never call learn, never update the scar
matrix, and never write Titanos.

Code: `src/resileos/ui/chroma.py`.
