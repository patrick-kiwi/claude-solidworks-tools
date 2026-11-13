# Shell (hollow a solid: open boxes, cups, funnels, ducts)

Read this before any `shell()`. Measuring the wall in images: `measuring-images.md`.

Model the outside as a solid, then `p.shell("Shell", t, open_faces)` - each open face given
like `select_face` (a point inside it and its outward normal):

```python
p.shell("Shell", 2, [(0, H, 0, "+Y")])                    # open-top box, 2 mm walls and floor
p.shell("Shell", 2, [(0, 0, 0, "-Y"), (0, L, 0, "+Y")])   # duct/tube: both ends open
```

- **Inward (default) every remaining face moves in by exactly t, square to itself**, the
  outside stays put. A W x D x H block open at the top loses (W-2t)(D-2t)(H-t); a rounded
  corner or fillet of radius r is r - t inside, and simply sharp when t >= r (no failure,
  exact). On sloping lofted/revolved sides the wall is t square to the slope (a duct measured
  2.00 mm), unlike hollowing by hand. To check a shelled frustum, move each side plane in by t
  (the inner half-width shifts by `t*sqrt(1 + slope^2)`, not t) - exact in the selftest.
- `outward=True` keeps the solid you drew as the *cavity* (e.g. a sleeve round a part's
  exact shape); walls grow outside it and the bbox grows by t except at the open faces.
- **Order matters.** Fillet the outside edges first, then shell - the wall stays uniform. Cut
  holes and openings AFTER the shell: a hole cut before it gets its own wall (a through hole
  became a 2 mm tube standing in the cavity).
- **Check a shelled loft by its wall, not its volume** - there is no exact volume, and
  "t x half the surface area" read 0.26% off a duct whose wall sampled exactly 2.000 mm. Measure
  the wall in section close-ups instead: the outer edge at two rows gives the slope, then
  wall = horizontal width x cos(slope) (the duct case near the end of `scripts/selftest.py`).
- A shell too thick for the part adds nothing; `shell()` raises. Open faces must be flat and
  pickable from outside (same rule as `select_face`).
- Prefer it to "outer block minus a cavity cut" when the cavity must follow a curved or
  sloping outside; the hand-made cavity is still fine (and easy to reason about) for plain
  boxes with features that differ inside and out.
