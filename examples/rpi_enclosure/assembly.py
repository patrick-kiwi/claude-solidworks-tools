"""Seat the lid on the base and check for clashes. Run base.py and lid.py first."""
from swlib import Assembly, workdir

OUT = workdir("rpi_enclosure")
with Assembly(OUT / "rpi_enclosure.SLDASM") as a:
    a.add(OUT / "rpi_base.SLDPRT", origin=(0, 0, 0))
    a.add(OUT / "rpi_lid.SLDPRT", origin=(0, 29, 0))     # lid origin on the base rim
    clashes = a.interference()
    a.save()
    a.snaps("asm", ("*Isometric", "*Right"))
    assert not clashes, f"parts interfere: {clashes}"
