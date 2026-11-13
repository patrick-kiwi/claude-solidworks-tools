"""Raspberry Pi 4/5 enclosure - base.

Frame: X = board length, Z = board width, Y = up. The 85 x 56 board is centred on the origin;
board-local (bx, by) maps to X = bx - 42.5, Z = 28 - by.
HDMI/USB-C side faces +Z (front), USB/Ethernet end faces +X, microSD end faces -X."""
from swlib import Part, workdir

OUT = workdir("rpi_enclosure")
WALL, FLOOR, H = 2.0, 2.0, 29.0          # H = outer height; lid sits on the rim
IX, IZ = 44.0, 29.5                      # inner half-extents (1.5 mm clearance round the board)
OX, OZ = IX + WALL, IZ + WALL
STANDOFF_H = 5.0
BOARD_BOT = FLOOR + STANDOFF_H           # 7.0
BOARD_TOP = BOARD_BOT + 1.6              # 8.6
bxX = lambda bx: bx - 42.5
HOLES = [(bxX(bx), 28 - by) for bx in (3.5, 61.5) for by in (3.5, 52.5)]   # 58 x 49 pattern

with Part(OUT / "rpi_base.SLDPRT") as p:
    p.select_plane("Top Plane"); p.start_sketch()
    p.rect((-OX, 0, -OZ), (OX, 0, OZ), r=3); p.extrude("Body", H)
    p.select_face(0, H, 0, "+Y"); p.start_sketch()
    p.rect((-IX, H, -IZ), (IX, H, IZ), r=1); p.cut("Cavity", H - FLOOR)

    # standoffs + M2.5 self-tap holes
    p.select_face(0, FLOOR, 0, "+Y"); p.start_sketch()
    for x, z in HOLES: p.circle((x, FLOOR, z), 3.0)
    p.extrude("Standoffs", STANDOFF_H)
    p.select_face(HOLES[0][0], BOARD_BOT, HOLES[0][1], "+Y"); p.start_sketch()
    for x, z in HOLES: p.circle((x, BOARD_BOT, z), 1.1)
    p.cut("Standoff holes", STANDOFF_H)

    # +X end: USB + Ethernet. Open-topped notch so the overhanging jacks can drop in.
    p.select_face(OX, 15, 0, "+X"); p.start_sketch()
    p.rect((OX, BOARD_TOP - 0.6, -27), (OX, H + 1, 27)); p.cut("USB-Ethernet opening", WALL + 1)

    # +Z front: USB-C, 2x micro-HDMI, audio (Pi 4)
    p.select_face(0, 20, OZ, "+Z"); p.start_sketch()
    cy = BOARD_TOP + 1.6
    p.rect((bxX(11.2) - 6, cy - 3.5, OZ), (bxX(11.2) + 6, cy + 3.5, OZ), r=1)
    for bx in (26.0, 39.5):
        p.rect((bxX(bx) - 5.5, cy - 3.5, OZ), (bxX(bx) + 5.5, cy + 3.5, OZ), r=1)
    p.circle((bxX(54.0), BOARD_TOP + 3.2, OZ), 3.5)
    p.cut("Front ports", WALL + 1)

    # -X end: microSD slot (card sits under the board)
    p.select_face(-OX, 20, 0, "-X"); p.start_sketch()
    p.rect((-OX, FLOOR + 1, -8), (-OX, BOARD_BOT + 0.5, 8), r=1); p.cut("microSD slot", WALL + 1)

    p.report()
    p.save()
    p.snaps("base", ("*Isometric", "*Front", "*Right"))
