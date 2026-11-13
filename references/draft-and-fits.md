# Draft and tapered fits

Read this before drafting walls (`draft_deg=` on `extrude`/`cut`) or designing a tapered,
press-fit or friction lid.

`draft_deg` on `extrude`/`cut` tapers the side walls by that angle from the sketch plane. Over
depth `d` the profile insets by `d*tan(angle)` - corner radii shrink by the same amount. Use it
for mould-style draft and for **tapered fits**: give a lid lip and the box's seat the same
drafted profile and they meet over their full height only when fully closed, which tolerates
3D-printing error far better than parallel vertical walls (lifted by `h`, the gap is
`h*sin(angle)`). `examples/tapered_lid_box/` builds exactly this, with the matching checked.

Real prints are never exact, and a taper turns a size error into a height error: a lip
oversize by `e` per side seats `e/tan(angle)` higher (0.1 mm at 3 degrees -> 1.9 mm). So decide
with the user what stops the lid, and say which you chose:
- **Rim stop** (default for boxes): the lid plate rests on the rim, and the lip is made
  undersize by a clearance `c` per side (inset its sketch by `c`). The taper guides and centres
  the lid on the way in; the rim sets the closed height; play is at most `c`. Try c = 0.1-0.2 mm.
- **Wedge fit**: leave a gap between plate and rim so the tapers themselves stop the lid - a
  snug friction fit that absorbs size error as a small height change. Use a shallow angle for
  grip, a steeper one for less height variation.
Expose the clearance as a named constant so it can be tuned after a test print.
