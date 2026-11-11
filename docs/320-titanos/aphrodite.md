# Aphrodite

Preferences, care weights, and a persona. Aphrodite does not write residual facts.

`GET` and `POST /api/v1/aphrodite/{hub}/state`, `POST /api/v1/aphrodite/{hub}/preference`, `POST /api/v1/aphrodite/{hub}/reset`.

Chat lines `I like X` and `I don't like X` update the preference map. A tutorial fragment is attached only when that step is verified.

Legions on Aphrodite: Calliope (next fragment from the preference map and a residual hash), Ligeia (suggestion only), Echo (lesson only, via Hades).

A verified Kin cycle stores `AphroditeState` on the Hades checkpoint `extra` field and may attach `tutorial_fragment`.
