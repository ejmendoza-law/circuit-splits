#!/usr/bin/env python3
"""Record one review decision. The website's review buttons open a GitHub
issue titled "[review] approve s123" (or reject / undo). A GitHub Action
passes that issue here. Edits, if any, are JSON in the issue body.

Usage: apply_review.py "<issue title>" <file with issue body> <reviewer> <date>
"""
import json, re, sys
from common import OUT

CIRCUITS = ["1st", "2d", "3d", "4th", "5th", "6th", "7th", "8th", "9th", "10th", "11th", "D.C."]
ALLOWED = {"issue", "provision", "note", "topic", "title", "sides"}


def main():
    title, body_file, who, when = sys.argv[1:5]
    m = re.match(r"\s*\[review\]\s+(approve|reject|undo)\s+(s\d+)\s*$", title)
    if not m:
        sys.exit("Not a review request: title must be '[review] approve|reject|undo s<number>'")
    action, sid = m.groups()
    known = {e["id"] for e in json.loads((OUT / "splits_machine.json").read_text())}
    if sid not in known:
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
            for s in new.get("sides", []):
                bad = [c for c in s.get("circuits", []) if c not in CIRCUITS]
                if bad:
                    sys.exit(f"Unknown circuit: {bad[0]}")
            edits.update(new)
        reviews[sid] = {"status": "approved" if action == "approve" else "rejected",
                        "edits": edits, "by": who, "at": when}
    rv.write_text(json.dumps(reviews, indent=1, sort_keys=True))
    print(f"{action} {sid} recorded")


if __name__ == "__main__":
    main()
