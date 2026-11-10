#!/usr/bin/env python3
"""Compare the free keyword option against the AI option on the same opinions."""
import json, random
from common import OUT
kw = {r["cluster_id"]: r for r in json.loads((OUT / "keyword.json").read_text())}
ai = {r["cluster_id"]: r for r in json.loads((OUT / "llm.json").read_text())}
ids = sorted(set(kw) & set(ai))
live = lambda r: r.get("status") == "live" and bool(r.get("criminal"))
both = [i for i in ids if kw[i]["is_split"] and live(ai[i])]
kw_only = [i for i in ids if kw[i]["is_split"] and not live(ai[i])]
ai_only = [i for i in ids if not kw[i]["is_split"] and live(ai[i])]
neither = [i for i in ids if not kw[i]["is_split"] and not live(ai[i])]
print(f"opinions compared: {len(ids)}")
print(f"both flag a live criminal split: {len(both)}")
print(f"keyword only: {len(kw_only)}   AI only: {len(ai_only)}   neither: {len(neither)}")
why = {}
for i in kw_only:
    r = ai[i]; k = "not criminal" if r.get("criminal") is False else r.get("status")
    why[k] = why.get(k, 0) + 1
print("AI's reason for rejecting keyword-only flags:", why)
random.seed(7)
sample = {"kw_only": random.sample(kw_only, min(15, len(kw_only))),
          "ai_only": random.sample(ai_only, min(15, len(ai_only))),
          "both": random.sample(both, min(10, len(both)))}
out = {k: [{"id": i, "cite": kw[i]["cite"], "kw_sentence": kw[i]["key_sentence"], "kw_score": kw[i]["score"],
            "ai_status": ai[i].get("status"), "ai_criminal": ai[i].get("criminal"), "ai_issue": ai[i].get("issue"),
            "ai_resolved_by": ai[i].get("resolved_by"), "ai_quote": ai[i].get("quote"),
            "ai_sides": [(s.get("position"), s.get("circuits")) for s in ai[i].get("sides", [])]} for i in v]
       for k, v in sample.items()}
(OUT / "compare_sample.json").write_text(json.dumps(out, indent=1))
