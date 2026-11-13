"""Lid for rpi_base: same X/Z frame; its origin sits at base Y = 29 when assembled."""
from swlib import Part, workdir

OUT = workdir("rpi_enclosure")
T = 2.0                       # plate thickness
OX, OZ = 46.0, 31.5           # matches the base's outer size
LX, LZ = 43.8, 29.3           # lip outer: 0.2 mm clearance inside the base's 44 x 29.5 cavity
LIP_W, LIP_D = 1.5, 3.0
bxX = lambda bx: bx - 42.5

with Part(OUT / "rpi_lid.SLDPRT") as p:
    p.select_plane("Top Plane"); p.start_sketch()
    p.rect((-OX, 0, -OZ), (OX, 0, OZ), r=3); p.extrude("Plate", T)

    # locating lip hanging down inside the base walls
    p.select_face(0, 0, 0, "-Y"); p.start_sketch()
    p.rect((-LX, 0, -LZ), (LX, 0, LZ), r=0.8); p.extrude("Lip", LIP_D)
    p.select_face(0, -LIP_D, 0, "-Y"); p.start_sketch()
    p.rect((-LX + LIP_W, -LIP_D, -LZ + LIP_W), (LX - LIP_W, -LIP_D, LZ - LIP_W), r=0.5)
    p.cut("Lip hollow", LIP_D)

    # tab closing the top of the base's USB/Ethernet notch (notch spans X 44..46, Z +-27)
    p.select_face(45, 0, 0, "-Y"); p.start_sketch()
    p.rect((44.2, 0, -26.8), (OX, 0, 26.8)); p.extrude("Notch tab", 3.5)

    # vent slots over the SoC (board ~bx 29, by 32 -> X -13.5, Z -4)
    p.select_face(30, T, 20, "+Y"); p.start_sketch()
    for i in range(7):
        x = bxX(29) + (i - 3) * 5
        p.rect((x - 1, T, -19), (x + 1, T, 11), r=0.9)
    p.cut("Vents")            # through all

    p.report()
    p.save()
    p.snaps("lid", ("*Isometric", "*Bottom"))
