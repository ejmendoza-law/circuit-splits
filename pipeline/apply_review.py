#!/usr/bin/env python3
"""Record one review decision. The website's review buttons open a GitHub
issue titled "[review] approve s123" (or reject / undo). A GitHub Action
passes that issue here. Edits, if any, are JSON in the issue body.

Usage: apply_review.py "<issue title>" <file with issue body> <reviewer> <date>
"""
import json, re, sys
from common import OUT

CIRCUITS = ["1st", "2d", "3d", "4th", "5th", "6th", "7th", "8th", "9th", "10th", "11th", "D.C."]
ALLOWED = {"issue", "provision", "note", "topic", "title", "sides", "added_opinions"}


def main():
    title, body_file, who, when = sys.argv[1:5]
    m = re.match(r"\s*\[review\]\s+(approve|reject|undo)\s+(s\d+)\s*$", title)
    if not m:
        sys.exit("Not a review request: title must be '[review] approve|reject|undo s<number>'")
    action, sid = m.groups()
    machine = {e["id"]: e for e in json.loads((OUT / "splits_machine.json").read_text())}
    if sid not in machine:
        sys.exit(f"No split with id {sid}")
    rv = OUT / "review.json"
    reviews = json.loads(rv.read_text()) if rv.exists() else {}
    if action == "undo":
        reviews.pop(sid, None)
    else:
        edits = (reviews.get(sid) or {}).get("edits") or {}
        j = re.search(r"```json\s*(\{.*?\})\s*```", open(body_file).read(), re.S)
        if j:
            new = {k: v for k, v in json.loads(j.group(1)).items() if k in ALLOWED}
            shown = edits.get("sides") or machine[sid].get("sides", [])   # the sides the reviewer was looking at
            sides = []
            for s in new.get("sides", []):
                bad = [c for c in s.get("circuits", []) if c not in CIRCUITS]
                if bad:
                    sys.exit(f"Unknown circuit: {bad[0]}")
                k = s.get("keep")
                cases = s["cases"] if "cases" in s else (shown[k].get("cases", []) if isinstance(k, int) and 0 <= k < len(shown) else [])
                sides.append({"position": str(s.get("position", "")), "circuits": s.get("circuits", []),
                              "cases": [str(c) for c in cases]})
            if "sides" in new:
                new["sides"] = sides[:4]
            ops = []
            for o in new.get("added_opinions", []):
                url = str(o.get("url", "")).strip()
                if url and not re.match(r"https://\S+$", url):
                    sys.exit("An opinion link must start with https://")
                if str(o.get("cite", "")).strip():
                    ops.append({"cite": str(o["cite"]).strip(), "url": url, "quote": str(o.get("quote", "")).strip()})
            if "added_opinions" in new:
                new["added_opinions"] = ops
            edits.update(new)
        reviews[sid] = {"status": "approved" if action == "approve" else "rejected",
                        "edits": edits, "by": who, "at": when}
    rv.write_text(json.dumps(reviews, indent=1, sort_keys=True))
    print(f"{action} {sid} recorded")


if __name__ == "__main__":
    main()
