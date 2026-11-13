"""swlib - a thin, verified helper layer over the SolidWorks COM API (pywin32, late binding).

Runs under *Windows* Python (launch scripts with sw_run.sh from WSL). Every public coordinate
and length is in millimetres, in MODEL space; the SolidWorks API itself works in metres.

Model frame used throughout: Y is up. "Top Plane" is the XZ plane at Y=0 (normal +Y), "Front
Plane" the XY plane at Z=0 (normal +Z), "Right Plane" the YZ plane at X=0 (normal +X). From any
plane or face a boss grows along the normal and a cut goes against it; reverse=True swaps both. Standard views look along: *Front -Z, *Back +Z, *Right -X, *Left +X,
*Top -Y, *Bottom +Y (i.e. *Front shows the +Z face).

Typical use:
    from swlib import Part, Assembly, workdir
    out = workdir("my_project")
    with Part(out / "bracket.SLDPRT") as p:
        p.select_plane("Top Plane"); p.start_sketch()
        p.rect((-20, 0, -10), (20, 0, 10), r=2); p.extrude("Base", 3)
        p.select_face(0, 3, 0, "+Y"); p.start_sketch()
        p.circle((10, 3, 0), 2.5); p.cut("Hole")               # through all
        p.report(); p.save(); p.snaps("bracket")
"""
import itertools
import math
import os
import struct
import types
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import PureWindowsPath

import pythoncom
import win32com.client
from win32com.client import VARIANT

NOTHING = VARIANT(pythoncom.VT_DISPATCH, None)   # for the Callout arg of SelectByID2
MM = 1e-3
END_BLIND, END_THROUGH_ALL = 0, 1
TEMPLATE_PART, TEMPLATE_ASSEMBLY = 8, 9          # swUserPreferenceStringValue_e
SAVE_SILENT, SAVE_COPY = 1, 2                    # swSaveAsOptions_e

VIEW_FOR = {"+X": "*Right", "-X": "*Left", "+Y": "*Top", "-Y": "*Bottom",
            "+Z": "*Front", "-Z": "*Back"}
AXIS = {"X": 0, "Y": 1, "Z": 2}
DEFAULT_VIEWS = ("*Isometric", "*Front", "*Right", "*Top")
SECTION_PLANE = {"X": "Right Plane", "Y": "Top Plane", "Z": "Front Plane"}
SECTION_REVERSE_DEFAULT = False                  # set by test: which half is hidden (see section())
FILLET_PROPAGATE, FILLET_UNIFORM = 1, 2          # swFeatureFilletOptions_e
CHAMFER_ANGLE_DISTANCE = 1                       # swChamferType_e (see Part.chamfer)
REF_DISTANCE, REF_FLIP = 8, 256                  # swRefPlaneReferenceConstraints_e
VISIBILITY_HIDDEN = 1                            # swVisibilityState_e
END_MID_PLANE = 6                                # swEndConditions_e (revolve: symmetric)


# ---------------------------------------------------------------- utilities
def val(x):
    """pywin32 late binding sometimes returns a bound method for a no-arg COM method
    (e.g. body.GetBodyBox) instead of calling it. Pass any such result through val()."""
    return x() if isinstance(x, types.MethodType) else x


def app():
    """The running SolidWorks instance. Raises a clear error if SolidWorks isn't open."""
    try:
        return win32com.client.GetActiveObject("SldWorks.Application")
    except pythoncom.com_error:
        raise RuntimeError("SolidWorks is not running - ask the user to start it.") from None


@contextmanager
def batch_calls(sw=None):
    """Make many small COM calls fast: sets ISldWorks.CommandInProgress for the block, then
    restores the previous value (also on error). From an out-of-process client like ours each
    call otherwise costs ~20 ms; inside this block ~1 ms (measured: 48 edges 12.8 s -> 0.19 s,
    identical results). Use it around read-only loops over geometry (edges, faces, boxes) -
    keep feature creation, view changes and snaps outside it, which are untested inside."""
    sw = sw or app()
    prev = bool(sw.CommandInProgress)
    sw.CommandInProgress = True
    try:
        yield
    finally:
        sw.CommandInProgress = prev


def workdir(project, root=None):
    """A Windows folder for this project's CAD files and images (created if missing).
    Default root: %USERPROFILE%\\solidworks_work. SolidWorks saves reliably to local drives,
    so keep CAD output here rather than on the WSL filesystem."""
    root = PureWindowsPath(root or os.path.join(os.path.expanduser("~"), "solidworks_work"))
    path = root / project
    os.makedirs(str(path), exist_ok=True)
    return path


def wsl_path(win_path):
    """C:\\foo\\bar.png -> /mnt/c/foo/bar.png, so the agent in WSL can Read the file."""
    p = str(win_path)
    if len(p) > 2 and p[1] == ":":
        return "/mnt/" + p[0].lower() + p[2:].replace("\\", "/")
    return p


def _png_size(path):
    """(width, height) from a PNG's header."""
    with open(str(path), "rb") as f:
        head = f.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    return struct.unpack(">II", head[16:24])


def open_docs(sw=None):
    """Every document SolidWorks has loaded - including parts loaded only as references of an
    open assembly, which have no window of their own."""
    sw = sw or app()
    docs, d = [], val(sw.GetFirstDocument)
    while d is not None:
        docs.append(d)
        d = val(d.GetNext)
    return docs


def _doc_path(d):
    return PureWindowsPath(val(d.GetPathName) or "")


def _clear_target(sw, path):
    """Make way for a fresh build saved at `path`.

    SolidWorks can't hold two docs with the same file name, so a re-run must drop the copy
    from the previous run. Closing that copy's window isn't enough when an open assembly
    still holds it as a reference - the later save then fails. So: close the project
    folder's assemblies first (they're stale if a part is being rebuilt anyway), then the
    conflicting doc. Docs from any OTHER folder are never touched: if one has the same file
    name, that is probably the user's, and we stop and say so."""
    if path is None:
        return
    name, folder = path.name.lower(), path.parent
    clash = [d for d in open_docs(sw) if _doc_path(d).name.lower() == name]
    if not clash:
        return
    foreign = [str(_doc_path(d)) for d in clash if _doc_path(d).parent != folder]
    if foreign:
        raise RuntimeError(f"a different document with the file name {path.name!r} is open "
                           f"({foreign[0]}); pick another name rather than closing it")
    for d in open_docs(sw):
        if d.GetType == 2 and _doc_path(d).parent == folder:
            sw.CloseDoc(d.GetTitle)
    for d in open_docs(sw):
        if _doc_path(d).name.lower() == name:
            sw.CloseDoc(d.GetTitle)
    if any(_doc_path(d).name.lower() == name for d in open_docs(sw)):
        raise RuntimeError(f"could not close the previous {path.name}; close it in SolidWorks")


# ---------------------------------------------------------------- exact-volume checks
# Hand-derived volumes to assert each feature against (record v = p.volume() before it).
# All verified to 1e-3 mm^3 in selftest.py / examples/tapered_lid_box.

def rr_area(a, b, r):
    """Area of a rounded rectangle with half-extents a, b and corner radius r (r=0: plain)."""
    return 4 * a * b - (4 - math.pi) * r * r


def drafted_volume(a, b, r, depth, deg):
    """Volume of a drafted extrude/cut of a rounded rectangle (half-extents a, b, corner r) whose
    profile insets by d*tan(deg) at depth d. Area is quadratic in d, so Simpson's rule is exact
    (for r=0, or while the corner radius stays positive: r > depth*tan(deg))."""
    k = math.tan(math.radians(deg))
    A = lambda d: rr_area(a - d * k, b - d * k, max(r - d * k, 0) if r > 0 else 0)
    return depth / 6 * (A(0) + 4 * A(depth / 2) + A(depth))


def fillet_volume(r, straight_len, corner_r=None):
    """Material a fillet of radius r removes (convex edge) or adds (concave edge).
    Straight edges: r^2(1-pi/4) per mm of straight_len. With corner_r, the edge is a whole
    rounded-rectangle loop (straight_len = sum of its straight edges, e.g. 4(a-R)+4(b-R)) and
    the four corners add a full turn by Pappus.
    Valid only while r <= corner_r and r <= the height of the faces either side: beyond that
    SolidWorks still builds a fillet, but a different shape (measured: concave r1.5 in an R1
    pocket corner, convex r2 on a 1.5 mm plate) - the formula then disagrees, which is your cue."""
    A = r * r * (1 - math.pi / 4)
    vol = A * straight_len
    if corner_r is not None:
        xbar = r * (10 - 3 * math.pi) / (3 * (4 - math.pi))    # section centroid, in from the edge
        vol += A * 2 * math.pi * (corner_r - xbar)
    return vol


def chamfer_volume(d, straight_len, corner_r=None):
    """Material a 45-degree chamfer of distance d removes; corner_r as for fillet_volume."""
    A = d * d / 2
    vol = A * straight_len
    if corner_r is not None:
        vol += A * 2 * math.pi * (corner_r - d / 3)
    return vol


def revolve_volume(area, centroid_r, deg=360):
    """Pappus: a profile of `area` (mm^2) whose centroid is `centroid_r` mm from the axis,
    revolved through `deg`, sweeps area * centroid_r * angle. Rectangle spanning radii r0..r1,
    height h: area = (r1 - r0) * h, centroid_r = (r0 + r1) / 2 (-> pi (r1^2 - r0^2) h for a tube).
    Triangle: centroid is the mean of its corners. A circle of radius a centred R out: a torus."""
    return area * centroid_r * math.radians(deg)


def loft_volume(profile0, profile1):
    """Exact volume of a TWO-profile loft between polygons on parallel axis-aligned planes,
    given their corners (model mm) in paired order - corner i of one runs straight to corner i
    of the other. The loft is ruled, so its cross-section area is quadratic in height and
    Simpson's rule is exact: V = h/6 (A0 + 4 Amid + A1), Amid from the corner midpoints.
    Holds for twisted pairings too (verified: a square frustum paired one corner out)."""
    assert len(profile0) == len(profile1) >= 3, "same number of corners in each profile"
    k = next(a for a in range(3) if len({round(q[a], 9) for q in profile0}) == 1)
    i, j = [a for a in range(3) if a != k]
    h = abs(profile1[0][k] - profile0[0][k])

    def area(pts):
        return abs(sum(p[i] * q[j] - q[i] * p[j] for p, q in zip(pts, pts[1:] + pts[:1]))) / 2
    mid = [tuple((a + b) / 2 for a, b in zip(p, q)) for p, q in zip(profile0, profile1)]
    return h / 6 * (area(profile0) + 4 * area(mid) + area(profile1))


def circle_loft_estimate(circle, profile, r=0.0, n=400):
    """Upper-bound ESTIMATE of a two-profile loft between a circle and a polygon or rounded
    rectangle on a parallel plane (circle -> rect duct, circle -> hex socket). There is no
    exact formula: SolidWorks' surface is not ruled. This is the ruled loft that pairs each
    corner of the profile with the circle point in the same direction from the circle's
    centre; SolidWorks' volume was 0.03-0.6% BELOW it on 8 lofts and loft cuts (0.03% for a
    hexagon or a 2:1 rounded rect with small corners, 0.6% for a sharp 2.4:1 rectangle; the
    more elongated and sharp-cornered the profile, the bigger the gap). So check
    0 < 1 - got/estimate < 0.01 - that catches a wrong size, a wrong height or a missing
    profile, not sub-percent errors.
      circle  = (centre, radius), model mm, as passed to circle()
      profile = the other end: polygon corners (>= 3, as polygon() returns / polyline() takes),
                or the two opposite corners passed to rect(), with that rect's r.
    The profile must surround the circle's axis (every direction from it meets the profile once)."""
    (cen, rad) = circle
    pts = [tuple(map(float, q)) for q in profile]
    k = next(a for a in range(3) if len({round(q[a], 9) for q in pts}) == 1)
    i, j = [a for a in range(3) if a != k]
    line = lambda p, q: (lambda t: (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    if len(pts) == 2:
        (i0, i1), (j0, j1) = sorted(q[i] for q in pts), sorted(q[j] for q in pts)
        if r <= 0:
            vs = [(i1, j0), (i1, j1), (i0, j1), (i0, j0)]
            segs = [line(p, q) for p, q in zip(vs, vs[1:] + vs[:1])]
        else:
            arc = lambda cu, cv, a0: (lambda t: (cu + r * math.cos(math.radians(a0 + 90 * t)),
                                                 cv + r * math.sin(math.radians(a0 + 90 * t))))
            segs = [line((i1, j0 + r), (i1, j1 - r)), arc(i1 - r, j1 - r, 0),
                    line((i1 - r, j1), (i0 + r, j1)), arc(i0 + r, j1 - r, 90),
                    line((i0, j1 - r), (i0, j0 + r)), arc(i0 + r, j0 + r, 180),
                    line((i0 + r, j0), (i1 - r, j0)), arc(i1 - r, j0 + r, 270)]
    else:
        vs = [(q[i], q[j]) for q in pts]
        if sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(vs, vs[1:] + vs[:1])) < 0:
            vs.reverse()                                       # counter-clockwise in (i, j)
        segs = [line(p, q) for p, q in zip(vs, vs[1:] + vs[:1])]
    cu, cv = cen[i], cen[j]
    ang = [math.atan2(s(0)[1] - cv, s(0)[0] - cu) for s in segs]
    turns = [(a1 - a0) % (2 * math.pi) for a0, a1 in zip(ang, ang[1:] + ang[:1])]
    assert abs(sum(turns) - 2 * math.pi) < 1e-6, "the profile must surround the circle's axis"

    def pt(h, u, v):
        q = [0.0] * 3; q[k], q[i], q[j] = h, u, v
        return tuple(q)
    P, C = [], []
    for s, a0, d in zip(segs, ang, turns):
        for m in range(n):
            t = m / n
            P.append(pt(pts[0][k], *s(t)))
            C.append(pt(cen[k], cu + rad * math.cos(a0 + d * t), cv + rad * math.sin(a0 + d * t)))
    return loft_volume(C, P)


def assert_close(label, got, want, tol=0.05):
    """Print and assert a check, e.g. assert_close("cavity", v - p.volume(), rr_area(...) * depth).
    Once the body has a lofted face, exact features read up to ~2e-6 of the WHOLE part's volume
    off (0.8 mm^3 on a 0.5 L duct, even away from the loft): pass tol=1e-5 * p.volume()."""
    print(f"  check {label}: {got:.3f} vs {want:.3f}")
    assert abs(got - want) <= tol, f"{label}: got {got:.3f}, want {want:.3f}"


def assert_box(label, got, want, tol=1e-3):
    """Print and assert a bounding box (xmin, ymin, zmin, xmax, ymax, zmax), e.g.
    assert_box("plate", p.bbox(), (-25, 0, -25, 25, 8, 25)). bbox() is rounded to 1e-3 mm."""
    print(f"  check {label}: {tuple(got)} vs {tuple(want)}")
    assert got is not None and len(got) == 6, f"{label}: no box ({got})"
    bad = [a for a in range(6) if abs(got[a] - want[a]) > tol]
    assert not bad, f"{label}: box {tuple(got)}, want {tuple(want)}"


# ---------------------------------------------------------------- edges
@dataclass
class Edge:
    """One edge of a solid body, with its geometry in model-space mm.
    `kind` is 'line', 'circle' (full circles and arcs) or 'other'. For a full circle
    start == end. `radius` is set for circles/arcs. `obj` is the COM edge."""
    obj: object
    kind: str
    start: tuple
    end: tuple
    mid: tuple
    radius: float = None

    def lies_in(self, axis, value, tol=1e-3):
        """True if start, mid and end all have that coordinate, e.g. lies_in('Y', 20) for an
        edge in the plane Y=20."""
        i = AXIS[axis.upper()]
        return all(abs(p[i] - value) < tol for p in (self.start, self.mid, self.end))

    def along(self, axis, tol=1e-6):
        """True for a straight edge parallel to the axis."""
        if self.kind != "line":
            return False
        d = [b - a for a, b in zip(self.start, self.end)]
        n = math.sqrt(sum(c*c for c in d))
        return n > 0 and abs(abs(d[AXIS[axis.upper()]]) / n - 1) < tol


# ---------------------------------------------------------------- shared doc behaviour
class _Doc:
    def __init__(self, template_pref, save_as):
        self.app = app()
        self.path = PureWindowsPath(save_as) if save_as else None
        _clear_target(self.app, self.path)
        self.doc = self.app.NewDocument(self.app.GetUserPreferenceStringValue(template_pref), 0, 0, 0)
        if self.doc is None:
            raise RuntimeError("NewDocument failed - check the default template in SolidWorks options.")
        self._plain_scene = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # On failure, close the half-built doc so it doesn't clutter SolidWorks.
        # On success leave it open so the user can look at it.
        if exc_type is not None:
            self.close()
        return False

    def save(self, path=None):
        path = PureWindowsPath(path) if path else self.path
        assert path, "no save path given"
        err = self.doc.SaveAs3(str(path), 0, SAVE_SILENT)
        # SaveAs3 can fail quietly (e.g. name clash with a loaded reference); confirm it landed.
        if err != 0 or _doc_path(self.doc) != path or not os.path.exists(str(path)):
            raise RuntimeError(f"save to {path} FAILED (error {err}); doc is at {_doc_path(self.doc)}")
        self.path = path
        print(f"saved: {path}")

    def close(self):
        self.app.CloseDoc(self.doc.GetTitle)

    def snap(self, name, view="*Isometric", folder=None, box=None):
        """Save the model, seen from a named view, as PNG. Returns the WSL path to Read.
        Images are rendered from the open model, not from the saved file.

        box=(xmin, ymin, zmin, xmax, ymax, zmax) in model mm makes a CLOSE-UP: the view is
        zoomed so that box's outline on screen fills the image (centred; the tighter of the two
        screen directions decides the scale, so the other shows a bit more). Works in any named
        view, for parts and assemblies, and inside section(). Leave a margin round the detail.
        A close-up prints its scale (px per mm), and afterwards pixel(point) gives where a model
        point lands in that image - e.g. a 0.15 mm gap at 200 px/mm should be ~30 px wide."""
        folder = PureWindowsPath(folder) if folder else (self.path.parent if self.path else None)
        assert folder, "pass folder= or construct with save_as="
        out = folder / f"{name}.png"
        if not self._plain_scene:
            # The floor shadow read as an extra block beside the part in *Top views, and the
            # floor reflection as more geometry below it - turn both off (this document only).
            scene = self.doc.GetActiveConfiguration.GetScene
            scene.FloorShadows = False
            scene.FloorReflections = False
            self._plain_scene = True
        self.doc.ShowNamedView2(view, -1)
        self.doc.ViewZoomtofit2()
        frame = self._zoom_to(box) if box is not None else None
        self.doc.GraphicsRedraw2()
        self.doc.SaveAs3(str(out), 0, SAVE_COPY | SAVE_SILENT)
        self._frame = None
        note = ""
        if frame:
            W, H = _png_size(out)
            R, (cx, cy), (w, h) = frame
            k = min(W / w if w > 1e-9 else math.inf, H / h if h > 1e-9 else math.inf)
            self._frame = (R, cx, cy, k, W, H)
            note = f"  (close-up: 1 mm = {k:.1f} px, {W / k:.2f} x {H / k:.2f} mm visible)"
        print(f"image: {wsl_path(out)}{note}")
        return wsl_path(out)

    def _zoom_to(self, box):
        """Zoom the current view onto a model-space box. ViewZoomTo2 takes its corners in the
        VIEW's frame (screen x right, y up), not model space - in *Front the two coincide,
        so model coordinates seem to work there and silently frame empty space in every other
        view. So: rotate the box's 8 corners into the view frame (Orientation3, row-vector
        p.R) and zoom to their screen extent."""
        assert len(box) == 6 and all(box[i] <= box[i + 3] for i in range(3)), \
            "box is (xmin, ymin, zmin, xmax, ymax, zmax) with min <= max"
        R = val(self.doc.ActiveView.Orientation3).ArrayData[:9]
        scr = [[sum(c[i] * R[i*3 + j] for i in range(3)) for j in range(2)]
               for c in itertools.product(*[(box[i], box[i + 3]) for i in range(3)])]
        lo = [min(p[j] for p in scr) for j in range(2)]
        hi = [max(p[j] for p in scr) for j in range(2)]
        w, h = hi[0] - lo[0], hi[1] - lo[1]
        assert max(w, h) > 1e-6, "box has no extent on screen in this view"
        self.doc.ViewZoomTo2(lo[0]*MM, lo[1]*MM, 0, hi[0]*MM, hi[1]*MM, 0)
        return R, ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2), (w, h)

    def pixel(self, point):
        """(column, row) of a model point (mm) in the LAST snap, which must be a close-up
        (box=...). Row 0 is the top of the image. Measured accurate to about a pixel."""
        assert getattr(self, "_frame", None), "pixel() needs the last snap to be a close-up (box=...)"
        R, cx, cy, k, W, H = self._frame
        sx, sy = (sum(point[i] * R[i*3 + j] for i in range(3)) for j in range(2))
        return W / 2 + (sx - cx) * k - 0.5, H / 2 - (sy - cy) * k - 0.5

    @contextmanager
    def section(self, axis="Z", offset=0.0, reverse=False):
        """Display-only section view (cut-away) for snaps - no geometry is changed, works for
        parts and assemblies, and is removed again when the block exits:

            with a.section("Z"):                 # cut on the plane Z=0
                a.snaps("asm_section", ("*Front", "*Isometric"))

        axis is the plane's normal: 'Z' cuts on Front Plane, 'X' on Right Plane, 'Y' on Top
        Plane; offset (mm) moves the cut along that axis. By default the half toward the
        standard views (+Z for *Front, +X for *Right, +Y for *Top, and toward *Isometric) is
        hidden so those views look straight at the cut face; reverse=True keeps that half."""
        plane = self.doc.FeatureByName(SECTION_PLANE[axis.upper()])
        assert plane is not None, f"no {SECTION_PLANE[axis.upper()]} in this document"
        mvm = self.doc.ModelViewManager
        data = val(mvm.CreateSectionViewData)
        data.FirstPlane = plane
        data.FirstOffset = offset * MM
        data.FirstReverseDirection = SECTION_REVERSE_DEFAULT ^ bool(reverse)
        data.ShowSectionCap = True
        assert mvm.CreateSectionView(data), "CreateSectionView failed"
        try:
            yield
        finally:
            val(mvm.RemoveSectionView)
            self.doc.GraphicsRedraw2()

    def snaps(self, prefix, views=DEFAULT_VIEWS, folder=None, box=None):
        """snap() from each view, named <prefix>_iso, _front, ...; box= makes them close-ups."""
        names = {"*Isometric": "iso", "*Front": "front", "*Back": "back", "*Right": "right",
                 "*Left": "left", "*Top": "top", "*Bottom": "bottom"}
        paths = [self.snap(f"{prefix}_{names.get(v, v.strip('*').lower())}", v, folder, box)
                 for v in views]
        self.doc.ShowNamedView2("*Isometric", -1)    # leave the user a useful view, not an edge-on one
        self.doc.ViewZoomtofit2()
        return paths


# ---------------------------------------------------------------- parts
class Part(_Doc):
    def __init__(self, save_as=None):
        super().__init__(TEMPLATE_PART, save_as)
        self.sm = self.doc.SketchManager
        self.fm = self.doc.FeatureManager
        self.sm.AddToDB = True           # draw exactly where told: no snapping / inference
        self.sm.DisplayWhenAdded = False
        self._xf = self._axis = None
        self._corners, self._circles, self._profiles = [], [], {}
        self.features = []

    # ---- selection
    def select_plane(self, name):
        """Select "Top Plane", "Front Plane", "Right Plane" or a plane made with plane()."""
        self.doc.ClearSelection2(True)
        ok = self.doc.Extension.SelectByID2(name, "PLANE", 0, 0, 0, False, 0, NOTHING, 0)
        assert ok, f"could not select plane {name!r}"

    def plane(self, name, base="Top Plane", offset=0.0):
        """Create a reference plane parallel to `base`, `offset` mm along base's normal (Top +Y,
        Front +Z, Right +X; for a plane made here, the same normal as its own base). Negative
        offsets go the other way. Sketch on it with select_plane(name) - sketch points then
        need that coordinate, e.g. z=30 on plane("P", "Front Plane", 30).
        The plane's position is read back from its transform and asserted."""
        assert offset != 0, "offset 0 is the base plane itself - sketch on that"
        base_t = val(val(self.doc.FeatureByName(base).GetSpecificFeature2).Transform).ArrayData
        self.select_plane(base)
        f = self.fm.InsertRefPlane(REF_DISTANCE | (REF_FLIP if offset < 0 else 0),
                                   abs(offset)*MM, 0, 0, 0, 0)
        self._named(f, name, "plane")
        t = val(val(f.GetSpecificFeature2).Transform).ArrayData
        # transform rows: [6:9] is the plane normal, [9:12] a point on it (model metres)
        moved = sum((t[9 + i] - base_t[9 + i]) * base_t[6 + i] for i in range(3)) / MM
        parallel = abs(sum(t[6 + i] * base_t[6 + i] for i in range(3)))
        assert abs(moved - offset) < 1e-6 and abs(parallel - 1) < 1e-9, \
            f"plane {name!r} landed {moved:.4f} mm from {base}, wanted {offset}"
        # A new plane is drawn in every render (and widens zoom-to-fit); hide it. Hidden
        # planes can still be selected by name.
        self.doc.ClearSelection2(True)
        f.Select2(False, 0)
        self.doc.BlankRefGeom()
        self.doc.ClearSelection2(True)
        assert f.Visible == VISIBILITY_HIDDEN, f"could not hide plane {name!r}"
        return f

    def select_face(self, x, y, z, normal):
        """Select the face through model point (x,y,z) whose outward normal is `normal`
        ('+X','-X','+Y','-Y','+Z','-Z').

        Picking by coordinate is a ray cast from the CURRENT view, and SolidWorks rotates the
        view whenever a sketch starts - so a naive pick silently grabs whichever face is in front
        (e.g. a rim top instead of a wall). We turn to the view that looks straight at the face,
        pick, then check the picked face's normal and fail loudly if it's wrong.
        Consequence: the face must be visible from outside along its normal (not hidden behind
        other geometry)."""
        self.doc.ShowNamedView2(VIEW_FOR[normal], -1)
        self.doc.ClearSelection2(True)
        ok = self.doc.Extension.SelectByID2("", "FACE", x*MM, y*MM, z*MM, False, 0, NOTHING, 0)
        assert ok, f"no face found at ({x}, {y}, {z}) looking from {VIEW_FOR[normal]}"
        face = self.doc.SelectionManager.GetSelectedObject6(1, -1)
        n = val(face.Normal)
        want = [0.0, 0.0, 0.0]
        want[AXIS[normal[1]]] = 1.0 if normal[0] == "+" else -1.0
        assert all(abs(a - b) < 1e-6 for a, b in zip(n, want)), \
            f"picked the wrong face at ({x}, {y}, {z}): normal {tuple(n)}, wanted {normal}"

    # ---- sketching (coordinates are model-space mm on the sketch plane)
    def start_sketch(self):
        """Open a sketch on the selected plane/face."""
        self.sm.InsertSketch(True)
        self._xf = self.sm.ActiveSketch.ModelToSketchTransform.ArrayData
        self._axis = None
        self._corners, self._circles = [], []     # what this sketch holds, for loft alignment

    def end_sketch(self, name):
        """Close the open sketch WITHOUT making a feature, name it, and return the name - for
        loft()/loft_cut() profiles. Remembers the sketch's corners/circle for loft alignment."""
        self.sm.InsertSketch(True)
        sketch = self.doc.FeatureByPositionReverse(0)
        assert self._corners or self._circles, "end_sketch(): nothing drawn in this sketch"
        sketch.Name = name
        assert sketch.Name == name, f"could not name the sketch {name!r} (name already used?)"
        self.doc.ClearSelection2(True)
        m = self._xf
        k = max(range(3), key=lambda i: abs([m[2], m[5], m[8]][i]))     # normal axis
        self._profiles[name] = (list(self._corners), list(self._circles), k)
        return name

    def _s(self, x, y, z):
        # SolidWorks MathTransform, row-vector form: p' = scale * (p . R + T),
        # R row-major in [0:9], T in [9:12], scale in [12]. (Done in Python because the
        # MathUtility route breaks under late binding.)
        m, v = self._xf, (x*MM, y*MM, z*MM)
        out = [sum(v[i]*m[i*3 + j] for i in range(3)) + m[9 + j] for j in range(3)]
        assert abs(out[2]) < 1e-6, f"point ({x}, {y}, {z}) is not on the sketch plane"
        return out[0]*m[12], out[1]*m[12]

    def rect(self, p1, p2, r=0.0):
        """Rectangle between two opposite model-space corners lying on the sketch plane
        (sketch planes here are axis-aligned). r > 0 rounds the corners; a slot with fully
        round ends needs r slightly less than half the width (r == half-width is rejected)."""
        (ax, ay), (bx, by) = self._s(*p1), self._s(*p2)
        x0, x1, y0, y1 = min(ax, bx), max(ax, bx), min(ay, by), max(ay, by)
        # corners in model space (for loft alignment): with r, the 8 points where arcs meet sides
        i, j = [a for a in range(3) if abs(p1[a] - p2[a]) > 1e-9]
        (i0, i1), (j0, j1) = sorted((p1[i], p2[i])), sorted((p1[j], p2[j]))
        for ci, cj, di, dj in ((i0, j0, 1, 1), (i1, j0, -1, 1), (i1, j1, -1, -1), (i0, j1, 1, -1)):
            for oi, oj in (((0, dj * r), (di * r, 0)) if r > 0 else ((0, 0),)):
                q = list(p1); q[i], q[j] = ci + oi, cj + oj
                self._corners.append(tuple(q))
        if r <= 0:
            self.sm.CreateCornerRectangle(x0, y0, 0, x1, y1, 0)
            return
        r *= MM
        assert 2*r < min(x1 - x0, y1 - y0) - 1e-9, "corner radius must be < half the short side"
        L, A = self.sm.CreateLine, self.sm.CreateArc
        L(x0+r, y0, 0, x1-r, y0, 0); A(x1-r, y0+r, 0, x1-r, y0, 0, x1, y0+r, 0, 1)
        L(x1, y0+r, 0, x1, y1-r, 0); A(x1-r, y1-r, 0, x1, y1-r, 0, x1-r, y1, 0, 1)
        L(x1-r, y1, 0, x0+r, y1, 0); A(x0+r, y1-r, 0, x0+r, y1, 0, x0, y1-r, 0, 1)
        L(x0, y1-r, 0, x0, y0+r, 0); A(x0+r, y0+r, 0, x0, y0+r, 0, x0+r, y0, 0, 1)

    def circle(self, centre, radius):
        cx, cy = self._s(*centre)
        self.sm.CreateCircleByRadius(cx, cy, 0, radius*MM)
        self._circles.append((tuple(centre), radius))

    def polyline(self, points):
        """Closed polygon through model-space points on the sketch plane (the last point joins
        back to the first - don't repeat it). Any straight-sided profile: an L, a trapezoid, a
        knob's half-section for revolve()."""
        assert len(points) >= 3, "a closed polyline needs at least 3 points"
        s = [self._s(*q) for q in points]
        for (x1, y1), (x2, y2) in zip(s, s[1:] + s[:1]):
            assert (x1, y1) != (x2, y2), "repeated point in polyline (don't close it yourself)"
            self.sm.CreateLine(x1, y1, 0, x2, y2, 0)
        self._corners.extend(tuple(q) for q in points)

    def polygon(self, centre, sides, radius=None, flats=None, toward=None):
        """Regular polygon on the sketch plane; returns its corners (model mm), counter-clockwise
        seen from the +side of the plane's normal axis (e.g. from +Y on Top Plane).
        Size it by `radius` (centre to corner) or `flats` (across-flats distance, how hex keys,
        nuts and sockets are specified: flats = 2 * radius * cos(180/sides)) - exactly one.
        `toward` points the FIRST CORNER: '+X', '-Z', ... or a model vector lying in the plane;
        default the first of +X, +Y, +Z in the plane (+X on Top/Front Plane, +Y on Right). A
        hexagon with a corner toward +X has its flats facing the other in-plane axis.
        Drawn with polyline() rather than CreatePolygon, whose 'inscribed' flag was measured
        to change nothing (the given point is always a corner) and which adds a construction
        circle; extruded volume = sides/2 * R^2 * sin(360/sides) * depth (selftest)."""
        assert sides >= 3 and (radius is None) != (flats is None), "sides >= 3 and one of radius/flats"
        R = radius if radius is not None else flats / 2 / math.cos(math.pi / sides)
        m = self._xf
        n = [m[2], m[5], m[8]]                          # sketch normal in model space
        k = max(range(3), key=lambda i: abs(n[i]))      # the plane's normal axis
        if toward is None:
            u = [1.0 if i == min(i for i in range(3) if i != k) else 0.0 for i in range(3)]
        elif isinstance(toward, str):
            u = [0.0] * 3; u[AXIS[toward[1].upper()]] = 1.0 if toward[0] == "+" else -1.0
        else:
            u = list(toward)
        assert abs(u[k]) < 1e-9 and any(u), f"toward {toward!r} must lie in the sketch plane"
        L = math.sqrt(sum(c*c for c in u)); u = [c / L for c in u]
        a = [0.0] * 3; a[k] = 1.0                       # +axis; v = a x u turns u CCW about it
        v = [a[1]*u[2] - a[2]*u[1], a[2]*u[0] - a[0]*u[2], a[0]*u[1] - a[1]*u[0]]
        pts = []
        for i in range(sides):
            t = 2 * math.pi * i / sides
            pts.append(tuple(centre[j] + R * (math.cos(t)*u[j] + math.sin(t)*v[j]) for j in range(3)))
        self.polyline(pts)
        return pts

    def centreline(self, p1, p2):
        """The axis for revolve()/revolve_cut(): an (infinite) construction line through two
        model-space points on the sketch plane. Its DIRECTION p1 -> p2 matters for partial
        angles - see revolve(). One per sketch: with two, SolidWorks silently revolves about
        the first one drawn, so a second call raises."""
        assert self._axis is None, "one centreline per sketch (SolidWorks would pick one silently)"
        (x1, y1), (x2, y2) = self._s(*p1), self._s(*p2)
        assert (x1, y1) != (x2, y2), "centreline needs two different points"
        assert self.sm.CreateCenterLine(x1, y1, 0, x2, y2, 0) is not None, "CreateCenterLine failed"
        self._axis = (p1, p2)

    def _end_sketch(self):
        self.sm.InsertSketch(True)
        sketch = self.doc.FeatureByPositionReverse(0)
        self.doc.ClearSelection2(True)
        sketch.Select2(False, 0)

    # ---- features (each closes the open sketch and consumes it)
    def _named(self, feat, name, kind):
        if feat is None:
            raise RuntimeError(
                f"{kind} {name!r} FAILED - usual causes: sketch on the wrong face/plane, "
                f"open or overlapping contours, or a cut that doesn't reach material (from a "
                f"reference plane a cut goes against its normal - try reverse=True or both=True)")
        feat.Name = name
        self.features.append(name)
        return feat

    def extrude(self, name, depth, reverse=False, draft_deg=0.0, draft_outward=False):
        """Boss. Grows along the sketch normal: outward from a face, +Y from Top Plane, +Z from
        Front Plane, +X from Right Plane (and from an offset plane, its base's way).
        reverse=True grows the other way (bbox-verified on all three planes).
        draft_deg tapers the side walls: by default the profile SHRINKS as the boss grows
        (verified against frustum volumes, also reversed); draft_outward=True makes it grow."""
        self._end_sketch()
        d = draft_deg > 0
        # FeatureExtrusion2's 2nd arg ("Flip") is flip-side-to-cut - a no-op for a boss; the
        # 3rd ("Dir") is the one that reverses direction.
        f = self.fm.FeatureExtrusion2(True, False, reverse, END_BLIND, 0, depth*MM, 0,
                                      d, False, draft_outward, False, math.radians(draft_deg), 0,
                                      False, False, False, False, True, True, True, 0, 0, False)
        return self._named(f, name, "extrude")

    def cut(self, name, depth=None, reverse=False, both=False, draft_deg=0.0, draft_outward=False):
        """Cut. depth=None means Through All. Goes AGAINST the sketch normal: into the material
        from a face, -Y from Top Plane, -Z from Front Plane, -X from Right Plane.
        So a cut sketched on Top Plane under a part standing on Y=0 goes away from it and
        FAILS (even through-all) - pass reverse=True to cut toward +Y.
        both=True cuts both ways from the sketch plane (depth each way, or through all both
        ways) - the natural choice for a plane through the middle of the part.
        draft_deg tapers the walls: by default the profile SHRINKS as the cut goes deeper
        (a pocket narrower at the bottom - verified); draft_outward=True widens it instead."""
        assert not (both and draft_deg), "both=True with draft is untested"
        self._end_sketch()
        cond = END_THROUGH_ALL if depth is None else END_BLIND
        d = draft_deg > 0
        D = (depth or 0.01)*MM
        # 2nd arg "Flip" is flip-side-to-cut (the API's name; with it a full-section cut failed),
        # not a direction - the 3rd ("Dir") reverses.
        f = self.fm.FeatureCut4(not both, False, reverse, cond, cond if both else 0, D, D if both else 0,
                                d, False, draft_outward, False, math.radians(draft_deg), 0,
                                False, False, False, False, False, True, True, True, True, False,
                                0, 0, False, False)
        return self._named(f, name, "cut")

    def _revolve(self, name, deg, reverse, symmetric, cut):
        assert self._axis, "draw the axis with centreline() in this sketch first"
        assert 0 < deg <= 360, "deg must be in (0, 360]"
        assert not (symmetric and deg == 360), "symmetric needs a partial angle"
        self._end_sketch()
        f = self.fm.FeatureRevolve2(not symmetric, True, False, cut, reverse, False,
                                    END_MID_PLANE if symmetric else END_BLIND, 0,
                                    math.radians(deg), 0, False, False, 0, 0, 0, 0, 0,
                                    True, True, True)
        if f is None:
            raise RuntimeError(f"revolve {name!r} FAILED - usual causes: the profile crosses or "
                               f"is not in the plane of the centreline, open/overlapping contours, "
                               f"or (cut) the swept region misses the material")
        return self._named(f, name, "revolve")

    def revolve(self, name, deg=360, reverse=False, symmetric=False):
        """Boss: revolve the sketch's closed profile(s) about its centreline() by `deg`.
        The profile may touch the axis (a solid knob, a cone) but must not cross it.
        Partial angles turn by the RIGHT-HAND RULE about the centreline's direction p1 -> p2
        (thumb along p1 -> p2): about +Y, a profile at +X swings toward -Z; about +X, +Y swings
        toward +Z; about +Z, +X toward +Y (bbox-verified on Front, Right and Top Plane, and
        flipped by drawing the centreline the other way). reverse=True turns the other way;
        symmetric=True splits the angle evenly either side of the sketch plane.
        Check with revolve_volume() (Pappus)."""
        return self._revolve(name, deg, reverse, symmetric, False)

    def revolve_cut(self, name, deg=360, reverse=False, symmetric=False):
        """Cut: remove what the sketch's profile sweeps revolving about its centreline() - a
        groove round a cylinder, a bore, a partial-turn slot. Same direction rules as revolve()
        (verified: the cut turns the same way a boss would). The profile may extend past the
        material; only the overlap is removed."""
        return self._revolve(name, deg, reverse, symmetric, True)

    # ---- lofts
    def _align_points(self, recs):
        """One pick point per profile so that corresponding corners pair up: the corner of each
        profile whose direction from the profile's centre is closest to the direction of the
        first polygon profile's first corner; for a circle, its point in that direction."""
        k = recs[0][2]
        flat = lambda v: [0.0 if a == k else v[a] for a in range(3)]
        unit = lambda v: (lambda n: [c / n for c in v] if n > 1e-12 else v)(math.sqrt(sum(c*c for c in v)))
        centre = lambda pts: [sum(q[a] for q in pts) / len(pts) for a in range(3)]
        ref = next(([q - c for q, c in zip(corners[0], centre(corners))]
                    for corners, _, _ in recs if corners),
                    [1.0 if a == min(a for a in range(3) if a != k) else 0.0 for a in range(3)])
        ref = unit(flat(ref))
        out = []
        for corners, circles, _ in recs:
            if corners:
                c = centre(corners)
                out.append(max(corners, key=lambda q: sum(
                    u * r for u, r in zip(unit(flat([a - b for a, b in zip(q, c)])), ref))))
            else:
                (cen, rad), = circles
                out.append(tuple(cen[a] + rad * ref[a] for a in range(3)))
        return out

    def _loft(self, name, profiles, align, cut):
        assert len(profiles) >= 2, "a loft needs at least two profiles"
        recs = []
        for n in profiles:
            assert n in self._profiles, f"{n!r} is not a sketch made with end_sketch()"
            corners, circles, k = self._profiles[n]
            assert bool(corners) != bool(circles) and len(circles) <= 1, \
                f"profile {n!r}: one closed polygon/rectangle OR one circle per sketch (proven scope)"
            recs.append(self._profiles[n])
        assert len({r[2] for r in recs}) == 1, "profiles must lie on parallel planes (proven scope)"
        picks = list(align) if align is not None else self._align_points(recs)
        assert len(picks) == len(profiles), "align= needs one point per profile"
        self.doc.ClearSelection2(True)
        for n, q in zip(profiles, picks):
            ok = self.doc.Extension.SelectByID2(n, "SKETCH", q[0]*MM, q[1]*MM, q[2]*MM, True, 1, NOTHING, 0)
            assert ok, f"could not select profile {n!r}"
        if cut:
            f = self.fm.InsertCutBlend(False, True, False, 1, 0, 0, False, 0, 0, 0, True, True)
        else:
            f = self.fm.InsertProtrusionBlend2(False, True, False, 1, 0, 0, 1, 1, True, True,
                                               False, 0, 0, 0, True, True, True, 0)
        if f is None:
            raise RuntimeError(f"loft {name!r} FAILED - usual causes: a profile that isn't one "
                               f"closed contour, profiles in the wrong order, or (cut) a loft that "
                               f"misses the material")
        return self._named(f, name, "loft")

    def loft(self, name, profiles, align=None):
        """Boss: loft through sketches made with end_sketch(), in the order given (sketch each
        on a parallel plane - e.g. Top Plane and plane('P', 'Top Plane', h)). Each profile is
        one closed polygon/rectangle or one circle.

        ALIGNMENT is the trap: SolidWorks pairs the profiles' corners from where each profile
        is picked; without pick points it pairs them by how the sketch was drawn, and rect()
        and polyline() wind opposite ways on some planes - the loft silently TWISTS (measured:
        a square frustum came out 3333 instead of 4667 mm^3). So every loft here is picked at
        corresponding corners: by default the corner of each profile pointing the same way from
        its centre as the first polygon's first corner (right for similar shapes: square ->
        smaller square, circle -> hexagon - where the circle's pick point makes no difference).
        Pass align=[point per profile] (model mm, a corner of each) to pair them yourself.

        Two profiles make a RULED loft: straight lines between paired corners, so polygon ->
        polygon volume is exact with loft_volume(). Give both the same number of corners (a
        square -> hexagon loft twists into curved faces; add corners on the square's sides
        instead) or make one a circle. Three or more profiles make a smooth (spline) loft that
        passes through every profile."""
        return self._loft(name, profiles, align, False)

    def loft_cut(self, name, profiles, align=None):
        """Cut: remove the lofted region between the profiles (e.g. a tapered or circle-to-hex
        socket, sketched on a face and on a plane inside the part). Same rules as loft()."""
        return self._loft(name, profiles, align, True)

    # ---- edges, fillets, chamfers
    def edges(self, where=None):
        """Every edge of the solid bodies as Edge records (mm), optionally filtered by a
        predicate, e.g. p.edges(lambda e: e.lies_in('Y', 20) and e.along('X')).
        Edge objects go stale after any new feature - call edges() again afterwards.
        Fast (~0.2 s for 50 edges) because it runs inside batch_calls(); without that it took
        ~13 s and was most of a typical build's run time."""
        out = []
        with batch_calls(self.app):
            for body in self.bodies():
                for e in (val(body.GetEdges) or []):
                    cp = val(e.GetCurveParams3)
                    mid = val(e.Evaluate2((cp.UMinValue + cp.UMaxValue) / 2, 0))[:3]
                    curve = val(e.GetCurve)
                    kind = "line" if val(curve.IsLine) else "circle" if val(curve.IsCircle) else "other"
                    radius = val(curve.CircleParams)[6] / MM if kind == "circle" else None
                    rec = Edge(e, kind, tuple(v / MM for v in cp.StartPoint),
                               tuple(v / MM for v in cp.EndPoint), tuple(v / MM for v in mid), radius)
                    if where is None or where(rec):
                        out.append(rec)
        return out

    def edge_extent(self, where, axis):
        """(lo, hi) along `axis` ('X', 'Y' or 'Z') over the start, mid and end points of the
        edges matching `where` - e.g. the half-width of a tapered seat at height y:
            p.edge_extent(lambda e: e.lies_in("Y", y) and inside(e), "X")
        Exact for straight edges (rounded-rect loops have them at the extremes); a full circle
        or an arc that bulges past its mid point reads short."""
        es = self.edges(where)
        assert es, "edge_extent(): no edges match - check the filter against p.edges() output"
        a = AXIS[axis.upper()]
        vals = [q[a] for e in es for q in (e.start, e.mid, e.end)]
        return min(vals), max(vals)

    def select_edges(self, edges):
        self.doc.ClearSelection2(True)
        assert edges, "no edges to select - check the filter against p.edges() output"
        for e in edges:
            assert e.obj.Select4(True, NOTHING), f"could not select edge at {e.mid}"
        n = self.doc.SelectionManager.GetSelectedObjectCount2(-1)
        assert n == len(edges), f"selected {n} of {len(edges)} edges"

    def fillet(self, name, radius, edges, propagate=False):
        """Constant-radius fillet on the given Edge records. Convex edges get rounded off,
        concave edges (e.g. floor-to-wall inside a box) get material added. propagate=True
        also takes every edge tangent-connected to them - one edge of a rounded-rectangle
        loop then fillets the whole loop."""
        self.select_edges(edges)
        opts = FILLET_UNIFORM | (FILLET_PROPAGATE if propagate else 0)
        f = self.fm.FeatureFillet3(opts, radius*MM, 0, 0, 0, 0, 0,
                                   NOTHING, NOTHING, NOTHING, NOTHING, NOTHING, NOTHING, NOTHING)
        return self._named(f, name, "fillet")

    def chamfer(self, name, distance, edges, propagate=False):
        """45-degree chamfer, `distance` back along both faces. Uses the angle-distance type:
        the 'equal distance' type returns a feature with error code 0 that removes NOTHING
        (found by checking volume), so don't switch to it."""
        self.select_edges(edges)
        f = self.fm.InsertFeatureChamfer(4 if propagate else 0, CHAMFER_ANGLE_DISTANCE,
                                         distance*MM, math.radians(45), 0, 0, 0, 0)
        return self._named(f, name, "chamfer")

    # ---- measurement / feedback
    def bodies(self):
        return list(self.doc.GetBodies2(0, True) or [])   # 0 = solid bodies

    def bbox(self):
        """(xmin, ymin, zmin, xmax, ymax, zmax) in mm over all solid bodies - TIGHT: built from
        each body's extreme points, because GetBodyBox pads spline faces (a loft whose widest
        section is +-12 mm reported +-13)."""
        boxes = []
        with batch_calls(self.app):
            for b in self.bodies():
                box = [0.0] * 6
                for a in range(3):
                    for sign, slot in ((-1, a), (1, a + 3)):
                        d = [0, 0, 0]; d[a] = sign
                        ok, *q = b.GetExtremePoint(*d)
                        assert ok, "GetExtremePoint failed"
                        box[slot] = q[a]
                boxes.append(box)
        if not boxes:
            return None
        return tuple(round(1000 * f(b[i] for b in boxes), 3)
                     for f, i in [(min, 0), (min, 1), (min, 2), (max, 3), (max, 4), (max, 5)])

    def volume(self):
        return self.doc.Extension.CreateMassProperty.Volume * 1e9   # mm^3, unrounded

    def report(self):
        """Rebuild and print the facts worth checking against the intended design."""
        self.doc.ForceRebuild3(False)
        info = {"features": self.features, "bodies": len(self.bodies()),
                "volume_mm3": round(self.volume(), 1), "bbox_mm": self.bbox()}
        for k, v in info.items():
            print(f"{k}: {v}")
        return info


# ---------------------------------------------------------------- assemblies
class Assembly(_Doc):
    def __init__(self, save_as=None):
        super().__init__(TEMPLATE_ASSEMBLY, save_as)
        self.components = []

    def add(self, part_path, origin=(0, 0, 0)):
        """Insert a part so that ITS ORIGIN lands at `origin` (mm, assembly space), unrotated.

        AddComponent5 actually positions the component's bounding-box CENTRE at the given
        point, not its origin - so we read the part's own bbox and compensate, then verify the
        placed component's box. The part must already be open in SolidWorks (e.g. built
        earlier in this session)."""
        part_path = str(PureWindowsPath(part_path))
        part = self.app.GetOpenDocumentByName(part_path)
        assert part is not None, f"open (or build) {part_path} in SolidWorks before adding it"
        boxes = [val(b.GetBodyBox) for b in (part.GetBodies2(0, True) or [])]
        assert boxes, f"{part_path} has no solid bodies"
        lo = [min(b[i] for b in boxes) for i in range(3)]
        hi = [max(b[i + 3] for b in boxes) for i in range(3)]
        centre = [origin[i]*MM + (lo[i] + hi[i]) / 2 for i in range(3)]
        comp = self.doc.AddComponent5(part_path, 0, "", False, "", *centre)
        assert comp is not None, f"AddComponent5 failed for {part_path}"
        got = val(comp.GetBox(False, False))
        want = [origin[i % 3]*MM + (lo + hi)[i] for i in range(6)]
        assert all(abs(g - w) < 1e-5 for g, w in zip(got, want)), \
            f"{part_path} placed wrong: box {[round(g*1000, 2) for g in got]}"
        self.components.append(comp)
        print(f"placed {PureWindowsPath(part_path).name}: box mm {[round(g*1000, 2) for g in got]}")
        return comp

    @staticmethod
    def box(comp):
        """A placed component's bounding box in assembly space, mm:
        (xmin, ymin, zmin, xmax, ymax, zmax). Use it to assert that parts sit where intended."""
        return tuple(round(v * 1000, 3) for v in val(comp.GetBox(False, False)))

    def bbox(self):
        """Overall box of everything placed with add(), assembly space, mm - e.g. the closed
        box's outer size, to assert against the size the user asked for."""
        assert self.components, "no components added"
        boxes = [self.box(c) for c in self.components]
        return tuple(f(b[i] for b in boxes)
                     for f, i in [(min, 0), (min, 1), (min, 2), (max, 3), (max, 4), (max, 5)])

    def interference(self):
        """Run interference detection. Returns a list of interference volumes (mm^3);
        empty means no clashes. Only meaningful once you've confirmed (by image and by the
        component boxes) that the parts are where you intended."""
        self.doc.ForceRebuild3(False)
        idm = self.doc.InterferenceDetectionManager
        idm.TreatCoincidenceAsInterference = False
        n = val(idm.GetInterferenceCount)
        vols = [round(i.Volume * 1e9, 3) for i in (val(idm.GetInterferences) or [])]
        idm.Done()
        print(f"interferences: {n} {vols if vols else ''}")
        return vols
