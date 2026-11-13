---
name: solidworks
description: Drive the user's running SolidWorks from WSL/Linux - build parts and assemblies from Python scripts via the COM API (sketches, extrudes, cuts, revolves, lofts, shells, draft/taper, fillets, chamfers), then check the result with rendered images, exact volumes and interference detection. Use this whenever the user wants something modelled, designed or built in SolidWorks or "in CAD" (enclosures, boxes, brackets, mounts, plates, spacers, knobs, bushings, funnels, nozzles, duct transitions, lids, tapered or press-fit lids, cases for a PCB or Raspberry Pi/Arduino, parts for 3D printing), wants edges rounded or two parts checked for fit, or mentions SolidWorks, SLDPRT or SLDASM files - even if they don't say "SolidWorks" and just ask you to "make a part" or "design a case".
---

# SolidWorks via COM

SolidWorks runs on the Windows host. From WSL you can run Windows executables, so a **Windows**
Python with pywin32 attaches to the running SolidWorks over COM and drives its API. `scripts/`
holds a small library (`swlib.py`) that wraps the API in millimetre, model-space calls and has
the hard-won fixes built in, plus a runner (`sw_run.sh`) that executes a build script under
Windows Python with `swlib` importable.

You can't watch the screen, but you are not blind: `snap()` renders the model to PNG and you
Read the image; `report()` gives volume, bounding box and the feature list; assemblies have
interference detection. Use all of them - every bug in the original build session was caught
this way, and one was invisible to the numbers alone.

**Proven scope:** parts built from rectangles (optionally rounded), circles, regular polygons
and other straight-sided profiles (polylines) sketched on Top,
Front or Right Plane, offset planes parallel to them, or flat axis-aligned faces; extrudes
(either direction) and blind/through-all cuts (either or both directions), optionally drafted
(tapered); revolves and revolved cuts about a sketched centreline (full or partial angle,
either way or symmetric); lofts and loft cuts between polygon, rectangle and circle
profiles on parallel planes (e.g. circle -> hexagon, hollow circle -> rectangle ducts); shells
(hollowing to a wall thickness, faces left open, inward or outward); selecting edges by geometry; constant-radius fillets (convex and concave, single
edges or whole tangent loops) and 45-degree chamfers; assemblies placed by origin with
interference checks; section (cut-away) views and close-ups (zoom to a region, measurable in
pixels) for images. Every one of these is covered by `scripts/selftest.py` against exact
volumes or bounding boxes. Anything else (lofts with guide curves or end tangency, sweeps, angled sketch planes, drawings,
exports, editing the user's existing files) is untested - see "Going beyond the proven scope" below.

## 1. Preflight

```bash
S=<this skill's directory>/scripts     # the scripts/ folder next to this SKILL.md
$S/sw_run.sh $S/sw_status.py
```

This confirms SolidWorks is reachable and shows the active document. If SolidWorks isn't
running, ask the user to start it (don't try to launch it). The first run also locates a
Windows Python with pywin32 and caches it in `~/.config/solidworks-skill/python`.

Mind the user's work: you are driving *their* SolidWorks session. Never close, modify or save
over documents you didn't create. If the active document has unsaved changes, mention it - new
documents open alongside it and don't touch it, but the user should know you're about to be
busy in their session (they will see views spinning while you work).

## 2. Plan before scripting

Write the design down as a docstring at the top of the build script:
- **The frame.** Y is up. Sketch the footprint on "Top Plane" (the XZ plane, Y=0); it extrudes
  toward +Y. Profiles that belong in a vertical plane go on "Front Plane" (XY, Z=0, bosses grow
  +Z) or "Right Plane" (YZ, X=0, bosses grow +X), or on an offset plane (`p.plane(...)`).
  Centre parts on the origin where sensible - symmetry makes coordinates easy to
  check. Say which physical side faces which axis (e.g. "connectors face +Z").
- **Key dimensions as named constants** (wall, floor, clearances, hole pattern), with derived
  values computed from them, so a fix is a one-line change.
- **Real-world data** (board size, hole patterns, connector positions) with its source. If you
  are working from memory rather than a datasheet, say so to the user at the end.

## 3. Write the build script

Scripts can live anywhere (e.g. the user's project folder in WSL). CAD output and images go to
a Windows folder from `workdir()` (`%USERPROFILE%\solidworks_work\<project>`), because
SolidWorks saves reliably to local drives.

```python
from swlib import Part, Assembly, workdir
OUT = workdir("bracket")

with Part(OUT / "bracket.SLDPRT") as p:              # closes itself if the build throws
    p.select_plane("Top Plane"); p.start_sketch()
    p.rect((-30, 0, -15), (30, 0, 15), r=3)          # model-space mm, on the sketch plane
    p.extrude("Base", 4)                             # -> Y 0..4
    p.select_face(0, 4, 0, "+Y"); p.start_sketch()   # top face; normal must be stated
    for x in (-20, 20): p.circle((x, 4, 0), 2.6)
    p.cut("Mounting holes")                          # depth=None -> through all
    p.report(); p.save(); p.snaps("bracket")
```

Run it: `$S/sw_run.sh path/to/build.py` (output streams as the build runs). A box with a lid,
an assembly and a dozen images takes about 40 s; if yours may run past ~2 minutes, raise the
Bash tool's timeout (or run it in the background) rather than let it be cut off, and tee the
output to a log.

Each run creates the documents fresh. If the previous run's copy is still open, it is closed
first and discarded - together with any assembly from the same project folder that still holds
it (otherwise the new save would fail). `save()` confirms the file really landed on disk and
raises if not. A same-named document from a *different* folder is never closed - that is
probably the user's - so the build stops and asks for another name. So iterate by editing the
script and re-running, not by patching the open model.

Build the parts and their assembly in one script (as `examples/tapered_lid_box` does):
`Assembly.add` needs the parts open, and one run keeps them consistent.

When you finish, leave your documents open so the user can look at them in SolidWorks.

### API (all mm, model space)

| Call | What it does |
|---|---|
| `Part(save_as)` / `Assembly(save_as)` | New document from the default template; use as a context manager |
| `select_plane(name)` | Select "Top Plane", "Front Plane", "Right Plane" or a plane made with `plane()` |
| `plane(name, base="Top Plane", offset)` | Parallel reference plane `offset` mm along base's normal (negative = the other side; base can be another `plane()`); position asserted, hidden from renders |
| `select_face(x, y, z, "+X", append=False)` | Select the flat face through that point with that outward normal; verified |
| `start_sketch()` | Open a sketch on the selection |
| `rect(p1, p2, r=0)` | Axis-aligned rectangle from two opposite corners; `r` rounds corners (must be < half the short side) |
| `circle(centre, radius)` | Circle |
| `polyline(points)` | Closed straight-sided polygon through the points (don't repeat the first) |
| `polygon(centre, sides, radius=None, flats=None, toward=None)` | Regular polygon sized by circumradius or across-flats (hex keys, nuts); first corner points `toward` ('+X' or a vector; default +X on Top/Front, +Y on Right). Returns the corners |
| `centreline(p1, p2)` | The axis for a revolve, through two points on the sketch plane; one per sketch; direction matters for partial angles |
| `revolve(name, deg=360, reverse=False, symmetric=False)` | Boss: revolve the profile about the sketch's centreline. Partial angles follow the right-hand rule about p1 -> p2; `symmetric` splits the angle either side of the plane |
| `end_sketch(name)` | Close the sketch without a feature and name it - a profile for `loft()`; returns the name |
| `loft(name, [sketch, ...], align=None)` | Boss through the profiles in order; corresponding corners paired automatically (see Lofts) |
| `loft_cut(name, [sketch, ...], align=None)` | Cut the lofted region (tapered or circle-to-hex sockets) |
| `revolve_cut(name, deg=360, ...)` | Cut: remove what the revolved profile sweeps (grooves, bores); same direction rules |
| `extrude(name, depth, reverse=False, draft_deg=0)` | Boss along the sketch normal: outward from a face, +Y/+Z/+X from Top/Front/Right Plane; `reverse=True` the other way. Draft makes the profile shrink as it grows (`draft_outward=True` to grow) |
| `cut(name, depth=None, reverse=False, both=False, draft_deg=0)` | Cut AGAINST the sketch normal: into material from a face, -Y/-Z/-X from Top/Front/Right Plane; `None` = through all; `reverse=True` the other way; `both=True` both ways (depth each side). Draft makes the pocket narrow as it deepens |
| `shell(name, t, open_faces=[(x, y, z, "+Y"), ...], outward=False)` | Hollow the solid to wall `t`, leaving those faces open (none: closed hollow body); see Shell |
| `edges(where)` | Edge records (`kind`, `start`, `mid`, `end`, `radius`, mm) filtered by a predicate; helpers `e.lies_in("Y", 20)`, `e.along("X")` |
| `edge_extent(where, axis)` | (lo, hi) along an axis over the matching edges - e.g. a tapered seat's half-width at a height (exact on straight edges) |
| `fillet(name, r, edges, propagate=False)` | Constant-radius fillet; `propagate=True` follows tangent edges (one edge of a rounded-rect loop does the loop) |
| `chamfer(name, d, edges, propagate=False)` | 45-degree chamfer, `d` back along both faces; `propagate` as for fillets |
| `report()` | Rebuild; print features, body count, volume (mm^3), bbox (mm) |
| `bbox()`, `volume()`, `bodies()` | The same numbers, for asserts. `bbox()` is `(xmin, ymin, zmin, xmax, ymax, zmax)`, tight (also on curved loft faces), rounded to 0.001 mm; `bodies()` is a **list** (`len(p.bodies()) == 1`) |
| `rr_area`, `drafted_volume`, `fillet_volume`, `chamfer_volume`, `revolve_volume`, `loft_volume`, `circle_loft_estimate`, `assert_close`, `assert_box` | Volume and check helpers (module-level in swlib) - see 4. Verify |
| `snap(name, view)` / `snaps(prefix, views)` | Render PNGs next to the saved file; return and print the `/mnt/c/...` path to Read. `snaps("x")` names them `x_iso`, `x_front`, `x_right`, `x_top` (`_back`, `_left`, `_bottom`). Floor shadow and reflection are turned off, so what you see is geometry |
| `snap(name, view, box=(x0, y0, z0, x1, y1, z1))` | **Close-up**: zoom so that model-space box fills the image (any view, parts and assemblies, inside `section()`); prints px per mm. Only the box's extent across the screen matters - in `*Front` give both z values the depth of the detail (the face, or the section plane). `snaps(..., box=)` too |
| `doc.pixel((x, y, z))` | (column, row) of a model point in the last close-up - for checking a gap or position in the PNG |
| `with doc.section("Z", offset=0):` | Display-only cut-away for the snaps inside the block (parts and assemblies); hides the +axis side so *Front/*Right/*Top/*Isometric look at the cut face |
| `save(path=None)`, `close()` | Save as / close this document |
| `Assembly.add(part_path, origin)` | Insert an open part with its **origin** at `origin`; verifies placement |
| `Assembly.box(comp)` | A placed component's box (mm), for asserting e.g. that a lid is seated |
| `Assembly.bbox()` | Overall box of all placed components - assert it against the size the user asked for |
| `Assembly.interference()` | List of clash volumes; empty = no clashes |

Several features can go in one sketch (four standoff circles, seven vent slots) - one
`extrude`/`cut` then makes them all. Sketch points must lie on the sketch plane: for a face at
X=46 every point you pass has x=46 (the library asserts this).

### Views

| View | Looks along | Shows the face facing |
|---|---|---|
| `*Front` / `*Back` | -Z / +Z | +Z / -Z |
| `*Right` / `*Left` | -X / +X | +X / -X |
| `*Top` / `*Bottom` | -Y / +Y | +Y / -Y |
| `*Isometric` | from the +X +Y +Z corner | +X, +Y and +Z faces only |

The isometric view never shows the -X, -Z or underside faces. Put features the user will want
to see in a hero shot on +X/+Z/+Y faces where the design allows, and for everything else render
the orthographic view of that face.

### Selecting faces - the trap that cost the most time

`select_face` picks by casting a ray from the current view, and SolidWorks auto-rotates the
view whenever a sketch starts. A naive pick therefore grabs whatever face happens to be in
front - in the first session a "+X wall" pick silently returned the rim top, and the sketch
collapsed to nothing. The library turns to the view looking straight at the face, picks, and
checks the normal. What that means for you:
- Choose a point clearly inside the face, away from edges and existing holes.
- The face must be visible from outside along its normal. Inner faces (e.g. the inside of a
  box wall) are hidden behind the opposite wall and can't be picked this way - sketch on the
  outer face instead and cut through, or cut down from the top face.
- An assertion "picked the wrong face" means your point hit something else first; move it.

### Selecting edges (for fillets and chamfers)

Edges are found by geometry, not clicked: `p.edges(predicate)` lists every edge with its start,
mid and end points, and you keep the ones you mean. Describe them the way you would in words -
"the edge in the plane Y=20 along X at Z=-15":

```python
top_back = p.edges(lambda e: e.lies_in("Y", 20) and e.lies_in("Z", -15) and e.along("X"))
p.fillet("Top back fillet", 3, top_back)
rim = p.edges(lambda e: e.lies_in("Y", 30) and e.lies_in("Z", -25) and e.along("X"))
p.fillet("Rim fillet", 1, rim, propagate=True)     # one straight + propagate = whole rounded loop
```

- Print `p.edges()` when unsure what is there. Assert the count you expect before filleting:
  a filter that matches nothing, or two loops sharing a plane (e.g. the outer rim AND the
  cavity's top edge both lie in Y=H), is the usual mistake. Add `abs(e.mid[0]) < ...`-style
  conditions to separate them.
- To chamfer or fillet only the outer loop of a face that also has holes (the bottom of a
  plate), select one straight outer edge and `propagate=True`: the loop follows tangent edges
  round the corners and leaves the hole circles alone.
  `p.chamfer("Bottom chamfer", 1, p.edges(lambda e: e.lies_in("Y", 0) and e.lies_in("Z", -25) and e.along("X")), propagate=True)`
- Edge records go stale after every feature; call `edges()` again rather than reusing them.
- Fillet a concave edge (floor meeting wall) and SolidWorks adds material; a convex edge loses it.
- A fillet bigger than it can properly fit often does **not** fail: SolidWorks builds a
  different shape and the image looks right. Measured: r2 on the edge of a 1.5 mm plate, and
  a concave r1.5 floor fillet in a pocket with R1 corners, both "succeeded" with the wrong
  volume. Up to the limit is fine and exact: r equal to the plate thickness (r2 on a 2 mm
  plate), r equal to the corner radius. So keep r <= the height of the faces either side and
  <= the loop's corner radius, and let `fillet_volume` catch it when you don't. Only when the
  fillet can't be built at all does the feature return None (the library then raises).
- Do fillets last, after the cuts that define the edges; filleting first changes the edges
  later cuts and selections rely on.
- Vertical corners of a footprint are simplest rounded in the sketch (`rect(..., r=)`); use a
  fillet when the edge only exists after several features. A fillet whose radius equals an
  adjacent corner radius is fine (it blends into a spherical corner). So for "round all the
  outside edges 2 mm": sketch the footprint with corner r = 2, then fillet the top and bottom
  loops with r = 2 (a box's cavity corners can then be smaller than the outside ones).

### Draft (tapered walls)

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

### Sketching on reference planes

Faces are usually the easiest place to sketch, but some profiles live in a vertical plane or
at a height where no face exists yet. The rule is the same for planes and faces: **a boss
grows along the sketch normal, a cut goes against it** (Top Plane +Y, Front Plane +Z, Right
Plane +X - verified by bounding box both ways). Consequences:
- A cut sketched on Top Plane under a part standing on Y=0 goes -Y, away from the part, and
  fails - even through-all. Use `reverse=True`.
- For a hole through a part that straddles Front or Right Plane, use `cut(..., both=True)`;
  a one-way cut only removes the half behind the plane.
- `p.plane("Lid seat", "Top Plane", 30)` makes a plane at Y=30; sketch points on it need
  y=30. Bosses from it grow the base plane's way (+Y here), cuts go the other way.
- New planes are hidden so they don't clutter images (they'd also widen zoom-to-fit);
  selecting them by name still works.

### Revolves (round parts: knobs, spacers, bushings, caps, grooves)

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

### Lofts (transitions: circle to hexagon, funnels, nozzles, ducts, tapered handles)

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

### Shell (hollow a solid: open boxes, cups, funnels, ducts)

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
- A shell too thick for the part adds nothing; `shell()` raises. Open faces must be flat and
  pickable from outside (same rule as `select_face`).
- Prefer it to "outer block minus a cavity cut" when the cavity must follow a curved or
  sloping outside; the hand-made cavity is still fine (and easy to reason about) for plain
  boxes with features that differ inside and out.

### Design habits that avoid failures

- Blind cuts must reach material or the feature fails; when cutting a wall from outside, make
  the depth a little more than the wall (wall + 1) so it pierces cleanly.
- Sketch shapes may extend past the face's edge (e.g. a notch open at the top) - that's fine
  for cuts.
- Rounded slots: width 2 with `r=0.9`, not `r=1` (a zero-length straight edge breaks the sketch).
- Think about assembly, not just shape: in the first build, connectors overhanging the board
  edge would have collided with a closed wall cutout as the board dropped in, so the cutout was
  made open-topped. Check how things go together, not just whether the holes line up.

## 4. Verify - every time

A feature returning successfully only means SolidWorks made *something*. Check what it made:

1. **Numbers.** Compare `report()` against the design: bbox equals the intended outer size?
   Body count 1 (unless intended)? Put `assert`s in the script for the things that must hold.
   The strongest check is **exact volume per feature**: record `v = p.volume()` before a
   feature and assert the change equals the hand-derived value (a hole: pi*r^2*length; a
   fillet on a straight edge: r^2*(1-pi/4)*length; a chamfer: d^2/2*length; round a corner of
   radius R, the section area times 2*pi*(R - centroid offset) per full turn - offset d/3 for a
   chamfer, r(10-3pi)/(3(4-pi)) for a fillet). It proves a hole
   goes all the way through, a slot is the right depth, a chamfer actually happened - things
   no single image shows. swlib has the formulas, so don't re-derive them:
   `rr_area(a, b, r)` (rounded-rect area from half-extents), `drafted_volume(a, b, r, depth,
   deg)`, `fillet_volume(r, straight_len, corner_r)` / `chamfer_volume(...)` (a straight edge,
   or a whole rounded-rect loop with Pappus corners), `revolve_volume(area, centroid_r, deg)`, `loft_volume(corners0, corners1)` (shells: see Shell),
   `circle_loft_estimate(...)` (a bound, see Lofts), `assert_close(label, got, want)` and
   `assert_box(label, p.bbox(), want_box)`.
   `examples/tapered_lid_box/build.py` uses all of them.
2. **Images.** Read the PNGs. Pick the views for this part: an isometric plus the orthographic
   view of every face you cut or that features exit through (e.g. `*Bottom` to prove a hole
   goes all the way, `*Left` for holes in a -X face) - pass them to `snaps()`. Check each
   feature exists, is on the intended face, and is in the right place relative to the others
   (count the holes; see if the notch is open where you meant). Lighting still shades inner
   faces: a bright patch on a box floor under a side hole is light through the hole, not a
   feature. Images are rendered from the open
   model; only rely on (and show the user) images from your latest successful run - earlier
   runs' PNGs with other names are left in the folder.
   For anything inside - a lip in its seat, standoffs in a deep box, a blind hole's depth -
   render a section: `with p.section("Z"): p.snaps("x_section", ("*Front", "*Isometric"))`.
   It changes no geometry and costs a second or two, so don't build half-model copies.
   Place the cut through the feature (`offset`, mm along the axis) and not on a face - a cut
   that coincides with a wall face shows nothing useful.
   A whole-model image makes small details tiny: a 0.15 mm lid gap or a 0.3 mm taper step is
   invisible. For those, render a **close-up**: `p.snap("lid_gap", "*Front", box=(...))` frames
   that model-space box (give it a margin round the detail) and prints the scale, e.g.
   `1 mm = 212.8 px`, so a 0.15 mm gap should show as a ~32 px band - combine with a section
   to look at a fit from inside:
   ```python
   with a.section("Z", offset=5):                       # cut through the lip, not on a face
       a.snap("lip_closeup", "*Front", box=(38, 18, 5, 46, 24, 5))
   ```
   To measure rather than eyeball, `doc.pixel(point)` gives where a model point lands in the
   last close-up, and `scripts/pngread.py` (stdlib only; runs under WSL `python3` too) reads
   the PNG - `w, h, rows = read_png(p.snap(...))` works inside the build script (the path is
   converted) - and `dark_runs(grey_row(rows, y))` lists the black edge lines crossing row `y`.
   Edges land within about a pixel of `pixel()`'s prediction (verified in selftest). Take the
   dark run nearest each predicted edge, not every run in a window: edges *behind* a section
   cut show as lines too (e.g. where a bore's flat wall meets its corner arc, 2 mm inside a
   wall). Use one small close-up per measurement, a few mm across - a box spanning the whole
   part gives ~10 px/mm instead of ~100.
3. **Assemblies.** Check the component boxes (printed by `add`, or `Assembly.box(comp)` in an
   assert) are where you intended **before**
   trusting `interference()`. In the first session the interference check said "0 clashes"
   while the lid was floating 12 mm above the base - true, and meaningless. Only the image
   showed it. (`Assembly.add` now places by origin and verifies, but keep looking.)
   Decide what the user's stated size means (usually the closed outside size, lid included),
   say so, and assert `Assembly.bbox()` against it. A stand-in for the contents (a 1.6 mm
   plate for a PCB, sitting on the standoffs) lets `interference()` check the fit and shows
   the headroom.

If something is wrong, fix the script and re-run. If a failure is confusing, build a small
probe part that does just the failing step and inspect it (print the picked face's normal,
count sketch segments with `val(p.sm.ActiveSketch.GetSketchSegments)`), then close it.

## 5. Report to the user

Say what you built and where the files are (Windows paths), show or name the key images, and
be explicit about what is assumed rather than verified - e.g. connector positions taken from
memory, clearances never tested against the real part, untested print tolerances.

## Going beyond the proven scope

The SolidWorks API can do far more than `swlib` wraps. When a request needs something
unproven, tell the user that part is new ground, then work in small steps:

1. **Look the call up** instead of guessing: `scripts/sw_api.sh` reflects over the installed
   API assemblies and prints exact signatures and enum values, offline:
   `sw_api.sh 'IFeatureManager.*Chamfer*'`, `sw_api.sh -Enum '*FilletOptions*'`,
   `sw_api.sh -Enum '*' -Value EndCondBlind`.
2. **Prototype in a throwaway part** with a shape whose result you can compute exactly, and
   check the volume change and an image. A call that returns a feature is not proof: the
   "equal distance" chamfer returns a feature with error code 0 and removes nothing.
3. **Promote it**: add it to `swlib.py` with a docstring noting the gotchas, add a case to
   `scripts/selftest.py`, run the selftest, and document it here - so the next session starts
   from proven ground.

Known behaviour to expect:

- **Late binding quirks.** Under pywin32's dynamic dispatch some no-arg methods come back as
  bound methods (wrap results in `val()`), while others are auto-invoked as properties so
  writing `()` calls the *result* and fails with "Member not found" (`GetMathUtility`,
  `Inverse`). If a call fails that way, try it without parentheses, or with `val()`.
- **Arrays and out-params.** Pass arrays of doubles as `VARIANT(VT_ARRAY | VT_R8, [...])`, and
  "Nothing" object args (including unused array args, and `SelectData`) as `swlib.NOTHING`.
  Methods with by-reference out-params can fail with "Parameter not optional"
  (`Feature.GetErrorCode2`); look for an older variant without them (`GetErrorCode`).
- **Entity methods work on edges/faces directly**: `edge.Select4(True, NOTHING)` works under
  late binding, no QueryInterface needed.
- **Units.** The raw API is metres; `swlib.MM = 1e-3`.
- **Speed.** Each COM call from WSL costs ~20 ms, so a loop over geometry (every edge, face or
  component) can take many seconds. Wrap such read-only loops in `with swlib.batch_calls():`
  (sets `CommandInProgress`, ~20x-60x faster, restored on exit); `edges()` already does.
- **`ViewZoomTo2`** takes its corners in the view's screen frame, not model space - it only
  looks right in *Front, where they coincide (handled by `snap(box=)`).
- **`GetBodyBox` is loose around spline faces** (lofts): +-13 mm for a loft whose true extent
  is +-12. `Part.bbox()` uses `GetExtremePoint` per axis instead, which is tight; component
  boxes in assemblies (`Assembly.box`/`bbox`) still come from SolidWorks' boxes.
- **`AddComponent5`** positions the component's bounding-box centre, not its origin (handled
  in `Assembly.add`).
- **Enum values** aren't available by name under late binding; look them up with
  `sw_api.sh -Enum` and name them as constants at the top of `swlib.py`.
- **Draft direction**: for both extrude and cut, `Ddir1=False` (swlib's default) shrinks the
  profile as the feature progresses - verified against frustum volumes.
- **`FeatureExtrusion2`/`FeatureCut4` argument 2 ("Flip") is not a direction.** It flips the
  side to cut and does nothing to a boss; argument 3 ("Dir") reverses (swlib's `reverse=`).

## Files

- `scripts/swlib.py` - the library (read its docstrings for details)
- `scripts/sw_run.sh` - runs a script under Windows Python with swlib on the path
- `scripts/sw_status.py` - preflight check
- `scripts/sw_api.sh` - offline API signature / enum lookup
- `scripts/pngread.py` - stdlib PNG reader and edge-line finder for measuring close-ups
- `scripts/selftest.py` - regression test of every swlib feature against exact volumes; run it
  after changing swlib (`sw_run.sh selftest.py`, about 3 minutes)
- `examples/rpi_enclosure/` - Raspberry Pi 4/5 case (base with standoffs and port cutouts, lid
  with locating lip and vents, assembly with interference check). Read it before a similar
  job; it shows the frame, constants and verification style in practice.
- `examples/tapered_lid_box/` - box with a 4-degree tapered lid fit, concave and convex fillets,
  exact-volume checks for every feature, an edge-loop check that the lip and seat tapers
  match, and a cut-away of the closed assembly.
