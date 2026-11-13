# Revolves (round parts: knobs, spacers, bushings, caps, grooves)

Read this before any `revolve()` / `revolve_cut()`.

Sketch the half cross-section on a plane that contains the axis, draw the axis with
`centreline()`, and revolve. For a part standing on Top Plane, use Front Plane and the Y axis:

```python
p.select_plane("Front Plane"); p.start_sketch()
p.centreline((0, 0, 0), (0, 1, 0))                       # axis = model Y
p.polyline([(0, 0, 0), (15, 0, 0), (15, 8, 0), (12, 12, 0), (0, 12, 0)])   # knob half-section
p.revolve("Knob")                                         # 360 deg
p.select_plane("Front Plane"); p.start_sketch()
p.centreline((0, 0, 0), (0, 1, 0))
p.rect((14, 3, 0), (16, 5, 0)); p.revolve_cut("Grip groove")   # may stick out past the surface
```

- The profile may touch the axis (a solid knob, a cone) but must not cross it - that fails.
  It must have its own centreline: a profile edge lying on the axis is not enough.
- **One centreline per sketch.** With two, SolidWorks silently revolves about the first one
  drawn; `centreline()` refuses a second.
- **Partial angles turn by the right-hand rule** about the centreline's direction p1 -> p2:
  about +Y, a profile at +X swings toward -Z; about +X, +Y swings toward +Z; about +Z, +X
  swings toward +Y. Draw the centreline the other way or pass `reverse=True` to turn the
  other way; `symmetric=True` puts half the angle each side of the sketch plane. Cuts turn
  the same way as bosses. All bbox-verified on Front, Right and Top Plane.
- Check every revolve by Pappus: `revolve_volume(area, centroid_r, deg)` = area x centroid
  distance from the axis x angle - a rectangle spanning radii r0..r1 has its centroid at
  (r0 + r1)/2; a triangle's is the mean of its corners. Exact to 1e-3 mm^3 in the selftest
  (tube, cone, torus about an off-origin axis, groove, partial cuts).
