"""Dev tool for eval runs: close documents created by eval agents, examples and selftests
(paths under solidworks_work\\eval*, _*, tapered_lid_box) - run between eval cases:
    scripts/sw_run.sh evals/close_eval_docs.py
Never touches anything else (the user's documents)."""
from swlib import app, open_docs, _doc_path
sw = app()
def ours(p):
    parts = [x.lower() for x in p.parts]
    if "solidworks_work" not in parts: return False
    proj = parts[parts.index("solidworks_work") + 1] if len(parts) > parts.index("solidworks_work") + 1 else ""
    return proj.startswith(("eval", "_")) or proj == "tapered_lid_box"
for kind in (".sldasm", ".sldprt"):
    for d in open_docs(sw):
        p = _doc_path(d)
        if p.suffix.lower() == kind and ours(p):
            sw.CloseDoc(d.GetTitle); print("closed", p)
print("still open:", [str(_doc_path(d)) for d in open_docs(sw)])
