# Close-ups and measuring in images

Read this when a detail is too small for a whole-model image (gaps, taper steps, wall
thicknesses under a few mm) or when you need a number from a PNG rather than a look.

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
