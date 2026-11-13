"""Downloads the pictures of every format-2 episode WITHOUT rendering (so they can be checked first)."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v2
u = v2.urdu_setup()
print("URDU FONT USED:", u.get("mode"), u["path"].name if u.get("path") else "NONE")
for f in sorted((HERE.parent / "episodes").glob("tk*.json")):
    if f.name.endswith("_old.json") or f.stem == "tk003": continue
    d = json.loads(f.read_text(encoding="utf-8"))
    if d.get("format") != 2: continue
    ep = f.stem
    print(f"=== {ep} ===")
    d2 = dict(d); d2.pop("rerender_v", None)      # pictures only: never touch the render markers
    v2.purge_banned(ep, d2)
    got, miss = v2.fetch_pictures(ep, d["scenes"])
    print(f"  new pictures: {got}   without picture: {miss}")
print("\nDONE. Tell Claude 'pictures done'. Nothing was rendered.")
