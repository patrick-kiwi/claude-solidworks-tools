"""Box with a tapered (drafted) lid fit, for 3D printing.

A lid whose lip is a tight vertical fit in the box binds or rattles once printing tolerances
creep in. Here the top LIP_D of the box cavity is a seat drafted at DRAFT degrees, and the lid's
lip is drafted to the same profile: the tapered faces are parallel, so the lid self-centres as
it goes down and the gap only closes up as it seats. Also shows fillets: concave (floor-to-wall
inside the box) and convex (outer edges).

Fit: "rim stop". The lid plate rests on the rim, which sets the closed height, and the lip is
undersize by FIT_CLEAR per side so print error can't make it wedge before the plate lands
(with a taper, a lip just 0.1 mm oversize per side would sit 0.1/tan(4deg) = 1.4 mm high).
Set FIT_CLEAR = 0 for nominal geometry (faces fully touching when closed); tune after a test print.

Frame: Y up, box centred on the origin, footprint on Top Plane. Lid origin sits on the rim (Y=H).
Every feature is checked against an exact volume; the taper fit is checked by comparing the
lip's and seat's edge loops at the top and bottom of the taper.
"""
import math
from swlib import Part, Assembly, workdir, rr_area, drafted_volume, fillet_volume, assert_close

OUT = workdir("tapered_lid_box")

OX, OZ, H, R_OUT = 35.0, 25.0, 30.0, 4.0      # outer half-extents, height, corner radius
WALL, FLOOR = 2.0, 2.0
IX, IZ, R_IN = OX - WALL, OZ - WALL, 2.0       # cavity half-extents and corner radius
# R_IN = R_OUT - WALL keeps the wall uniform round the corners (smaller: thicker there, fine;
# larger: thinner). With R_OUT <= WALL, use a small R_IN (e.g. 1) and accept thick corners.
# keep F_FLOOR <= R_IN and the outer fillets <= R_OUT so the exact fillet volumes apply.
LIP_D, DRAFT = 4.0, 4.0                        # taper depth (mm) and angle (deg)
FIT_CLEAR = 0.15                               # lip undersize per side (rim-stop fit)
T = 2.0                                        # lid plate thickness
LIP_W = 1.6                                    # lip wall thickness at its bottom
F_FLOOR, F_BASE, F_LID = 1.5, 1.0, 1.5         # fillet radii
t = LIP_D * math.tan(math.radians(DRAFT))      # taper's inset over its depth (0.28 mm)


# ---- helpers ----------------------------------------------------------------------------
def x_extent(part, y):
    """Half-width of the edge loop lying in the plane Y=y, ignoring the outer perimeter
    (the outer wall's edges share those planes: the rim, and the lid plate's underside)."""
    inside = lambda e: all(abs(p[0]) < OX - 0.1 and abs(p[2]) < OZ - 0.1 for p in (e.start, e.mid, e.end))
    es = part.edges(lambda e: e.lies_in("Y", y) and inside(e))
    assert es, f"no edges at Y={y}"
    return max(abs(c) for e in es for c in (e.start[0], e.mid[0], e.end[0]))


# ---- base ---------------------------------------------------------------------------------
with Part(OUT / "tl_base.SLDPRT") as b:
    b.select_plane("Top Plane"); b.start_sketch()
    b.rect((-OX, 0, -OZ), (OX, 0, OZ), r=R_OUT); b.extrude("Body", H)
    assert_close("body", b.volume(), rr_area(OX, OZ, R_OUT) * H)

    v = b.volume()
    b.select_face(0, H, 0, "+Y"); b.start_sketch()
    b.rect((-IX, H, -IZ), (IX, H, IZ), r=R_IN); b.cut("Cavity", H - FLOOR)
    assert_close("cavity", v - b.volume(), rr_area(IX, IZ, R_IN) * (H - FLOOR))

    # tapered seat: from the rim, narrowing with depth until it is flush with the cavity wall
    v = b.volume()
    b.select_face(OX - WALL / 2, H, 0, "+Y"); b.start_sketch()
    b.rect((-IX - t, H, -IZ - t), (IX + t, H, IZ + t), r=R_IN + t)
    b.cut("Tapered seat", LIP_D, draft_deg=DRAFT)
    assert_close("seat", v - b.volume(),
                 drafted_volume(IX + t, IZ + t, R_IN + t, LIP_D, DRAFT) - rr_area(IX, IZ, R_IN) * LIP_D)

    # concave fillet where the floor meets the walls (one edge + propagate = the whole loop)
    v = b.volume()
    floor_edge = b.edges(lambda e: e.lies_in("Y", FLOOR) and e.lies_in("Z", -IZ) and e.along("X"))
    b.fillet("Floor fillet", F_FLOOR, floor_edge, propagate=True)
    straight = 4 * (IX - R_IN) + 4 * (IZ - R_IN)
    assert_close("floor fillet (adds)", b.volume() - v, fillet_volume(F_FLOOR, straight, R_IN))

    # convex fillet round the bottom outside edge
    v = b.volume()
    bottom_edge = b.edges(lambda e: e.lies_in("Y", 0) and e.lies_in("Z", -OZ) and e.along("X"))
    b.fillet("Base edge fillet", F_BASE, bottom_edge, propagate=True)
    straight = 4 * (OX - R_OUT) + 4 * (OZ - R_OUT)
    assert_close("base edge fillet (removes)", v - b.volume(), fillet_volume(F_BASE, straight, R_OUT))

    seat_top, seat_bottom = x_extent(b, H), x_extent(b, H - LIP_D)
    b.report(); b.save(); b.snaps("base", ("*Isometric", "*Top"))

# ---- lid ----------------------------------------------------------------------------------
with Part(OUT / "tl_lid.SLDPRT") as l:
    l.select_plane("Top Plane"); l.start_sketch()
    l.rect((-OX, 0, -OZ), (OX, 0, OZ), r=R_OUT); l.extrude("Plate", T)

    # lip: same profile as the seat's top, drafted by the same angle as it grows downward
    v = l.volume()
    l.select_face(0, 0, 0, "-Y"); l.start_sketch()
    c = FIT_CLEAR
    l.rect((-IX - t + c, 0, -IZ - t + c), (IX + t - c, 0, IZ + t - c), r=R_IN + t - c)
    l.extrude("Tapered lip", LIP_D, draft_deg=DRAFT)
    assert_close("lip", l.volume() - v, drafted_volume(IX + t - c, IZ + t - c, R_IN + t - c, LIP_D, DRAFT))

    v = l.volume()
    l.select_face(0, -LIP_D, 0, "-Y"); l.start_sketch()
    l.rect((-IX + LIP_W, -LIP_D, -IZ + LIP_W), (IX - LIP_W, -LIP_D, IZ - LIP_W), r=0.5)
    l.cut("Lip hollow", LIP_D)
    assert_close("lip hollow", v - l.volume(), rr_area(IX - LIP_W, IZ - LIP_W, 0.5) * LIP_D)

    v = l.volume()
    top_edge = l.edges(lambda e: e.lies_in("Y", T) and e.lies_in("Z", -OZ) and e.along("X"))
    l.fillet("Lid edge fillet", F_LID, top_edge, propagate=True)
    straight = 4 * (OX - R_OUT) + 4 * (OZ - R_OUT)
    assert_close("lid edge fillet", v - l.volume(), fillet_volume(F_LID, straight, R_OUT))

    lip_top, lip_bottom = x_extent(l, 0), x_extent(l, -LIP_D)
    l.report(); l.save(); l.snaps("lid", ("*Isometric", "*Bottom", "*Front"))

# ---- the fit ------------------------------------------------------------------------------
print(f"taper half-width  top: seat {seat_top:.3f} / lip {lip_top:.3f}   "
      f"bottom: seat {seat_bottom:.3f} / lip {lip_bottom:.3f}")
# same taper, lip inset by exactly FIT_CLEAR all the way down
assert abs(seat_top - lip_top - FIT_CLEAR) < 1e-3 and abs(seat_bottom - lip_bottom - FIT_CLEAR) < 1e-3, \
    "lip and seat tapers are not parallel at FIT_CLEAR"
assert abs(seat_top - seat_bottom - t) < 1e-3, "taper inset is not LIP_D*tan(DRAFT)"

with Assembly(OUT / "tl_box.SLDASM") as a:
    a.add(OUT / "tl_base.SLDPRT")
    lid = a.add(OUT / "tl_lid.SLDPRT", origin=(0, H, 0))
    assert abs(Assembly.box(lid)[1] - (H - LIP_D)) < 1e-3, "lid not seated"
    assert not a.interference(), "lid and base clash"
    print("closed size", a.bbox())             # outer size of the closed box
    assert a.bbox() == (-OX, 0, -OZ, OX, H + T, OZ), "closed box is not the intended size"
    a.save(); a.snaps("asm", ("*Isometric", "*Front"))
    with a.section("Z"):                       # cut-away through the middle: lip in its seat
        a.snaps("asm_section", ("*Front", "*Isometric"))

for h in (0, 0.5, 1, 2):
    gap = (FIT_CLEAR + h * math.tan(math.radians(DRAFT))) * math.cos(math.radians(DRAFT))
    print(f"lid lifted {h} mm -> gap between tapered faces {gap:.3f} mm")
print("ALL CHECKS PASSED")
