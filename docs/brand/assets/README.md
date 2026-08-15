# Scenara brand assets

Use `scenara-mark.svg` on light surfaces and `scenara-mark-inverse.svg` on dark
surfaces. Both preserve the official violet, electric-blue, and cyan ribbon
gradients. `scenara-mark-mono.svg` inherits `currentColor` for one-color output.
The app icon uses its fixed midnight background; no other asset adds a
background container.

## Geometry baseline

The current source geometry is fixed to the 64 x 64 view box:

- The vertical axis is `x = 32`.
- The four-point center star is centered at `(32, 32)`.
- The upper/left ribbon is offset by `-3` units on the y axis.
- The lower/right ribbon is the same master curve rotated 180 degrees around
  `(32, 32)` and offset by `+3` units on the y axis.

All supplied variants use this same geometry. The application icon and favicon
apply only their own background and scale. Do not create a second hand-tuned
path, move the center star with a ribbon, or alter the ribbon gap in a product
surface.

- Mark clear space: at least 16 units in the 64-unit source view box.
- Mark minimum size: 24 px digital and 8 mm print.
- Horizontal wordmark minimum width: 120 px digital and 32 mm print.
- Vertical wordmark minimum width: 88 px digital and 24 mm print.
- Do not crop, recolor, rotate, stretch, outline, shadow, change the ribbon gap,
  or alter the supplied gradients.
- Use `Scenara 景枢` in product presentation and `Scenara` in compact technical UI.
- Use the brand line `连接视觉 · 理解世界` only in presentation contexts, not in compact product controls.
