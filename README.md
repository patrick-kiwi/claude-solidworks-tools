# solidworks-skill

A standalone [Claude Code](https://claude.com/claude-code) skill that lets Claude drive a running
SolidWorks on the Windows host from WSL: it builds parts and assemblies from Python scripts via the
COM API, then checks its own work with rendered images, measurements and interference detection.

## Install

```bash
git clone <this repo> ~/repos/solidworks-skill
ln -s ~/repos/solidworks-skill ~/.claude/skills/solidworks
```

Requirements: WSL on a Windows machine with SolidWorks (tested: 2026), and a Windows Python with
`pywin32` (`pip install pywin32`). `scripts/sw_run.sh` finds that Python automatically (or set
`SW_PYTHON=/mnt/c/.../python.exe`).

## Layout

- `SKILL.md` - what Claude reads: workflow, API reference, gotchas
- `scripts/swlib.py` - helper library (mm, model-space; verified face picking; assemblies by origin)
- `scripts/sw_run.sh` - run a build script under Windows Python from WSL
- `scripts/sw_status.py` - preflight check
- `scripts/sw_api.sh` - offline API signature / enum lookup
- `scripts/selftest.py` - regression test against exact volumes
- `examples/rpi_enclosure/` - Raspberry Pi 4/5 case: base, lid, assembly
- `examples/tapered_lid_box/` - box with a 4-degree tapered lid fit and fillets
- `evals/` - test prompts and grading criteria (skill-creator / `claude plugin eval` format)

## Scope

Only techniques proven in practice: rectangle/circle sketches on Top Plane and flat axis-aligned
faces, extrudes and blind/through-all cuts (optionally drafted), edge selection by geometry,
fillets (single edges or tangent loops, convex or concave), 45-degree chamfers, assemblies placed
by origin, interference checks, section views. `scripts/selftest.py` checks each against exact volumes. New
techniques get added once they've been verified; `scripts/sw_api.sh` looks up API signatures and
enum values offline to help.
