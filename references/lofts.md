# Lofts (transitions: circle to hexagon, funnels, nozzles, ducts, tapered handles)

Read this before any `loft()` / `loft_cut()`. Hollow transitions also need `shell.md`.

Sketch each cross-section on its own parallel plane, close each sketch with `end_sketch()`
(no feature), then loft through them in order:

```python
p.select_plane("Top Plane"); p.start_sketch()
p.circle((0, 0, 0), 10); base = p.end_sketch("Round end")
p.plane("Hex level", "Top Plane", 20)
p.select_plane("Hex level"); p.start_sketch()
hexagon = p.polygon((0, 20, 0), 6, flats=17); top = p.end_sketch("Hex end")   # polygon returns corners
p.loft("Circle to hex", [base, top])
```

- **Twist is the trap.** SolidWorks pairs the profiles' corners from where each is picked;
  left to itself it pairs them by how each sketch was drawn, and `rect()` and `polyline()`
  wind opposite ways on some planes - the loft then twists silently (a square frustum came
  out 3333 mm^3 instead of 4667). `loft()` therefore always picks: by default the corner of
  each profile that points the same way from its centre as the first polygon's first corner,
  which is right for similar shapes (square -> smaller square, rounded rectangle ->
  smaller rounded rectangle, circle -> polygon - a circle's pick makes no difference). For anything else
  pass `align=[a corner of each profile]` (model mm) naming the corners that belong together.
- **Same number of corners**, or one end a circle. A square -> hexagon loft twists into
  curved faces; draw the square as a 6-point `polyline()` (extra corners on two sides) so
  each hexagon corner has a partner.
- **Two profiles make a ruled loft** (straight lines between paired corners), so polygon
  lofts are exact: `loft_volume(corners0, corners1)` with the corners in paired order (the
  frustum formula generalised; true for twisted pairings too). Three or more profiles give a
  smooth loft through every profile - a fat middle profile makes a barrel whose widest point
  is exactly that profile (tight `bbox()` confirms).
- **Round faces read slightly low**: SolidWorks' volume for lofted round faces (circle ->
  circle, rounded rectangles) is 4e-5..1e-4 below the exact value even when the face is an
  exact cone - compare those with a relative tolerance (`tol=want * 2e-4`). Planar-faced lofts
  are exact. Once a body has a lofted face, *later* exact features read up to ~2e-6 of the
  whole part's volume off (0.8 mm^3 on a 0.5 L duct, even away from the loft): use
  `tol=1e-5 * p.volume()` for them.
- **Circle to polygon or rectangle has no exact volume** - the surface is not ruled, so don't
  hunt for a formula (an agent spent minutes on one that held only for its own shape).
  `circle_loft_estimate((centre, radius), profile, r)` gives an upper bound: SolidWorks read
  0.03-0.6% below it on 8 lofts and loft cuts (most for an elongated, sharp-cornered end).
  Assert `0 < 1 - got/est < 0.01` - it catches a wrong size, height or profile - and check
  the shape with a section close-up. These lofts can't twist: the circle's pick point and the
  loft direction gave identical solids.
- Loft cuts: sketch the mouth on the part's face and the floor on a plane inside it, then
  `loft_cut()` - e.g. a tapered hex socket.
- **Hollow transitions** (ducts, funnels, adapters with collars): build the outside solid
  first (collar extrude, loft, collar extrude), then `shell()` it with both end faces open -
  the wall is t square to every face, sloping ones included. (The hand-made way - bores plus
  an inner `loft_cut()` with profiles inset by t - leaves only `t*cos(slope)` on sloping
  sides: 1.86 mm for 2 mm at 22 degrees.) Check the walls with a section close-up measured by
  `pixel()`.
- Proven only between profiles on parallel planes, one closed contour per sketch, with no
  guide curves or end tangency; the library refuses other cases.
