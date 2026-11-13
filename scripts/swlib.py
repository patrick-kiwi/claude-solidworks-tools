"""swlib - a thin, verified helper layer over the SolidWorks COM API (pywin32, late binding).

Runs under *Windows* Python (launch scripts with sw_run.sh from WSL). Every public coordinate
and length is in millimetres, in MODEL space; the SolidWorks API itself works in metres.

Model frame used throughout: Y is up. "Top Plane" is the XZ plane at Y=0, and a boss sketched
on it extrudes toward +Y. Standard views look along: *Front -Z, *Back +Z, *Right -X, *Left +X,
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
import math
import os
import types
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
FILLET_PROPAGATE, FILLET_UNIFORM = 1, 2          # swFeatureFilletOptions_e
CHAMFER_ANGLE_DISTANCE = 1                       # swChamferType_e (see Part.chamfer)


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

    def snap(self, name, view="*Isometric", folder=None):
        """Save the model, seen from a named view, as PNG. Returns the WSL path to Read.
        Images are rendered from the open model, not from the saved file."""
        folder = PureWindowsPath(folder) if folder else (self.path.parent if self.path else None)
        assert folder, "pass folder= or construct with save_as="
        out = folder / f"{name}.png"
        self.doc.ShowNamedView2(view, -1)
        self.doc.ViewZoomtofit2()
        self.doc.GraphicsRedraw2()
        self.doc.SaveAs3(str(out), 0, SAVE_COPY | SAVE_SILENT)
        print(f"image: {wsl_path(out)}")
        return wsl_path(out)

    def snaps(self, prefix, views=DEFAULT_VIEWS, folder=None):
        names = {"*Isometric": "iso", "*Front": "front", "*Back": "back", "*Right": "right",
                 "*Left": "left", "*Top": "top", "*Bottom": "bottom"}
        paths = [self.snap(f"{prefix}_{names.get(v, v.strip('*').lower())}", v, folder) for v in views]
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
        self._xf = None
        self.features = []

    # ---- selection
    def select_plane(self, name):
        self.doc.ClearSelection2(True)
        ok = self.doc.Extension.SelectByID2(name, "PLANE", 0, 0, 0, False, 0, NOTHING, 0)
        assert ok, f"could not select plane {name!r}"

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
                f"open or overlapping contours, or a blind cut that doesn't reach material")
        feat.Name = name
        self.features.append(name)
        return feat

    def extrude(self, name, depth, flip=False, draft_deg=0.0, draft_outward=False):
        """Boss. From a face: grows outward along the face normal. From Top Plane: toward +Y.
        draft_deg tapers the side walls: by default the profile SHRINKS as the boss grows
        (verified against frustum volumes); draft_outward=True makes it grow instead."""
        self._end_sketch()
        d = draft_deg > 0
        f = self.fm.FeatureExtrusion2(True, flip, False, END_BLIND, 0, depth*MM, 0,
                                      d, False, draft_outward, False, math.radians(draft_deg), 0,
                                      False, False, False, False, True, True, True, 0, 0, False)
        return self._named(f, name, "extrude")

    def cut(self, name, depth=None, flip=False, draft_deg=0.0, draft_outward=False):
        """Cut into the material from the sketch face. depth=None means Through All.
        draft_deg tapers the walls: by default the profile SHRINKS as the cut goes deeper
        (a pocket narrower at the bottom - verified); draft_outward=True widens it instead."""
        self._end_sketch()
        cond = END_THROUGH_ALL if depth is None else END_BLIND
        d = draft_deg > 0
        f = self.fm.FeatureCut4(True, flip, False, cond, 0, (depth or 0.01)*MM, 0,
                                d, False, draft_outward, False, math.radians(draft_deg), 0,
                                False, False, False, False, False, True, True, True, True, False,
                                0, 0, False, False)
        return self._named(f, name, "cut")

    # ---- edges, fillets, chamfers
    def edges(self, where=None):
        """Every edge of the solid bodies as Edge records (mm), optionally filtered by a
        predicate, e.g. p.edges(lambda e: e.lies_in('Y', 20) and e.along('X')).
        Edge objects go stale after any new feature - call edges() again afterwards."""
        out = []
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
        """(xmin, ymin, zmin, xmax, ymax, zmax) in mm over all solid bodies."""
        boxes = [val(b.GetBodyBox) for b in self.bodies()]
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
