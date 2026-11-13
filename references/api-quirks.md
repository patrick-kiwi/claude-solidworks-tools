# Raw SolidWorks API: known behaviour

Read this before calling the SolidWorks API directly (`p.sm`, `p.doc`, anything `swlib` doesn't
wrap) or when a raw call fails strangely. Look calls up with `scripts/sw_api.sh` first.

- **Late binding quirks.** Under pywin32's dynamic dispatch some no-arg methods come back as
  bound methods (wrap results in `val()`), while others are auto-invoked as properties so
  writing `()` calls the *result* and fails with "Member not found" (`GetMathUtility`,
  `Inverse`). If a call fails that way, try it without parentheses, or with `val()`.
- **Arrays and out-params.** Pass arrays of doubles as `VARIANT(VT_ARRAY | VT_R8, [...])`, and
  "Nothing" object args (including unused array args, and `SelectData`) as `swlib.NOTHING`.
  Methods with by-reference out-params can fail with "Parameter not optional"
  (`Feature.GetErrorCode2`); look for an older variant without them (`GetErrorCode`).
- **Entity methods work on edges/faces directly**: `edge.Select4(True, NOTHING)` works under
  late binding, no QueryInterface needed.
- **Units.** The raw API is metres; `swlib.MM = 1e-3`.
- **Speed.** Each COM call from WSL costs ~20 ms, so a loop over geometry (every edge, face or
  component) can take many seconds. Wrap such read-only loops in `with swlib.batch_calls():`
  (sets `CommandInProgress`, ~20x-60x faster, restored on exit); `edges()` already does.
- **`ViewZoomTo2`** takes its corners in the view's screen frame, not model space - it only
  looks right in *Front, where they coincide (handled by `snap(box=)`).
- **`GetBodyBox` is loose around spline faces** (lofts): +-13 mm for a loft whose true extent
  is +-12. `Part.bbox()` uses `GetExtremePoint` per axis instead, which is tight; component
  boxes in assemblies (`Assembly.box`/`bbox`) still come from SolidWorks' boxes.
- **`AddComponent5`** positions the component's bounding-box centre, not its origin (handled
  in `Assembly.add`).
- **Enum values** aren't available by name under late binding; look them up with
  `sw_api.sh -Enum` and name them as constants at the top of `swlib.py`.
- **Draft direction**: for both extrude and cut, `Ddir1=False` (swlib's default) shrinks the
  profile as the feature progresses - verified against frustum volumes.
- **`FeatureExtrusion2`/`FeatureCut4` argument 2 ("Flip") is not a direction.** It flips the
  side to cut and does nothing to a boss; argument 3 ("Dir") reverses (swlib's `reverse=`).
