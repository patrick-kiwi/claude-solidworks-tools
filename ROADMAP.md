# Roadmap: techniques to prove next

Agreed with the user on 2026-11-13. Work top to bottom; each item follows the CLAUDE.md
"adding a technique" loop (look up with `scripts/sw_api.sh` -> prototype in a throwaway part
with an exactly computable result -> `swlib.py` with gotchas in the docstring -> selftest case
-> SKILL.md), and gets its own commit. API names below are starting points to look up, not
verified signatures.

**Deliberately not planned:** STL/STEP export. The user exports by hand after reviewing the
model in SolidWorks - that review is the point. Builds should end by inviting a review.

## 1. Close-up images (zoom to area) - DONE

`snap(name, view, box=...)` / `snaps(..., box=)` + `pixel(point)` + `scripts/pngread.py`.
Proven in selftest: edge lines of a 0.5 mm slot land within ~1 px of the prediction in *Front,
*Right, *Top, *Isometric and inside a section, and a 0.5 mm gap between assembly components
measures 121 px at 242 px/mm. Trap found: `ViewZoomTo2` takes view-frame coordinates, not
model space (correct by accident in *Front only).

Why: the last two eval agents both wanted it - a 0.15 mm lid gap or a 0.26 mm taper is
invisible when the view frames the whole model. Also needed to judge items 2-4 by eye.

- Goal: `snap(name, view, box=(xmin, ymin, zmin, xmax, ymax, zmax))` (or a `zoom=` window) that
  frames a model-space region, usable inside `section()`.
- Look up: `IModelDoc2.ViewZoomTo2`, `IModelView.Scale2` / `Translation3`, `ViewZoomtofit2`.
- Prove: render a known gap (e.g. two blocks 0.5 mm apart in an assembly, or a 0.5 mm slot) and
  measure it in pixels from the PNG (Python/PIL on the Windows side or numpy in WSL); the
  pixel width / framed width must match. Check it works for parts, assemblies and with a
  section active.

## 2. Sketching on Front/Right Plane and on offset reference planes - DONE

`extrude/cut(reverse=)`, `cut(both=)`, `p.plane(name, base, offset)` (hidden after creation,
position asserted from its transform). Proven by bbox in selftest: bosses go +normal and cuts
-normal from Top/Front/Right, both swapped by `reverse`; offset planes (positive, negative,
chained) land where asked; two-way cuts are exactly 2x. Traps found: swlib's old `flip` was
FeatureExtrusion2/FeatureCut4's "flip side to cut" (no-op on a boss) - the direction is the
next argument; the "Top Plane cut fails" trap below was the -Y cut direction, fixed by
`reverse=True`; new planes show up in renders unless hidden.

Why: foundation for revolves and lofts (both sketch on vertical / offset planes).

- Front Plane = XY (normal Z), Right Plane = YZ (normal X): prove the sketch transform
  (`Part._s` already converts model -> sketch coordinates via `ModelToSketchTransform`; check
  the assertion that points lie on the plane still holds) and which way `extrude`/`cut` go
  from each plane, with and without `flip`. Prove by bbox, not just volume.
- New: `p.plane(name, base="Front Plane", offset=30)` -> offset reference plane, then
  `select_plane(name)`. Look up `IFeatureManager.InsertRefPlane` and the
  `swRefPlaneReferenceConstraints_e` enum (distance constraint, flip). Prove the plane is at
  +offset (not -offset) by sketching on it and extruding a boss with a known bbox.
- Known trap: a through-all cut sketched on a plane lying exactly on a face boundary fails (hit
  in this session with Top Plane at Y=0) - sketch on the face instead, or document.

## 3. Revolves (boss and cut) - DONE

`p.centreline(p1, p2)`, `p.revolve(name, deg, reverse, symmetric)`, `p.revolve_cut(...)`,
`p.polyline(points)`, `revolve_volume(area, centroid_r, deg)`. Proven in selftest by Pappus
(tube, cone touching the axis, torus about an off-origin axis, 360 and 90 deg grooves, L-shaped
polyline extrude, all to 1e-3 mm^3) and by bbox (partial angles on all three planes). Findings:
partial angles follow the right-hand rule about the centreline's p1 -> p2 direction, cuts too;
with two centrelines SolidWorks silently uses the first (so swlib allows one per sketch); no
centreline -> fails even if a profile edge lies on the axis; a profile crossing the axis fails.

Why: knobs, round spacers, caps, bushings, grooves.

- Sketch a closed profile plus a centreline (axis) on Front Plane; revolve 360 deg (and a
  partial angle). Look up `IFeatureManager.FeatureRevolve2`, `ISketchManager.CreateCenterLine`.
- Prove by Pappus: volume = 2*pi * (profile centroid distance from axis) * profile area. A
  rectangle offset from the axis gives a tube (pi*(R^2 - r^2)*h) - exact and easy. Revolved
  cut: a rectangular groove in a cylinder.
- Add a `revolve_volume(area, centroid_r, deg=360)` helper next to the other volume helpers.

## 4. Polygons and lofts (the user's circle-to-hexagon example) - DONE

Lofts DONE: `p.end_sketch(name)`, `p.loft(name, [sketches], align=None)`, `p.loft_cut(...)`,
`loft_volume(corners0, corners1)`; `bbox()` now tight (`GetExtremePoint`). Proven in selftest
(15 cases): square frustum (exact, and a mid-height section close-up lands within 1 px),
deliberately twisted pairing = `loft_volume`, circle -> circle cone frustum, circle -> hexagon
(between prism and cylinder; *Top close-up of both ends to 1 px), 6-corner square -> hexagon
(exact), three collinear squares (exact), three-profile barrel (widest exactly at the middle
profile), rounded rectangles on Front Plane (Simpson), loft cut socket (exact). Findings:
- Pairing comes from the pick point; without one, SolidWorks pairs by sketch order, and
  `rect()`/`polyline()` wind oppositely on some planes -> silent twist (3333 vs 4667 mm^3).
  Picks at corresponding corners fix any winding, so `loft()` always picks (auto: the corner
  pointing the same way from each profile's centre). A circle's pick makes no difference.
- Two profiles -> ruled loft; Simpson with the corner-midpoint polygon is exact, even twisted.
- Square -> hexagon (4 vs 6 corners) twists into curved faces; give both the same count.
- SolidWorks' volume of lofted ROUND faces is 4e-5..1e-4 low, even when the face is an
  exact cone/cylinder (ConeParams checked); planar lofts and revolves are exact.
- `GetBodyBox` pads spline bodies (+-13 for a true +-12); `GetExtremePoint` works under late
  binding as `ok, x, y, z = body.GetExtremePoint(dx, dy, dz)`.

Polygons DONE: `p.polygon(centre, sides, radius= | flats=, toward=)` draws via `polyline()`
and returns the corners; selftest checks hexagon (radius, Top), hexagon (across flats, Front)
and pentagon (Right) by exact volume and bbox. Finding: `CreatePolygon`'s Inscribed flag
changes nothing (the point is always a corner, both settings measured identical) and it adds a
construction circle - not used.

Why: transitions between different cross-sections - knob with a hex socket, funnels, nozzles,
round-fan-to-rectangular-vent ducts, tapered handles.

- Starting point from item 3: `p.polyline(points)` (closed, straight-sided) is already proven,
  so `polygon()` can simply compute its corners and call it - a fallback if
  `CreatePolygon` turns out awkward under late binding (it also adds a construction circle).
  Lofts from Top Plane to an offset plane (`p.plane("P", "Top Plane", h)`) stand upright like
  the revolve tests, and a revolved cone frustum (`revolve()` of a trapezoid) is a cross-check
  for the circle -> circle loft.
- `p.polygon(centre, circumradius or inradius, sides, angle)` - look up
  `ISketchManager.CreatePolygon`. Prove: extruded hexagon volume = (3*sqrt(3)/2) * R^2 * h.
- Loft between profiles on parallel planes (item 2): look up
  `IFeatureManager.InsertProtrusionBlend2` / `InsertCutBlend`, and how profiles are
  selected (selection marks; order matters).
- Prove with exactly computable lofts first: square -> smaller concentric square (frustum),
  circle -> circle (cone frustum: pi*h/3*(R^2 + Rr + r^2)). Then circle -> hexagon: no closed
  form, so check volume lies between the obvious bounds, end faces match the profiles (bbox,
  section), and look at close-ups.
  Images can be proof too, not just a look: `snap(box=...)` + `doc.pixel(point)` predict
  where an edge must land, and `scripts/pngread.py` (`read_png`, `dark_runs`) finds where it
  did, to ~1 px (see `closeup()` in selftest.py). Use it for the loft's shape, e.g. the
  silhouette width of a section at mid-height, or the hexagon's corners in a *Top close-up.
- Expected trap: SolidWorks pairs the profiles' points by where each profile is selected, so a
  bad pick twists the loft. Find out how to control it (pick points / connectors /
  start-point alignment) and build that into the helper.

## 4b. Iteration-5 eval fixes - DONE (selftest 77 -> 89)

From the six agents' skill_issues.md (iteration 5, incl. the new round-to-rect duct case):
- **Circle -> polygon/rect lofts are not ruled** - no exact volume. The duct agent's pairing
  rule (each corner to the circle point in the same direction) matched its own part to 3e-4
  but is off by up to 6e-3 on a sharp 2.4:1 rectangle; arc-length pairing is worse. Kept as
  `circle_loft_estimate()`, an upper bound SolidWorks reads 0.03-0.6% under (8 lofts/cuts).
  The circle's pick point and the loft direction make no difference (identical volumes).
- After a loft, exact features read up to ~2e-6 of the whole part's volume off (0.8 mm^3 on
  a 0.5 L part, even an extrude that doesn't touch the loft); cuts measured exact.
- Floor shadow/reflection: `ISwScene.FloorShadows/FloorReflections` via
  `doc.GetActiveConfiguration.GetScene`; snap() turns both off (parts and assemblies). Turning
  the shadow back on afterwards does not bring it back in renders.
- `read_png()` takes snap()'s /mnt/c path under Windows Python; `assert_box()`,
  `Part.edge_extent()`; docs for the hollow-loft recipe and wall thinning on slopes.

## 5. Shell (hollow a solid to a wall thickness) - NEXT

Why: every box/enclosure build so far makes the cavity by hand ("outer body minus a cut").
A shell with the top face removed is one call, and it hollows lofted or revolved shapes
(a funnel, a knob, a duct) where a hand-made cavity would need a second matching loft.

- Look up: only `IModelDoc2.InsertFeatureShell(Thickness, Outward) -> Void` (2026 install;
  `sw_api.sh 'IModelDoc2.InsertFeatureShell*'`). It returns nothing, so success must be
  checked from the feature tree (`FeatureByPositionReverse(0)` type/name) and the volume.
  Faces to remove are pre-selected (`select_face`, append with mark?) - find out whether it
  needs a mark, and what happens with no face selected (a closed hollow body?).
- Prove exactly: a 40 x 30 x 20 block shelled 2 mm with the top face open removes
  (40-4)(30-4)(20-2) mm^3; outward=True grows the bbox by 2 mm per side instead. Then a
  rounded-rect block (inner corner radius = r - t, so `rr_area` gives the cavity exactly),
  a shelled revolve (Pappus) and a shelled frustum loft (`loft_volume` of the inset corners -
  check whether SolidWorks' inset is a true offset; for a tapered wall it is not a plain
  corner inset, so prove on the box first).
- Check with a section close-up (`with p.section("Z"): p.snap(..., box=...)` + `pixel()`):
  the wall must measure t px-exactly on both sides and on the floor.
- Expected traps: thickness >= a fillet/corner radius on the inside fails or builds a
  different shape (cf. the over-size fillet finding); shelling after fillets vs before.
- Then: rewrite `examples/tapered_lid_box` or `rpi_enclosure` cavity with it only if it
  keeps every existing check passing - otherwise just document.
- The duct adapter is the motivating case: hollowed by hand (bores + inner loft cut) its wall
  is t*cos(slope) square to the sloping sides (1.86 mm for 2 mm at 22 deg). A shell with both
  end faces removed should give a true normal t - check with a mid-height section close-up
  (no exact volume exists for a circle -> rect loft, so prove the shell on boxes/frustums
  first). Then add an eval case or re-run `round-to-rect-duct-adapter` to see if agents use it.

## Later candidates (not yet ordered)

- **Patterns**: linear and circular (`FeatureLinearPattern5`, `FeatureCircularPattern5`) - vent
  slot arrays, bolt circles. Exact: n x feature volume.
- **Mirror** (`InsertMirrorFeature2`) about a reference plane.
- **Sweep** along a path (`InsertProtrusionSwept4`/`FeatureSweep`) - handles, cable channels.
- **Rib** (`InsertRib`) - stiffeners in enclosures.
- **Countersunk / counterbored holes**: a countersink might already work as a cut with 45-deg
  draft (cone volume is exact) - prove before reaching for the Hole Wizard.
- **Tangent loft ends / blended transitions**: a "smooth transition" duct meets its collars
  with an 11-22 deg crease. Try loft end tangency (`InsertProtrusionBlend2` start/end
  tangency args) or extra profiles equal to the collar ends a few mm into the loft; check by
  a section image (no exact volume). Iteration-6 duct agent.
- **`measure_gap(p0, p1)` close-up helper**: nearest dark run to each `pixel()` prediction,
  in mm - three agents wrote ~15 lines of this; prove against the selftest's slot/gap
  close-ups.
- **Mid-plane extrude** (`END_MID_PLANE` already used by revolves): an L-bracket agent had to
  make an offset plane just to centre a profile on Front Plane.
- **Section views that are easier to read**: cut faces render the same grey as the faces
  behind them (perfboard agent); a colour per component or on the cut face would help.
- **Section profile from geometry** (intersect the body with a plane, e.g. a temporary split
  or `IBody2` methods): measure a loft's cross-section without image work (duct agent).
- **SKILL.md size** (461 lines, ~31 KB): a simple-part agent found it long. If it passes ~500
  lines, move Revolves/Lofts/Draft detail into `references/` with pointers.
- **Editing the user's existing files**: highest value, highest risk given "never modify the
  user's documents" - design first (work on a copy saved under solidworks_work?), then prove.
