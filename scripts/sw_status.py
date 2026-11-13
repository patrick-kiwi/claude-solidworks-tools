"""Preflight: is SolidWorks reachable, which version, what's the user looking at?"""
from swlib import app, val

sw = app()
print(f"SolidWorks connected: API revision {sw.RevisionNumber}")
doc = sw.ActiveDoc
if doc is None:
    print("active document: none")
else:
    kind = {1: "Part", 2: "Assembly", 3: "Drawing"}.get(doc.GetType, doc.GetType)
    dirty = " (UNSAVED CHANGES)" if val(doc.GetSaveFlag) else ""
    print(f"active document: {doc.GetTitle} [{kind}]{dirty}")
