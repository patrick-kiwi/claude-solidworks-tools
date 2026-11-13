"""Regression test for swlib: every feature checked against an exact, hand-derived volume.
Run after changing swlib:  sw_run.sh selftest.py   (builds throwaway parts in solidworks_work\\_selftest)"""
import math
from swlib import Part, workdir

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
    p.close()                                          # selftest leaves nothing open

with Part(OUT / "st_draft.SLDPRT") as p:
    p.select_plane("Top Plane"); p.start_sketch()
    p.rect((-10, 0, -10), (10, 0, 10)); p.extrude("Drafted boss", 10, draft_deg=4)
    check("boss 4 deg draft (shrinks)", p.volume(), frustum(20, 20 - 20 * TAN4, 10))
    v = p.volume()
    p.select_face(0, 10, 0, "+Y"); p.start_sketch()
    p.rect((-5, 10, -5), (5, 10, 5)); p.cut("Drafted pocket", 5, draft_deg=4)
    check("pocket 4 deg draft (narrows)", v - p.volume(), frustum(10, 10 - 10 * TAN4, 5))
    p.close()

with Part(OUT / "st_loop.SLDPRT") as p:
    p.select_plane("Top Plane"); p.start_sketch()
    p.rect((-20, 0, -15), (20, 0, 15), r=5); p.extrude("Rounded block", 10)
    loop = p.edges(lambda e: e.lies_in("Y", 10))
    one = [e for e in loop if e.along("X")][:1]
    v = p.volume()
    p.fillet("Loop fillet", 2, one, propagate=True)
    # Exact removal: section A = r^2(1-pi/4) swept along 2*(30+20) mm of straight sides, plus the
    # four quarter-turns at the R5 corners by Pappus: A * 2*pi * rho, where rho = R - xbar and
    # xbar = r(10-3pi)/(3(4-pi)) is the section centroid's distance in from the outer edge.
    r, R = 2, 5
    A = r * r * (1 - math.pi / 4)
    rho = R - r * (10 - 3 * math.pi) / (3 * (4 - math.pi))
    check(f"propagated fillet round a {len(loop)}-edge loop", v - p.volume(),
          A * 100 + A * 2 * math.pi * rho)

    # chamfer the bottom loop by propagation: triangle section d^2/2, centroid d/3 in from the edge
    v = p.volume()
    bottom = [e for e in p.edges(lambda e: e.lies_in("Y", 0)) if e.along("X")][:1]
    d = 1
    p.chamfer("Loop chamfer", d, bottom, propagate=True)
    A = d * d / 2
    check("propagated chamfer round the loop", v - p.volume(),
          A * 100 + A * 2 * math.pi * (R - d / 3))
    p.close()

print(f"\n{sum(results)}/{len(results)} passed")
assert all(results), "selftest FAILED"
