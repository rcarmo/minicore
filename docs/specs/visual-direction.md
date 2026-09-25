# Minicore visual direction

Minicore uses a network workbench for a fixed IP troubleshooting simulator.

The main graph is always 3D with a shallow oblique camera. Diagnostic detail stays in 2D panels, tables and inspectors. The layout, colour system, labels, motion and inspector design remain specific to Minicore.

## Visual model

Use a restrained network workbench:

- shallow oblique 3D camera, not a free-floating cloud;
- deterministic horizontal role bands for packet endpoints, access edge, provider edge and provider core;
- stable topology coordinates with no continuous force simulation;
- compact device glyphs and direct labels;
- straight or gently routed links for physical and logical relationships;
- protocol overlays on demand without changing the base layout;
- persistent header for lab identity, freshness and connection state;
- docked and floating 2D panels for evidence rather than card walls.

Decorative depth must never make links harder to trace or suggest topology that is not observed.

## State language

Colour communicates only defined operational state and always has a second cue:

- up or available;
- degraded;
- down;
- unknown or unavailable;
- stale;
- selected.

Expected but unobserved elements use distinct dashed or outlined treatment. Collection failure is not network failure. God ground truth is an explicit source-labelled annotation in God view only.

## Activity and accessibility

The synthwave activity ring is narrow, local to one node and independent of health, selection and labels. It does not create traffic animation or a glow-heavy scene.

Keep all inspector operations keyboard accessible, honour reduced motion, provide a structured list or table fallback, and give a clear fallback when WebGL is unavailable.
