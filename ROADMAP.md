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

## 3. Revolves (boss and cut)

Why: knobs, round spacers, caps, bushings, grooves.

- Sketch a closed profile plus a centreline (axis) on Front Plane; revolve 360 deg (and a
  partial angle). Look up `IFeatureManager.FeatureRevolve2`, `ISketchManager.CreateCenterLine`.
- Prove by Pappus: volume = 2*pi * (profile centroid distance from axis) * profile area. A
  rectangle offset from the axis gives a tube (pi*(R^2 - r^2)*h) - exact and easy. Revolved
  cut: a rectangular groove in a cylinder.
- Add a `revolve_volume(area, centroid_r, deg=360)` helper next to the other volume helpers.

## 4. Polygons and lofts (the user's circle-to-hexagon example)

Why: transitions between different cross-sections - knob with a hex socket, funnels, nozzles,
round-fan-to-rectangular-vent ducts, tapered handles.

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

## Later candidates (not yet ordered)

- **Shell** (`InsertFeatureShell`): hollow a solid to a wall thickness - would replace the
  "outer body minus cavity" pattern in the box examples. Exact check: outer minus inner volume.
- **Patterns**: linear and circular (`FeatureLinearPattern5`, `FeatureCircularPattern5`) - vent
  slot arrays, bolt circles. Exact: n x feature volume.
- **Mirror** (`InsertMirrorFeature2`) about a reference plane.
- **Sweep** along a path (`InsertProtrusionSwept4`/`FeatureSweep`) - handles, cable channels.
- **Rib** (`InsertRib`) - stiffeners in enclosures.
- **Countersunk / counterbored holes**: a countersink might already work as a cut with 45-deg
  draft (cone volume is exact) - prove before reaching for the Hole Wizard.
- **Editing the user's existing files**: highest value, highest risk given "never modify the
  user's documents" - design first (work on a copy saved under solidworks_work?), then prove.
