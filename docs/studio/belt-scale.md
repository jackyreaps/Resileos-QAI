# Belt scale (visual matrix control)

The belt scale is matrix control for the visual path, implemented in
`src/resileos/ui/belt_scale.py`. The same pentagram figure is used at
every scale, with phi as the proportion. Only the frame changes. This
module does not build images, call learn, or write a scar.

## Scales

| Scale          | Frame | Orientation | Belt (index) |
| -------------- | ----- | ----------- | ------------ |
| local          | 3     | edge        | 0            |
| sun_earth_moon | 5     | near triad  | 1            |
| orion          | 9     | outer mark  | 2            |
| north_star     | 12    | pole        | 3            |

`matrix_control("orion")` returns belt 2, frame 9.

## The word "belt" here

The `belt` field on this control is the scale's index in the list
above. It is not the 5-mod Human Belt in the [five-pin](../200-core/five-pin.md)
construction, which is always 5 (2 dyadic + 3 triadic). The name
`local` also differs: five-pin `local` is the hub pin at frame 5;
belt-scale `local` is the edge scale at frame 3.

## Residual embed

`embed_frame(arr, scale="orion")` reads this control and sets the
cascade address (`belt` / `frame` / residual path) from it. The pixel
matrix is not changed. `suite_residual` still receives the original
`belt` argument, so `residual_bin` does not shift just because a
scale was named. With `scale` omitted or empty, `embed_frame` matches
its previous behavior, including the same dict keys.
