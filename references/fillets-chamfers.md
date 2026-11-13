# Fillets and chamfers: sizes, order, rounding a whole part

Read this before filleting or chamfering. Finding the edges is in SKILL.md ("Selecting edges").

- Fillet a concave edge (floor meeting wall) and SolidWorks adds material; a convex edge loses it.
- A fillet bigger than it can properly fit often does **not** fail: SolidWorks builds a
  different shape and the image looks right. Measured: r2 on the edge of a 1.5 mm plate, and
  a concave r1.5 floor fillet in a pocket with R1 corners, both "succeeded" with the wrong
  volume. Up to the limit is fine and exact: r equal to the plate thickness (r2 on a 2 mm
  plate), r equal to the corner radius. So keep r <= the height of the faces either side and
  <= the loop's corner radius, and let `fillet_volume` catch it when you don't. Only when the
  fillet can't be built at all does the feature return None (the library then raises).
- Do fillets last, after the cuts that define the edges; filleting first changes the edges
  later cuts and selections rely on.
- Vertical corners of a footprint are simplest rounded in the sketch (`rect(..., r=)`); use a
  fillet when the edge only exists after several features. A fillet whose radius equals an
  adjacent corner radius is fine (it blends into a spherical corner). So for "round all the
  outside edges 2 mm": sketch the footprint with corner r = 2, then fillet the top and bottom
  loops with r = 2 (a box's cavity corners can then be smaller than the outside ones).

**Checking the volume.** On a straight edge a fillet removes (convex) or adds (concave)
r^2*(1-pi/4)*length and a chamfer d^2/2*length. To round a corner of radius R, the section area
times 2*pi*(R - centroid offset) per full turn - offset d/3 for a chamfer, r(10-3pi)/(3(4-pi))
for a fillet. `fillet_volume(r, straight_len, corner_r)` / `chamfer_volume(...)` do both (a
straight edge, or a whole rounded-rect loop with Pappus corners).
