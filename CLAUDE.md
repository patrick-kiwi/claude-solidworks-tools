# claude-solidworks-tools

A standalone Claude Code skill (`solidworks`) that drives the user's running SolidWorks from WSL
over COM, builds parts/assemblies from Python scripts, and verifies them with rendered images,
exact volumes and interference checks. `SKILL.md` is what the skill-using agent reads (workflow,
API, gotchas) - read it first; this file is for *developing* the skill.

## Environment (this machine)

- WSL Ubuntu 22.04 on Windows; SolidWorks Premium 2026 (API rev 34) installed at
  `D:\Program Files\SolidWorks\SOLIDWORKS` - it must be running (the user starts it).
- Installed as a skill by symlink: `~/.claude/skills/solidworks -> ~/repos/solidworks-skill`
  (this repo). Edits here are live for every session.
- Windows Python with pywin32: auto-found by `scripts/sw_run.sh`, cached in
  `~/.config/solidworks-skill/python` (currently the `chemdraw` conda env).
- CAD output and PNGs go to `C:\Users\Patrick\solidworks_work\<project>` (`/mnt/c/...` from WSL).
- GitHub: `git@github.com:patrick-kiwi/claude-solidworks-tools.git` (SSH auth works).

## Working rules (agreed with the user)

- **Standalone and proven-only.** Keep this separate from the claude-custom-skills /
  scientific-skills collection. Only document and wrap techniques that have been verified.
- **Adding a technique:** look up the call with `scripts/sw_api.sh` (offline reflection over the
  install's interop DLLs) -> prototype in a throwaway part whose result is exactly computable ->
  add to `swlib.py` with gotchas in the docstring -> add a case to `scripts/selftest.py` ->
  run it -> document in `SKILL.md`. A returned feature is not proof (the "equal distance"
  chamfer returns a feature and removes nothing) - check volume and an image.
- **Run the selftest after any swlib change:** `scripts/sw_run.sh scripts/selftest.py`
  (~2.5 min, currently 77/77; it closes its own documents).
- **One SolidWorks instance:** never run two SolidWorks jobs at once - test subagents run one at
  a time, and don't use SolidWorks yourself while one is running.
- **The user's documents:** never close or modify SolidWorks documents this work didn't create.
- Commits end with the `Co-Authored-By: Claude ...` line; push to origin when asked.

## Testing the skill (skill-creator loop)

- Test cases live in `evals/<case>/` (prompt.md, case.yaml, graders/) - skill-creator /
  `claude plugin eval` format. Five cases: l-bracket-vertical-holes, perfboard-box-with-lid,
  desk-cable-organizer, tapered-lid-sd-card-box, filleted-chamfered-plate.
- Runs: one general-purpose subagent per case, given the skill path + prompt, told to put
  scripts/PNGs/run_log.txt/final_message.md/skill_issues.md in
  `~/repos/solidworks-skill-workspace/iteration-N/<case>/with_skill/outputs/` (outside this
  repo, local only) and to use `workdir("eval-<name>")`. No baseline runs (user agreed: light
  testing). Save each run's timing.json from the task notification, grade into grading.json.
- Aggregate + viewer (skill-creator lives under `~/.claude/skills/synced/*/skill-creator`):
  `python3 -m scripts.aggregate_benchmark <iteration dir> --skill-name solidworks`, then
  `eval-viewer/generate_review.py <iteration dir> --skill-name solidworks --benchmark ... --static
  /mnt/c/Users/Patrick/solidworks_work/solidworks_skill_review_iterN.html` and open it with
  `explorer.exe`.
- Each agent's `skill_issues.md` has been the most useful signal - read them all.

## History

- Iteration 1 (3 basic cases): 16/16, but found a silent-save bug on re-runs (open assembly held
  the old part) -> fixed: `_clear_target` closes the project's assemblies, `save()` verifies.
- Iteration 2 (same cases): 16/16; perfboard 326 s -> 172 s.
- Iteration 3 (draft/fillet/chamfer cases): 12/12 first try. The SD-box agent took 829 s,
  mostly building cut-away half-copies by hand -> section views were then added
  (`with doc.section("Z"): ...`, display-only).
- Iteration 4 (SD box only): 6/6, 829 s -> 363 s; the agent used `section()` three times and
  built no half-copies. Its feedback led to: `edges()` was ~13 s per call (each COM call ~20 ms
  out-of-process) -> `batch_calls()` (`CommandInProgress`), now 0.2 s - the tapered-lid example
  went to 36 s end to end; exact-volume helpers moved into swlib; `Assembly.bbox()`; proven that
  over-size fillets (r > face height or > pocket corner radius) silently build the wrong shape.
- Roadmap items 1-3 (close-ups, Front/Right/offset planes, revolves) brought the selftest to
  59; item 4 (polygons, lofts) to 77. Loft finding: corners pair by pick point, else by sketch winding -> silent twist;
  `loft()` always picks. `bbox()` now tight (`GetExtremePoint`).
- Design insight now in SKILL.md: a taper turns size error into height error (e/tan(angle));
  default to a rim-stop fit with lip clearance (`FIT_CLEAR` in examples/tapered_lid_box).

## Open items / next steps

1. Re-run all five evals (iteration 5) to measure the batch_calls() speed-up end to end
   (none of the five uses revolves or lofts yet - a funnel / knob-with-hex-socket case
   would show whether agents find and use them).
2. Test hygiene: agents can see `evals/` file names via `ls` of the skill dir (none opened
   them). Consider moving grading material outside the skill directory before larger runs.
3. Techniques to prove next: **see ROADMAP.md** (agreed order: ~~close-ups~~ (done), ~~Front/Right and
   offset reference planes~~ (done), ~~revolves~~ (done), ~~polygons + lofts~~ (done); **shell is next** (hand-off notes in ROADMAP item 5), then patterns, mirror, sweep,
   rib, countersinks, editing existing files). STL/STEP export is deliberately left to the user.
4. Optionally run skill-creator's description optimisation for triggering accuracy.
