"""Regression test for swlib: every feature checked against an exact, hand-derived volume.
Run after changing swlib:  sw_run.sh selftest.py   (builds throwaway parts in solidworks_work\\_selftest)"""
import math
import time
from swlib import (Part, Assembly, workdir, app, val, rr_area, drafted_volume, fillet_volume,
                   chamfer_volume, revolve_volume, loft_volume, circle_loft_estimate, assert_box)
from pngread import read_png, grey_row, grey_col, dark_runs

OUT = workdir("_selftest")
TAN4 = math.tan(math.radians(4))
results = []


def check(label, got, want, tol=0.01):
    ok = abs(got - want) <= tol
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got:.3f} (want {want:.3f})")


def block(p, x=20, z=15, h=20):
    p.select_plane("Top Plane"); p.start_sketch()
    p.rect((-x, 0, -z), (x, 0, z)); p.extrude("Block", h)


def closeup(doc, name, view, box, segs, scan="row", label=None):
    """Snap a close-up and check that the edge lines crossing the middle row (or column) of
    the PNG sit where doc.pixel() predicts for the given model-space edge segments."""
    W, H, rows = read_png(doc.snap(name, view, box=box))   # snap()'s /mnt/c path, opened on Windows
    i = (H if scan == "row" else W) // 2 + 17           # a little off-centre, away from vertices
    seen = dark_runs(grey_row(rows, i) if scan == "row" else grey_col(rows, i))
    a, b = (1, 0) if scan == "row" else (0, 1)          # (scan coordinate, measured coordinate)
    want = []
    for p, q in segs:
        P, Q = doc.pixel(p), doc.pixel(q)
        if (P[a] - i) * (Q[a] - i) <= 0 and P[a] != Q[a]:
            want.append(P[b] + (i - P[a]) * (Q[b] - P[b]) / (Q[a] - P[a]))
    want.sort()
    ok = len(seen) == len(want) and all(abs(s - w) <= 1.5 for s, w in zip(seen, want))
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  close-up {label or name}: edges at "
          f"{[round(s) for s in seen]} px (want {[round(w, 1) for w in want]})")


frustum = lambda a, b, h: h / 3 * (a*a + b*b + a*b)

with Part(OUT / "st_features.SLDPRT") as p:
    block(p)                                                        # 40 x 20 x 30
    check("block volume", p.volume(), 40 * 30 * 20)
    check("bbox", sum(p.bbox()), -20 + 0 - 15 + 20 + 20 + 15)

    v = p.volume()
    p.select_face(0, 20, 0, "+Y"); p.start_sketch()
    p.circle((10, 20, 0), 2); p.cut("Through hole")
    check("through-all hole", v - p.volume(), math.pi * 4 * 20)

    v = p.volume()
    p.select_face(20, 10, 0, "+X"); p.start_sketch()                # wall face, verified pick
    p.rect((20, 5, -5), (20, 15, 5), r=2); p.cut("Rounded pocket", 3)
    check("rounded-rect blind cut", v - p.volume(), (100 - (4 - math.pi) * 4) * 3)

    v = p.volume()
    edge = p.edges(lambda e: e.lies_in("Y", 20) and e.lies_in("Z", -15) and e.along("X"))
    assert len(edge) == 1, edge
    p.fillet("Fillet", 3, edge)
    check("fillet r3 on 40 mm edge", v - p.volume(), 9 * (1 - math.pi / 4) * 40)

    v = p.volume()
    edge = p.edges(lambda e: e.lies_in("Y", 0) and e.lies_in("Z", 15) and e.along("X"))
    p.chamfer("Chamfer", 2, edge)
    check("chamfer 2 mm on 40 mm edge", v - p.volume(), 0.5 * 2 * 2 * 40)
    p.save(); p.snaps("features", ("*Isometric", "*Right"))

    # section view: display only - must render, then leave the geometry untouched
    import os
    v = p.volume()
    img = OUT / "features_section_z.png"            # Windows path (snap returns the WSL one)
    if os.path.exists(str(img)):
        os.remove(str(img))
    with p.section("Z"):
        p.snap("features_section_z", "*Front")
    ok = os.path.exists(str(img)) and abs(p.volume() - v) < 1e-6
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  section view rendered and removed, volume unchanged")
    p.close()                                          # selftest leaves nothing open

with Part(OUT / "st_draft.SLDPRT") as p:
    p.select_plane("Top Plane"); p.start_sketch()
    p.rect((-10, 0, -10), (10, 0, 10)); p.extrude("Drafted boss", 10, draft_deg=4)
    check("boss 4 deg draft (shrinks)", p.volume(), frustum(20, 20 - 20 * TAN4, 10))
    check("drafted_volume() helper = frustum", drafted_volume(10, 10, 0, 10, 4), frustum(20, 20 - 20 * TAN4, 10))
    v = p.volume()
    p.select_face(0, 10, 0, "+Y"); p.start_sketch()
    p.rect((-5, 10, -5), (5, 10, 5)); p.cut("Drafted pocket", 5, draft_deg=4)
    check("pocket 4 deg draft (narrows)", v - p.volume(), frustum(10, 10 - 10 * TAN4, 5))
    inside = lambda y: (lambda e: e.lies_in("Y", y) and all(abs(q[0]) < 8 for q in (e.start, e.mid, e.end)))
    check("edge_extent(): pocket half-width at the mouth", p.edge_extent(inside(10), "X")[1], 5)
    check("edge_extent(): ...and at the floor (Z axis)", p.edge_extent(inside(5), "Z")[1], 5 - 5 * TAN4, tol=1e-6)
    try:
        assert_box("drafted part", p.bbox(), (-10, 0, -10, 10, 10, 10))
        assert_box("drafted part, wrong", p.bbox(), (-10, 0, -10, 10, 11, 10)); ok = False
    except AssertionError:
        ok = True
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  assert_box() passes the right box and raises on a wrong one")
    p.close()

with Part(OUT / "st_loop.SLDPRT") as p:
    p.select_plane("Top Plane"); p.start_sketch()
    p.rect((-20, 0, -15), (20, 0, 15), r=5); p.extrude("Rounded block", 10)
    t0 = time.perf_counter()
    loop = p.edges(lambda e: e.lies_in("Y", 10))
    dt = time.perf_counter() - t0
    ok = dt < 3 and not app().CommandInProgress          # was ~13 s per call before batch_calls()
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  edges() fast ({dt:.2f} s) and CommandInProgress restored")
    one = [e for e in loop if e.along("X")][:1]
    v = p.volume()
    p.fillet("Loop fillet", 2, one, propagate=True)
    # Exact removal (swlib.fillet_volume): section r^2(1-pi/4) swept along 2*(30+20) mm of
    # straight sides, plus the four quarter-turns at the R5 corners by Pappus.
    check(f"propagated fillet round a {len(loop)}-edge loop", v - p.volume(), fillet_volume(2, 100, 5))

    # chamfer the bottom loop by propagation: triangle section d^2/2, centroid d/3 in from the edge
    v = p.volume()
    bottom = [e for e in p.edges(lambda e: e.lies_in("Y", 0)) if e.along("X")][:1]
    d = 1
    p.chamfer("Loop chamfer", d, bottom, propagate=True)
    check("propagated chamfer round the loop", v - p.volume(), chamfer_volume(d, 100, 5))
    p.close()

# reference planes: which way bosses and cuts go from Front/Right/Top and offset planes (by bbox)
def boxes(p):
    return sorted(tuple(round(v * 1000, 3) for v in val(b.GetBodyBox)) for b in p.bodies())


def same(label, got, want):
    ok = [tuple(map(float, b)) for b in got] == [tuple(map(float, b)) for b in want]
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got}" + ("" if ok else f" (want {want})"))


for plane, a, b, fwd, back in [
        ("Front Plane", (1, 2, 0), (4, 7, 0), (1, 2, 0, 4, 7, 5), (1, 2, -5, 4, 7, 0)),
        ("Right Plane", (0, 2, 1), (0, 7, 4), (0, 2, 1, 5, 7, 4), (-5, 2, 1, 0, 7, 4)),
        ("Top Plane", (1, 0, 2), (4, 0, 7), (1, 0, 2, 4, 5, 7), (1, -5, 2, 4, 0, 7))]:
    for reverse, want in ((False, fwd), (True, back)):
        with Part() as p:
            p.select_plane(plane); p.start_sketch(); p.rect(a, b)
            p.extrude("Boss", 5, reverse=reverse)
            same(f"boss from {plane}{' reversed' if reverse else ''}", [p.bbox()], [want])
            p.close()

# a full-section 3 mm slab cut from a plane through the block's middle splits it in two;
# the two bodies' boxes show which side the cut went
for plane, rect, fwd, back in [
        ("Front Plane", ((-12, -2, 0), (12, 12, 0)),
         [(-10, 0, -10, 10, 10, -3), (-10, 0, 0, 10, 10, 10)], [(-10, 0, -10, 10, 10, 0), (-10, 0, 3, 10, 10, 10)]),
        ("Right Plane", ((0, -2, -12), (0, 12, 12)),
         [(-10, 0, -10, -3, 10, 10), (0, 0, -10, 10, 10, 10)], [(-10, 0, -10, 0, 10, 10), (3, 0, -10, 10, 10, 10)])]:
    for reverse, want in ((False, fwd), (True, back)):
        with Part() as p:
            block(p, 10, 10, 10)
            p.select_plane(plane); p.start_sketch(); p.rect(*rect)
            p.cut("Slab", 3, reverse=reverse)
            same(f"cut from {plane}{' reversed' if reverse else ''}", boxes(p), want)
            p.close()

with Part() as p:                                   # the Top Plane trap: default cut goes -Y
    block(p, 10, 10, 10)
    p.select_plane("Top Plane"); p.start_sketch(); p.circle((-6, 0, 6), 2)
    try:
        p.cut("Away from the part")
        ok = False
    except RuntimeError:
        ok = True
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  through-all cut from Top Plane under the part fails (goes -Y)")
    p.close()

with Part(OUT / "st_planes.SLDPRT") as p:
    block(p, 10, 10, 10)
    v = p.volume()
    p.select_plane("Top Plane"); p.start_sketch(); p.circle((-6, 0, 6), 2)
    p.cut("Up from Top Plane", reverse=True)
    check("through-all from Top Plane, reversed", v - p.volume(), math.pi * 4 * 10)
    v = p.volume()
    p.select_plane("Front Plane"); p.start_sketch(); p.circle((6, 5, 0), 2)
    p.cut("Both ways from Front Plane", both=True)
    check("through-all both ways from Front Plane", v - p.volume(), math.pi * 4 * 20)
    v = p.volume()
    p.select_plane("Right Plane"); p.start_sketch(); p.circle((0, 5, -6), 1.5)
    p.cut("Blind both ways from Right Plane", 3, both=True)
    check("blind 3 mm both ways from Right Plane", v - p.volume(), math.pi * 2.25 * 6)
    p.close()

with Part(OUT / "st_offset.SLDPRT") as p:           # offset planes, chained, negative, reversed
    p.plane("P30", "Front Plane", 30)
    p.select_plane("P30"); p.start_sketch(); p.rect((0, 0, 30), (4, 4, 30)); p.extrude("B30", 5)
    p.plane("P40", "P30", 10)
    p.select_plane("P40"); p.start_sketch(); p.rect((0, 0, 40), (4, 4, 40)); p.extrude("B40", 3, reverse=True)
    p.plane("Pm", "Right Plane", -12.5)
    p.select_plane("Pm"); p.start_sketch(); p.rect((-12.5, 0, 0), (-12.5, 4, 4)); p.extrude("Bm", 5)
    p.plane("PT", "Top Plane", 20)
    p.select_plane("PT"); p.start_sketch(); p.rect((0, 20, 0), (4, 20, 4)); p.extrude("BT", 2)
    same("bosses on offset planes", boxes(p), sorted([(0, 0, 30, 4, 4, 35), (0, 0, 37, 4, 4, 40),
                                                     (-12.5, 0, 0, -7.5, 4, 4), (0, 20, 0, 4, 22, 4)]))
    p.close()

with Part() as p:                                   # draft still shrinks when reversed
    p.select_plane("Front Plane"); p.start_sketch(); p.rect((-10, -10, 0), (10, 10, 0))
    p.extrude("Drafted back", 10, reverse=True, draft_deg=4)
    check("reversed 4 deg drafted boss from Front Plane", p.volume(), frustum(20, 20 - 20 * TAN4, 10))
    same("  ...and it went -Z", [p.bbox()], [(-10, -10, -10, 10, 10, 0)])
    p.close()

# close-ups: a 0.5 mm slot must land on the predicted pixels in every view and in a section
with Part(OUT / "st_zoom.SLDPRT") as p:
    p.select_plane("Top Plane"); p.start_sketch()
    p.rect((-20, 0, -5), (20, 0, 5)); p.extrude("Block", 10)
    v = p.volume()
    p.select_face(0, 10, 0, "+Y"); p.start_sketch()
    p.rect((-0.25, 10, -6), (0.25, 10, 6)); p.cut("Slot", 4)          # open at both Z faces
    check("0.5 mm slot", v - p.volume(), 0.5 * 4 * 10)
    walls = [((x, 6, 5), (x, 10, 5)) for x in (-0.25, 0.25)]          # slot's vertical edges, +Z face
    rims = [((x, 10, -5), (x, 10, 5)) for x in (-0.25, 0.25)]         # slot's top edges
    closeup(p, "zoom_front", "*Front", (-1, 7, 5, 1, 11, 5), walls)
    closeup(p, "zoom_right", "*Right", (20, 8, 3, 20, 12, 7), [((20, 0, 5), (20, 10, 5))])
    closeup(p, "zoom_top", "*Top", (-1, 10, -1, 1, 10, 1), rims)
    closeup(p, "zoom_iso", "*Isometric", (-1, 8, 3, 1, 10, 7),
            walls + rims + [((0.25, 10, 5), (20, 10, 5))])
    with p.section("Z", offset=1):                                    # cut face at Z=1
        closeup(p, "zoom_section", "*Front", (-1, 7, 1, 1, 11, 1),
                [((x, 6, 1), (x, 10, 1)) for x in (-0.25, 0.25)], label="in a section")
    p.close()

# fillet radius == plate thickness: exact (r > thickness also "succeeds" but builds another shape)
with Part(OUT / "st_plate.SLDPRT") as p:
    p.select_plane("Top Plane"); p.start_sketch()
    p.rect((-30, 0, -20), (30, 0, 20), r=2); p.extrude("Plate", 2)
    check("plate volume", p.volume(), rr_area(30, 20, 2) * 2)
    v = p.volume()
    p.fillet("Edge fillet", 2, p.edges(lambda e: e.lies_in("Y", 2) and e.along("X"))[:1], propagate=True)
    check("r2 fillet on a 2 mm plate", v - p.volume(), fillet_volume(2, 4 * 28 + 4 * 18, 2))
    p.save()

    with Assembly(OUT / "st_asm.SLDASM") as a:          # two plates stacked, then overlapping
        a.add(p.path)
        top = a.add(p.path, origin=(0, 2, 0))
        bb = a.bbox()
        check("Assembly.bbox() of two stacked plates", sum(bb[3:]) - sum(bb[:3]), 60 + 4 + 40)
        ok = a.interference() == []
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  stacked (touching) plates: no interference")
        lap = a.add(p.path, origin=(0, 1, 0))           # half-way into the bottom plate
        ok = len(a.interference()) > 0
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  overlapping plate: interference found")
        a.add(p.path, origin=(0, 4.5, 0))               # 0.5 mm above the stack: a visible gap
        closeup(a, "zoom_asm_gap", "*Front", (20, 3.5, 20, 26, 7, 20),
                [((20, y, 20), (26, y, 20)) for y in (4, 4.5, 6.5)], scan="col",
                label="0.5 mm gap between assembly components")
        a.close()
    p.close()

# polylines and revolves (Pappus: area x centroid radius x angle)
with Part() as p:                                   # L-shaped polyline extruded
    p.select_plane("Front Plane"); p.start_sketch()
    p.polyline([(0, 0, 0), (12, 0, 0), (12, 3, 0), (3, 3, 0), (3, 10, 0), (0, 10, 0)])
    p.extrude("L", 5)
    check("L-shaped polyline extruded", p.volume(), (12 * 3 + 3 * 7) * 5)
    p.close()

ngon = lambda n, R: n / 2 * R * R * math.sin(2 * math.pi / n)     # regular polygon area
S60, C30 = math.sin(math.pi / 3), math.cos(math.pi / 6)
for plane, kw, h, want_box, area in [
        ("Top Plane", dict(centre=(5, 0, 3), sides=6, radius=10), 5,      # corner toward +X
         (-5, 0, 3 - 10 * S60, 15, 5, 3 + 10 * S60), ngon(6, 10)),
        ("Front Plane", dict(centre=(0, 0, 0), sides=6, flats=10, toward="+Y"), 4,   # flats face +-X
         (-5, -5 / C30, 0, 5, 5 / C30, 4), ngon(6, 5 / C30)),
        ("Right Plane", dict(centre=(0, 2, -1), sides=5, radius=6), 3,    # default: corner toward +Y
         (0, 2 - 6 * math.cos(math.pi / 5), -1 - 6 * math.sin(2 * math.pi / 5), 3, 8,
          -1 + 6 * math.sin(2 * math.pi / 5)), ngon(5, 6))]:
    with Part() as p:
        p.select_plane(plane); p.start_sketch()
        corners = p.polygon(**kw); p.extrude("Polygon", h)
        ok = abs(p.volume() - area * h) < 1e-3 and all(abs(g - w) < 1e-3 for g, w in zip(p.bbox(), want_box))
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  polygon {kw} on {plane}: volume {p.volume():.3f} "
              f"(want {area * h:.3f}), bbox {p.bbox()}" + ("" if ok else f" (want {want_box})"))
        p.close()

with Part(OUT / "st_revolve.SLDPRT") as p:
    p.select_plane("Front Plane"); p.start_sketch()
    p.centreline((0, 0, 0), (0, 1, 0))
    p.rect((6, 0, 0), (10, 20, 0)); p.revolve("Tube")
    check("revolved tube = pi(R^2-r^2)h", p.volume(), math.pi * (100 - 36) * 20)
    check("  revolve_volume() helper", revolve_volume(4 * 20, 8), math.pi * (100 - 36) * 20)
    v = p.volume()
    p.select_plane("Front Plane"); p.start_sketch()
    p.centreline((0, 0, 0), (0, 1, 0))
    p.rect((8, 8, 0), (11, 12, 0)); p.revolve_cut("Groove")       # sticks out past r=10
    check("revolved groove cut", v - p.volume(), revolve_volume(2 * 4, 9))
    v = p.volume()
    p.select_plane("Front Plane"); p.start_sketch()
    p.centreline((0, 0, 0), (0, 1, 0))
    p.rect((5, 14, 0), (11, 16, 0)); p.revolve_cut("Quarter slot", 90)
    check("90-degree revolved cut", v - p.volume(), revolve_volume(4 * 2, 8, 90))
    p.save(); p.snaps("revolve", ("*Isometric", "*Front"))
    p.close()

with Part() as p:                                   # profile touching the axis: a cone
    p.select_plane("Front Plane"); p.start_sketch()
    p.centreline((0, 0, 0), (0, 1, 0))
    p.polyline([(0, 0, 0), (10, 0, 0), (0, 20, 0)]); p.revolve("Cone")
    check("revolved cone = pi r^2 h / 3", p.volume(), revolve_volume(100, 10 / 3))
    p.close()

with Part() as p:                                   # circle about an off-origin axis: torus
    p.select_plane("Front Plane"); p.start_sketch()
    p.centreline((30, 0, 0), (30, 1, 0))
    p.circle((40, 0, 0), 3); p.revolve("Torus")
    check("torus about the axis x=30", p.volume(), revolve_volume(math.pi * 9, 10))
    p.close()

# partial angles: right-hand rule about the centreline's direction (by bbox)
for plane, a, b, axis, kw, want in [
        ("Front Plane", (6, 0, 0), (10, 20, 0), ((0, 0, 0), (0, 1, 0)), {}, (0, 0, -10, 10, 20, 0)),
        ("Front Plane", (6, 0, 0), (10, 20, 0), ((0, 1, 0), (0, 0, 0)), {}, (0, 0, 0, 10, 20, 10)),
        ("Front Plane", (6, 0, 0), (10, 20, 0), ((0, 0, 0), (0, 1, 0)), {"reverse": True}, (0, 0, 0, 10, 20, 10)),
        ("Front Plane", (6, 0, 0), (10, 20, 0), ((0, 0, 0), (0, 1, 0)), {"symmetric": True},
         (6 * math.cos(math.pi / 4), 0, -10 * math.sin(math.pi / 4), 10, 20, 10 * math.sin(math.pi / 4))),
        ("Front Plane", (0, 6, 0), (20, 10, 0), ((0, 0, 0), (1, 0, 0)), {}, (0, 0, 0, 20, 10, 10)),
        ("Right Plane", (0, 0, 6), (0, 20, 10), ((0, 0, 0), (0, 1, 0)), {}, (0, 0, 0, 10, 20, 10)),
        ("Top Plane", (6, 0, 0), (10, 0, 20), ((0, 0, 0), (0, 0, 1)), {}, (0, 0, 0, 10, 10, 20))]:
    with Part() as p:
        p.select_plane(plane); p.start_sketch(); p.centreline(*axis); p.rect(a, b)
        p.revolve("Quarter", 90, **kw)
        ok = abs(p.volume() - revolve_volume(4 * 20, 8, 90)) < 0.01 and \
            all(abs(g - w) < 1e-3 for g, w in zip(p.bbox(), want))
        results.append(ok)
        d = "".join("+-"[a > b] + "XYZ"[i] for i, (a, b) in enumerate(zip(*axis)) if a != b)
        print(f"{'PASS' if ok else 'FAIL'}  90 deg about {d} on {plane} {kw or ''}: {p.bbox()}"
              + ("" if ok else f" (want {want})"))
        p.close()

with Part() as p:                                   # a cut turns the same way: 270 deg leaves +X+Z
    p.select_plane("Top Plane"); p.start_sketch(); p.circle((0, 0, 0), 10); p.extrude("Cyl", 20)
    p.select_plane("Front Plane"); p.start_sketch(); p.centreline((0, 0, 0), (0, 1, 0))
    p.rect((0, -1, 0), (11, 21, 0)); p.revolve_cut("Three quarters", 270)
    check("270-degree revolved cut leaves a quarter", p.volume(), math.pi * 100 * 20 / 4)
    same("  ...the +X+Z quarter", [p.bbox()], [(0, 0, 0, 10, 20, 10)])
    p.close()

# lofts: two profiles make a ruled loft, so polygon lofts are exact by loft_volume() (Simpson)


def est_ok(got, est, lo, hi, label):
    """circle -> polygon lofts are not ruled: SolidWorks reads 0.03-0.6% under the estimate."""
    gap = 1 - got / est
    ok = lo <= gap <= hi
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  circle_loft_estimate(): {label} reads {gap:.2e} under it "
          f"(measured band {lo:.0e}..{hi:.0e})")
sqr = lambda a, y: [(a, y, a), (-a, y, a), (-a, y, -a), (a, y, -a)]       # square corners on Y=y


def two_profiles(p, bottom, top, h=20):
    """Sketch `bottom(p)` on Top Plane and `top(p)` on a plane h above; return the names."""
    p.select_plane("Top Plane"); p.start_sketch(); bottom(p); s1 = p.end_sketch("Bottom")
    p.plane("Loft top", "Top Plane", h)
    p.select_plane("Loft top"); p.start_sketch(); top(p); s2 = p.end_sketch("Top")
    return [s1, s2]


with Part(OUT / "st_loft.SLDPRT") as p:              # the winding trap: rect and polyline wind
    s = two_profiles(p, lambda p: p.rect((-10, 0, -10), (10, 0, 10)),   # oppositely; auto-align
                     lambda p: p.polyline(sqr(5, 20)))                   # must pair them anyway
    p.loft("Frustum", s)
    check("square frustum loft (rect -> polyline, auto-aligned)", p.volume(), frustum(20, 10, 20))
    check("  loft_volume() helper", loft_volume(sqr(10, 0), sqr(5, 20)), frustum(20, 10, 20))
    same("  tight bbox", [p.bbox()], [(-10, 0, -10, 10, 20, 10)])
    with p.section("Y", offset=10):                  # mid-height cut face is 15 mm square
        closeup(p, "loft_mid", "*Top", (-11, 10, -11, 11, 10, 11),
                [((x, 10, -7.5), (x, 10, 7.5)) for x in (-7.5, 7.5)] +
                [((x, 0, -10), (x, 0, 10)) for x in (-10, 10)], label="loft section at mid-height")
    p.save(); p.snaps("loft", ("*Isometric", "*Front"))
    p.close()

with Part() as p:                                    # paired one corner out on purpose: twisted
    s = two_profiles(p, lambda p: p.rect((-10, 0, -10), (10, 0, 10)), lambda p: p.polyline(sqr(5, 20)))
    p.loft("Twisted", s, align=[(10, 0, 10), (-5, 20, 5)])
    top = [(-5, 20, 5), (-5, 20, -5), (5, 20, -5), (5, 20, 5)]          # paired with sqr(10, 0)
    check("loft paired one corner out (align=) twists, still loft_volume()", p.volume(),
          loft_volume(sqr(10, 0), top))
    p.close()

with Part() as p:                                    # circle -> circle: cone frustum
    s = two_profiles(p, lambda p: p.circle((0, 0, 0), 10), lambda p: p.circle((0, 20, 0), 5))
    p.loft("Cone", s)
    want = math.pi * 20 / 3 * (100 + 25 + 50)
    # the face is an exact cone, but SolidWorks' volume of LOFTED round faces reads 4e-5..1e-4 low
    check("circle -> circle loft = cone frustum (to 2e-4)", p.volume(), want, tol=want * 2e-4)
    p.close()

with Part(OUT / "st_loft_hex.SLDPRT") as p:          # the circle -> hexagon transition
    hexagon = []
    s = two_profiles(p, lambda p: p.circle((0, 0, 0), 10),
                     lambda p: hexagon.extend(p.polygon((0, 20, 0), 6, radius=10)))
    p.loft("Circle to hexagon", s)
    v = p.volume()
    ok = ngon(6, 10) * 20 < v < math.pi * 100 * 20
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  circle -> hexagon loft between hexagonal prism and cylinder: {v:.3f}")
    est_ok(v, circle_loft_estimate(((0, 0, 0), 10), hexagon), 2e-4, 5e-4, "circle -> hexagon")
    same("  tight bbox", [p.bbox()], [(-10, 0, -10, 10, 20, 10)])
    ring = [(10 * math.cos(t * math.pi / 90), 0, 10 * math.sin(t * math.pi / 90)) for t in range(180)]
    closeup(p, "loft_hex_top", "*Top", (-11, 20, -11, 11, 20, 11),
            list(zip(hexagon, hexagon[1:] + hexagon[:1])) + list(zip(ring, ring[1:] + ring[:1])),
            scan="col", label="hexagon top and circle base seen from above")
    p.save(); p.snaps("loft_hex", ("*Isometric", "*Front"))
    p.close()

with Part() as p:                                    # circle -> sharp 2.4:1 rectangle: the widest gap
    s = two_profiles(p, lambda p: p.circle((0, 0, 0), 10), lambda p: p.rect((-12, 20, -5), (12, 20, 5)))
    p.loft("Circle to rect", s)
    est_ok(p.volume(), circle_loft_estimate(((0, 0, 0), 10), [(-12, 20, -5), (12, 20, 5)]), 5e-3, 7e-3,
           "circle -> 24x10 rectangle")
    p.close()

with Part() as p:                                    # rect -> circle, circle picked elsewhere: same solid
    s = two_profiles(p, lambda p: p.rect((-12, 0, -5), (12, 0, 5)), lambda p: p.circle((0, 20, 0), 10))
    p.loft("Rect to circle", s, align=[(-12, 0, -5), (0, 20, 10)])
    est_ok(p.volume(), circle_loft_estimate(((0, 20, 0), 10), [(-12, 0, -5), (12, 0, 5)]), 5e-3, 7e-3,
           "reversed, circle picked at +Z (pick point makes no difference)")
    p.close()

with Part() as p:                                    # the duct: circle -> 120x60 R3, then exact features
    s = two_profiles(p, lambda p: p.circle((0, 0, 0), 50),
                     lambda p: p.rect((-60, 50, -30), (60, 50, 30), r=3), h=50)
    p.loft("Duct transition", s)
    est_ok(p.volume(), circle_loft_estimate(((0, 0, 0), 50), [(-60, 50, -30), (60, 50, 30)], r=3),
           1.5e-4, 4e-4, "circle R50 -> 120x60 R3 duct")
    v = p.volume()
    p.select_face(55, 50, 0, "+Y"); p.start_sketch(); p.rect((-60, 50, -30), (60, 50, 30), r=3)
    p.extrude("Collar", 15)
    want = rr_area(60, 30, 3) * 15                    # reads ~0.8 mm^3 low once the body has a loft
    check("exact extrude after a loft, to 1e-5 of the part", p.volume() - v, want, tol=1e-5 * p.volume())
    v = p.volume()
    p.select_face(55, 65, 0, "+Y"); p.start_sketch(); p.rect((-58, 65, -28), (58, 65, 28), r=1)
    p.cut("Vent bore", 15)
    check("exact cut after a loft", v - p.volume(), rr_area(58, 28, 1) * 15, tol=1e-5 * p.volume())
    p.close()

with Part() as p:                                    # loft cut: circle mouth -> rounded-rect floor
    block(p, 20, 20, 30)
    v = p.volume()
    p.select_face(15, 30, 15, "+Y"); p.start_sketch(); p.circle((0, 30, 0), 12); s1 = p.end_sketch("Mouth")
    p.plane("P10", "Top Plane", 10)
    p.select_plane("P10"); p.start_sketch(); p.rect((-14, 10, -6), (14, 10, 6), r=2); s2 = p.end_sketch("Floor")
    p.loft_cut("Socket", [s1, s2])
    est_ok(v - p.volume(), circle_loft_estimate(((0, 30, 0), 12), [(-14, 10, -6), (14, 10, 6)], r=2),
           7e-4, 1.3e-3, "loft cut circle R12 -> 28x12 R2")
    p.close()

with Part() as p:                                    # square with 6 corners -> hexagon: ruled, exact
    sq6 = [(8, 0, 0), (8, 0, -8), (-8, 0, -8), (-8, 0, 0), (-8, 0, 8), (8, 0, 8)]   # polygon()'s turn
    hexagon = []
    s = two_profiles(p, lambda p: p.polyline(sq6),
                     lambda p: hexagon.extend(p.polygon((0, 20, 0), 6, radius=10)))
    p.loft("Square to hexagon", s)
    check("6-corner square -> hexagon loft = loft_volume()", p.volume(), loft_volume(sq6, hexagon))
    p.close()

with Part() as p:                                    # three profiles: smooth through the middle
    p.select_plane("Top Plane"); p.start_sketch(); p.rect((-10, 0, -10), (10, 0, 10)); s1 = p.end_sketch("S1")
    p.plane("P10", "Top Plane", 10); p.plane("P20", "Top Plane", 20)
    p.select_plane("P10"); p.start_sketch(); p.rect((-7.5, 10, -7.5), (7.5, 10, 7.5)); s2 = p.end_sketch("S2")
    p.select_plane("P20"); p.start_sketch(); p.rect((-5, 20, -5), (5, 20, 5)); s3 = p.end_sketch("S3")
    p.loft("Three in line", [s1, s2, s3])
    check("three collinear squares loft = frustum", p.volume(), frustum(20, 10, 20))
    p.close()

with Part() as p:                                    # a fat middle profile: the loft bulges to it
    p.select_plane("Top Plane"); p.start_sketch(); p.rect((-10, 0, -10), (10, 0, 10)); s1 = p.end_sketch("S1")
    p.plane("P10", "Top Plane", 10); p.plane("P20", "Top Plane", 20)
    p.select_plane("P10"); p.start_sketch(); p.rect((-12, 10, -12), (12, 10, 12)); s2 = p.end_sketch("S2")
    p.select_plane("P20"); p.start_sketch(); p.rect((-10, 20, -10), (10, 20, 10)); s3 = p.end_sketch("S3")
    p.loft("Barrel", [s1, s2, s3])
    same("three-profile barrel: widest exactly at the middle profile (tight bbox)", [p.bbox()],
         [(-12, 0, -12, 12, 20, 12)])
    p.close()

with Part() as p:                                    # rounded rectangles on Front Plane
    p.select_plane("Front Plane"); p.start_sketch(); p.rect((-10, -6, 0), (10, 6, 0), r=3); s1 = p.end_sketch("S1")
    p.plane("F15", "Front Plane", 15)
    p.select_plane("F15"); p.start_sketch(); p.rect((-6, -4, 15), (6, 4, 15), r=1); s2 = p.end_sketch("S2")
    p.loft("Rounded taper", [s1, s2])
    want = 15 / 6 * (rr_area(10, 6, 3) + 4 * rr_area(8, 5, 2) + rr_area(6, 4, 1))
    check("rounded-rect loft on Front Plane (Simpson, to 2e-4)", p.volume(), want, tol=want * 2e-4)
    same("  went +Z", [p.bbox()], [(-10, -6, 0, 10, 6, 15)])
    p.close()

with Part() as p:                                    # loft cut: tapered square socket
    block(p, 15, 15, 20)
    v = p.volume()
    p.select_face(0, 20, 0, "+Y"); p.start_sketch(); p.rect((-5, 20, -5), (5, 20, 5)); s1 = p.end_sketch("Mouth")
    p.plane("P15", "Top Plane", 15)
    p.select_plane("P15"); p.start_sketch(); p.rect((-3, 15, -3), (3, 15, 3)); s2 = p.end_sketch("Floor")
    p.loft_cut("Socket", [s1, s2])
    check("loft cut: square socket 10 -> 6 over 5 mm", v - p.volume(), frustum(10, 6, 5))
    p.close()

# renders: snap() turns the floor shadow off - in *Top it looked like a block beside the part
def shadow_free(doc, label):
    """Brightness 5 mm left of a 40 x 20 block in a *Top close-up (the shadow fell there)."""
    rows = read_png(doc.snap("shadow_" + label, "*Top", box=(-35, 15, -15, 25, 15, 15)))[2]
    c, r = doc.pixel((-25, 15, 0))
    return rows[round(r)][3 * round(c)]


with Part(OUT / "st_shadow.SLDPRT") as p:
    block(p, 20, 10, 15)
    p.save()
    p._plain_scene = True                            # control: SolidWorks' default scene first
    dark = shadow_free(p, "default")
    p._plain_scene = False                           # then as snap() normally renders
    g = shadow_free(p, "part")
    ok = g > 170 and dark < 160
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  part *Top snap has no floor shadow: grey {g} beside the part "
          f"(default scene: {dark})")
    with Assembly(OUT / "st_shadow.SLDASM") as a:
        a.add(p.path)
        g = shadow_free(a, "asm")
        ok = g > 170
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  assembly *Top snap has no floor shadow: grey {g}")
        a.close()
    p.close()

# shell: every remaining face moves in by exactly t (square to the face), or out with outward=True
TOP = [(10, 20, 0, "+Y")]                           # the 20 mm block's top face, clear of a centre hole
with Part(OUT / "st_shell.SLDPRT") as p:
    block(p)                                        # 40 x 20 x 30 -> open-top box, 2 mm walls
    v = p.volume()
    p.shell("Shell", 2, TOP)
    check("shell 2 mm, top open = (40-4)(30-4)(20-2)", v - p.volume(), 36 * 26 * 18)
    same("  outside unchanged", [p.bbox()], [(-20, 0, -15, 20, 20, 15)])
    p.save()
    with p.section("Z"):                             # walls and floor measure t in a cut-away
        for x0, label in ((-20, "left"), (18, "right")):
            closeup(p, f"shell_wall_{label}", "*Front", (x0 - 1, 8, 0, x0 + 3, 12, 0),
                    [((x, 0, 0), (x, 20, 0)) for x in (x0, x0 + 2)], label=f"shell {label} wall 2 mm")
        closeup(p, "shell_floor", "*Front", (-2, -1, 0, 2, 3, 0),
                [((-5, y, 0), (5, y, 0)) for y in (0, 2)], scan="col", label="shell floor 2 mm")
    p.close()

with Part() as p:
    block(p); v = p.volume()
    p.shell("Closed shell", 2)
    check("shell with no open face = closed hollow body", v - p.volume(), 36 * 26 * 16)
    check("  still one body", len(p.bodies()), 1, tol=0)
    p.close()

with Part() as p:
    block(p)
    p.shell("Outward shell", 2, TOP, outward=True)
    check("outward shell: the block becomes the cavity", p.volume(), 44 * 34 * 22 - 40 * 30 * 20)
    same("  bbox grows 2 mm except at the open top", [p.bbox()], [(-22, -2, -17, 22, 20, 17)])
    p.close()

with Part() as p:
    block(p); v = p.volume()
    p.shell("Two open faces", 2, TOP + [(0, 10, 15, "+Z")])
    check("shell with top and front open", v - p.volume(), 36 * 28 * 18)
    p.close()

for r, t in ((5, 2), (5, 6)):                        # rounded corners: r - t inside, sharp once t >= r
    with Part() as p:
        p.select_plane("Top Plane"); p.start_sketch()
        p.rect((-20, 0, -15), (20, 0, 15), r=r); p.extrude("Rounded block", 20)
        v = p.volume()
        p.shell("Shell", t, TOP)
        check(f"shell {t} mm of an R{r} rounded block (inner r = {max(r - t, 0)})", v - p.volume(),
              rr_area(20 - t, 15 - t, max(r - t, 0)) * (20 - t))
        p.close()

for fr, t in ((3, 2), (2, 3)):                       # filleted bottom loop, then shell
    with Part() as p:
        p.select_plane("Top Plane"); p.start_sketch()
        p.rect((-20, 0, -15), (20, 0, 15), r=5); p.extrude("Rounded block", 20)
        one = [e for e in p.edges(lambda e: e.lies_in("Y", 0)) if e.along("X")][:1]
        p.fillet("Bottom fillet", fr, one, propagate=True)
        v = p.volume()
        p.shell("Shell", t, TOP)
        cavity = rr_area(20 - t, 15 - t, 5 - t) * (20 - t) - (fillet_volume(fr - t, 4 * 15 + 4 * 10, 5 - t) if fr > t else 0)
        check(f"shell {t} mm after an r{fr} bottom fillet (inner fillet {max(fr - t, 0)})", v - p.volume(), cavity)
        p.close()

with Part() as p:                                    # trap: a hole cut before the shell becomes a tube
    block(p)
    p.select_face(0, 20, 0, "+Y"); p.start_sketch(); p.circle((0, 20, 0), 3); p.cut("Hole")
    v = p.volume()
    p.shell("Shell", 2, TOP)
    check("hole cut before the shell becomes a 2 mm tube", v - p.volume(),    # r3 bore was empty already,
          36 * 26 * 18 - math.pi * 5 ** 2 * 18)                               # the r3..r5 tube stays
    p.close()

with Part() as p:                                    # revolved frustum: inner wall a true offset
    p.select_plane("Front Plane"); p.start_sketch(); p.centreline((0, 0, 0), (0, 1, 0))
    p.polyline([(0, 0, 0), (15, 0, 0), (8, 20, 0), (0, 20, 0)]); p.revolve("Frustum")
    v = p.volume()
    p.shell("Shell", 2, [(0, 20, 0, "+Y")])
    rad = lambda y: 15 - 7 * y / 20 - 2 * math.hypot(7, 20) / 20      # side moved 2 mm square to itself
    check("shelled revolved frustum (true offset, cone frustum)", v - p.volume(),
          math.pi * 18 / 3 * (rad(2) ** 2 + rad(2) * rad(20) + rad(20) ** 2))
    p.close()

with Part() as p:                                    # lofted square frustum, same rule
    s = two_profiles(p, lambda p: p.rect((-10, 0, -10), (10, 0, 10)), lambda p: p.polyline(sqr(5, 20)))
    p.loft("Frustum", s)
    v = p.volume()
    p.shell("Shell", 2, [(0, 20, 0, "+Y")])
    hw = lambda y: 10 - y / 4 - 2 * math.hypot(1, 1 / 4)              # not a plain 2 mm corner inset
    check("shelled loft frustum (true offset)", v - p.volume(), frustum(2 * hw(2), 2 * hw(20), 18))
    p.close()

with Part() as p:                                    # too thick: SolidWorks adds nothing, silently
    block(p)
    try:
        p.shell("Too thick", 16, TOP); ok = False
    except RuntimeError:
        ok = p.features == ["Block"]
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  over-thick shell raises and adds no feature")
    p.close()

with Part(OUT / "st_shell_duct.SLDPRT") as p:        # circle -> rect duct: wall t square to its slope
    p.select_plane("Top Plane"); p.start_sketch(); p.circle((0, 0, 0), 15); s1 = p.end_sketch("Round")
    p.plane("P30", "Top Plane", 30)
    p.select_plane("P30"); p.start_sketch(); p.rect((-20, 30, -10), (20, 30, 10)); s2 = p.end_sketch("Rect")
    p.loft("Duct", [s1, s2])
    p.shell("Shell", 2, [(0, 0, 0, "-Y"), (0, 30, 0, "+Y")])
    p.save()
    with p.section("Z"):                             # in Z=0 the outer side runs x = 15 + y/6
        for x0, side in ((-20, 0), (14, 1)):
            W, H, rows = read_png(p.snap(f"shell_duct_{side}", "*Front", box=(x0, 12, 0, x0 + 6, 18, 0)))
            k = p._frame[3]
            def wall(y):                             # outer and inner edge x (mm) at height y
                c0, row = p.pixel((0, y, 0))
                xs = sorted((q - c0) / k for q in dark_runs(grey_row(rows, round(row))))
                return (xs[0], xs[1]) if side == 0 else (xs[-1], xs[-2])
            (o13, _), (o17, _) = wall(13), wall(17)
            slope = abs(o17 - o13) / 4
            o, i = wall(15)
            check(f"duct shell wall square to the slope, {'left' if side == 0 else 'right'} (mm)",
                  abs(o - i) * math.cos(math.atan(slope)), 2, tol=0.02)
    p.close()

with Part() as p:                                   # traps: crossing the axis, two centrelines
    p.select_plane("Front Plane"); p.start_sketch(); p.centreline((0, 0, 0), (0, 1, 0))
    p.rect((-3, 0, 0), (10, 20, 0))
    try:
        p.revolve("Across the axis"); ok = False
    except RuntimeError:
        ok = True
    p.select_plane("Front Plane"); p.start_sketch(); p.centreline((0, 0, 0), (0, 1, 0))
    try:
        p.centreline((0, -5, 0), (1, -5, 0)); ok = False
    except AssertionError:
        pass
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  profile across the axis raises; a second centreline is refused")
    p.sm.InsertSketch(True)
    p.close()

print(f"\n{sum(results)}/{len(results)} passed")
assert all(results), "selftest FAILED"
