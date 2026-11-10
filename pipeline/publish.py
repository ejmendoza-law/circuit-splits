#!/usr/bin/env python3
"""Step 4: apply the reviewer's decisions and write the file the website reads.

Uses no AI and no network, so it is safe to run any time.
"""
import json
from common import OUT, ROOT


def main():
    entries = json.loads((OUT / "splits_machine.json").read_text())
    rv = OUT / "review.json"
    reviews = json.loads(rv.read_text()) if rv.exists() else {}
    for e in entries:
        d = reviews.get(e["id"])
        if d:
            e.update(d.get("edits") or {})
            e["status"] = d["status"]
    site = ROOT / "site" / "data"
    site.mkdir(parents=True, exist_ok=True)
    (site / "splits.json").write_text(json.dumps(entries, indent=1))
    n = lambda s: sum(e["status"] == s for e in entries)
    print(f"{len(entries)} splits: {n('approved')} reviewed, {n('unreviewed')} unreviewed, "
          f"{n('needs_review')} in the review queue, {n('rejected')} rejected")


if __name__ == "__main__":
    main()
