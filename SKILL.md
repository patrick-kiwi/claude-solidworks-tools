---
name: solidworks
description: Drive the user's running SolidWorks from WSL/Linux - build parts and assemblies from Python scripts via the COM API (sketches, extrudes, cuts, draft/taper, fillets, chamfers), then check the result with rendered images, exact volumes and interference detection. Use this whenever the user wants something modelled, designed or built in SolidWorks or "in CAD" (enclosures, boxes, brackets, mounts, plates, spacers, lids, tapered or press-fit lids, cases for a PCB or Raspberry Pi/Arduino, parts for 3D printing), wants edges rounded or two parts checked for fit, or mentions SolidWorks, SLDPRT or SLDASM files - even if they don't say "SolidWorks" and just ask you to "make a part" or "design a case".
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

**Proven scope:** parts built from rectangles (optionally rounded) and circles sketched on Top
Plane or flat axis-aligned faces; extrudes and blind/through-all cuts, optionally drafted
(tapered); selecting edges by geometry; constant-radius fillets (convex and concave, single
edges or whole tangent loops) and 45-degree chamfers; assemblies placed by origin with
interference checks; section (cut-away) views for images. Every one of these is covered by `scripts/selftest.py` against exact
volumes. Anything else (revolves, sweeps, angled sketch planes, drawings, exports, editing the
user's existing files) is untested - see "Going beyond the proven scope" below.

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
  toward +Y. Centre parts on the origin where sensible - symmetry makes coordinates easy to
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

Run it: `$S/sw_run.sh path/to/build.py` (output streams as the build runs).

Each run creates the documents fresh. If the previous run's copy is still open, it is closed
first and discarded - together with any assembly from the same project folder that still holds
it (otherwise the new save would fail). `save()` confirms the file really landed on disk and
raises if not. A same-named document from a *different* folder is never closed - that is
probably the user's - so the build stops and asks for another name. So iterate by editing the
script and re-running, not by patching the open model.

When you finish, leave your documents open so the user can look at them in SolidWorks.

### API (all mm, model space)

| Call | What it does |
|---|---|
| `Part(save_as)` / `Assembly(save_as)` | New document from the default template; use as a context manager |
| `select_plane("Top Plane")` | Select a reference plane (only Top Plane is proven - see below) |
| `select_face(x, y, z, "+X")` | Select the flat face through that point with that outward normal; verified |
| `start_sketch()` | Open a sketch on the selection |
| `rect(p1, p2, r=0)` | Axis-aligned rectangle from two opposite corners; `r` rounds corners (must be < half the short side) |
| `circle(centre, radius)` | Circle |
| `extrude(name, depth, draft_deg=0)` | Boss: from a face it grows outward along the normal; from Top Plane toward +Y. Draft makes the profile shrink as it grows (`draft_outward=True` to grow) |
| `cut(name, depth=None, draft_deg=0)` | Cut into material from the sketch face; `None` = through all. Draft makes the pocket narrow as it deepens |
| `edges(where)` | Edge records (`kind`, `start`, `mid`, `end`, `radius`, mm) filtered by a predicate; helpers `e.lies_in("Y", 20)`, `e.along("X")` |
| `fillet(name, r, edges, propagate=False)` | Constant-radius fillet; `propagate=True` follows tangent edges (one edge of a rounded-rect loop does the loop) |
| `chamfer(name, d, edges, propagate=False)` | 45-degree chamfer, `d` back along both faces; `propagate` as for fillets |
| `report()` | Rebuild; print features, body count, volume (mm^3), bbox (mm) |
| `bbox()`, `volume()` | The same numbers, for asserts |
| `snap(name, view)` / `snaps(prefix, views)` | Render PNGs next to the saved file; prints the `/mnt/c/...` path to Read |
| `with doc.section("Z", offset=0):` | Display-only cut-away for the snaps inside the block (parts and assemblies); hides the +axis side so *Front/*Right/*Top/*Isometric look at the cut face |
| `save(path=None)`, `close()` | Save as / close this document |
| `Assembly.add(part_path, origin)` | Insert an open part with its **origin** at `origin`; verifies placement |
| `Assembly.box(comp)` | A placed component's box (mm), for asserting e.g. that a lid is seated |
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
- Edge records go stale after every feature; call `edges()` again rather than reusing them.
- Fillet a concave edge (floor meeting wall) and SolidWorks adds material; a convex edge loses it.
- Large radii fail when the fillet can't fit (radius bigger than an adjacent face) - the
  feature then returns None and the library raises.
- Do fillets last, after the cuts that define the edges; filleting first changes the edges
  later cuts and selections rely on.
- Vertical corners of a footprint are simplest rounded in the sketch (`rect(..., r=)`); use a
  fillet when the edge only exists after several features. A fillet whose radius equals an
  adjacent corner radius is fine (it blends into a spherical corner).

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
   no single image shows. `examples/tapered_lid_box/build.py` has helpers for rounded
   rectangles, drafted pockets and fillet loops (Pappus for the corners).
2. **Images.** Read the PNGs. Pick the views for this part: an isometric plus the orthographic
   view of every face you cut or that features exit through (e.g. `*Bottom` to prove a hole
   goes all the way, `*Left` for holes in a -X face) - pass them to `snaps()`. Check each
   feature exists, is on the intended face, and is in the right place relative to the others
   (count the holes; see if the notch is open where you meant). The dark band beside the part
   in some views is SolidWorks' floor shadow, not geometry. Images are rendered from the open
   model; only rely on (and show the user) images from your latest successful run - earlier
   runs' PNGs with other names are left in the folder.
   For anything inside - a lip in its seat, standoffs in a deep box, a blind hole's depth -
   render a section: `with p.section("Z"): p.snaps("x_section", ("*Front", "*Isometric"))`.
   It changes no geometry and costs a second or two, so don't build half-model copies.
   Place the cut through the feature (`offset`, mm along the axis) and not on a face - a cut
   that coincides with a wall face shows nothing useful. The image frames the whole model, so
   small details stay small; say so rather than over-reading them.
3. **Assemblies.** Check the component boxes (printed by `add`, or `Assembly.box(comp)` in an
   assert) are where you intended **before**
   trusting `interference()`. In the first session the interference check said "0 clashes"
   while the lid was floating 12 mm above the base - true, and meaningless. Only the image
   showed it. (`Assembly.add` now places by origin and verifies, but keep looking.)

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
- **`AddComponent5`** positions the component's bounding-box centre, not its origin (handled
  in `Assembly.add`).
- **Enum values** aren't available by name under late binding; look them up with
  `sw_api.sh -Enum` and name them as constants at the top of `swlib.py`.
- **Draft direction**: for both extrude and cut, `Ddir1=False` (swlib's default) shrinks the
  profile as the feature progresses - verified against frustum volumes.
- Other reference planes ("Front Plane" = XY, "Right Plane" = YZ) can be selected, but which
  way a boss or cut goes from them is unverified. Prefer sketching on a face of existing
  geometry, where the direction is known (outward for bosses, inward for cuts).

## Files

- `scripts/swlib.py` - the library (read its docstrings for details)
- `scripts/sw_run.sh` - runs a script under Windows Python with swlib on the path
- `scripts/sw_status.py` - preflight check
- `scripts/sw_api.sh` - offline API signature / enum lookup
- `scripts/selftest.py` - regression test of every swlib feature against exact volumes; run it
  after changing swlib (`sw_run.sh selftest.py`, about a minute)
- `examples/rpi_enclosure/` - Raspberry Pi 4/5 case (base with standoffs and port cutouts, lid
  with locating lip and vents, assembly with interference check). Read it before a similar
  job; it shows the frame, constants and verification style in practice.
- `examples/tapered_lid_box/` - box with a 4-degree tapered lid fit, concave and convex fillets,
  exact-volume checks for every feature, and an edge-loop check that the lip and seat tapers
  match.
