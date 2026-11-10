#!/usr/bin/env python3
"""Step 3: group opinions that discuss the same split and merge each group
into one entry. Writes data/splits_machine.json, then publishes.

Split IDs are permanent. data/groups.json records which split each opinion
belongs to, so a new opinion is either added to an existing split or starts
a new one. Existing splits never change ID, which keeps reviewer decisions
attached to the right entry.
"""
import json, sys
from concurrent.futures import ThreadPoolExecutor
from common import OUT, CIRCUITS
from llm import ask
import publish

SMART = "claude-sonnet-5-5"
AUTO_PUBLISH = 0.8   # entries at or above this confidence go live as "unreviewed"

MATCH_SYS = """You are a federal criminal appellate lawyer maintaining a list of circuit splits.

EXISTING SPLITS lists splits already on the list, as: split_id | provision | question.
NEW OPINIONS lists opinions that each acknowledge a circuit split, as: opinion_id | provision | question.

For each new opinion, decide whether it describes the SAME circuit split as an existing split, meaning the same legal question even if worded differently. Related but distinct questions are different splits. If it matches, assign that split_id. If it matches nothing existing, assign a label of the form "new-1", "new-2", and so on, giving the same label to new opinions that describe the same split as each other. Most new opinions will not match anything.

Reply with ONLY JSON: {"assign": {"<opinion_id>": "<split_id or new-N>", ...}} covering every new opinion."""

MERGE_SYS = """You are a federal criminal appellate lawyer. Below are records from several court of appeals opinions that each describe the same circuit split. Merge them into one accurate entry. Where records conflict about which side a circuit is on, prefer the more recent opinion and the circuit's own opinion. A circuit may appear on only one side. Write in plain English.

Reply with ONLY JSON:
{"issue": "the question, one sentence", "provision": "...", "topic": "<keep one of the topics used in the records>",
 "sides": [{"position": "...", "circuits": ["5th", ...], "cases": ["..."]}],
 "note": "one sentence on anything a practitioner should know, e.g. a pending en banc or cert petition mentioned in the records; else empty"}"""


STALE_SYS = """You are a federal criminal appellate lawyer. Below is a circuit split that court of appeals opinions acknowledged, with the date of the most recent such opinion. From your own knowledge, say whether the split has since been resolved: by a Supreme Court decision, an act of Congress, or an amendment to the Sentencing Guidelines or federal rules that took effect after that date or that the opinions did not account for. Answer "yes" only if you can name the specific decision or amendment and it squarely settles this question. If you are not sure, answer "unsure". Otherwise answer "no".

Reply with ONLY JSON: {"resolved": "yes" | "no" | "unsure", "by": "the decision or amendment, with year; empty unless yes"}"""


TITLE_SYS = """Write a headline for this circuit split, for a list that criminal defense lawyers scan. At most 9 words. Name the statute, guideline, or doctrine and the point in dispute. No question mark, no "Circuit split on", no ending period. Reply with ONLY JSON: {"title": "..."}"""


def title_for(e):
    try:
        t, _ = ask(TITLE_SYS, json.dumps({"question": e["issue"], "provision": e.get("provision", "")}))
        return t["title"].strip().rstrip(".")
    except Exception:
        return ""


def load(name, default):
    f = OUT / name
    return json.loads(f.read_text()) if f.exists() else default


def slim(r):
    return {k: r.get(k) for k in ("cite", "date", "issue", "provision", "topic", "sides",
                                  "this_court", "source", "quote")}


def norm_sides(sides):
    out, used = [], set()
    for s in sides or []:
        cs = [c for c in s.get("circuits", []) if c in CIRCUITS and c not in used]
        used.update(cs)
        cs.sort(key=CIRCUITS.index)
        out.append({"position": s.get("position", ""), "circuits": cs, "cases": s.get("cases", [])})
    return out


def assign_new(live, groups):
    """Give every not-yet-grouped opinion a split ID."""
    new = [r for r in live if str(r["cluster_id"]) not in groups]
    if not new:
        return
    rep = {}  # split id -> a representative record, for the existing list
    for r in live:
        sid = groups.get(str(r["cluster_id"]))
        if sid and sid not in rep:
            rep[sid] = r
    line = lambda k, r: f"{k} | {r.get('provision', '')} | {r['issue']}"
    new.sort(key=lambda r: (r.get("provision") or "", r["issue"]))
    prompt = ("EXISTING SPLITS:\n" + ("\n".join(line(s, r) for s, r in sorted(rep.items())) or "(none yet)")
              + "\n\nNEW OPINIONS:\n" + "\n".join(line(r["cluster_id"], r) for r in new))
    res, _ = ask(MATCH_SYS, prompt, model=SMART, max_tokens=16000)
    labels = {}
    for r in sorted(new, key=lambda r: r["cluster_id"]):
        cid = str(r["cluster_id"])
        a = str(res.get("assign", {}).get(cid, ""))
        if a in rep:
            groups[cid] = a
        elif a.startswith("new-") and a in labels:
            groups[cid] = labels[a]
        else:                                   # new split: its ID is its first opinion's number
            groups[cid] = f"s{cid}"
            if a.startswith("new-"):
                labels[a] = groups[cid]


def make(sid, recs, cache):
    recs = sorted(recs, key=lambda r: r["date"], reverse=True)
    members = sorted(r["cluster_id"] for r in recs)
    if cache.get(sid, {}).get("members") == members:
        e = cache[sid]["entry"]
        if not e.get("title"):
            e["title"] = title_for(e)
        return e
    r = recs[0]
    e = {"issue": r["issue"], "provision": r.get("provision", ""), "topic": r.get("topic", "Other"),
         "sides": r.get("sides", []), "note": ""}
    if len(recs) > 1:
        try:
            e, _ = ask(MERGE_SYS, json.dumps([slim(x) for x in recs], indent=1), max_tokens=6000)
        except Exception as ex:
            print("merge failed", sid, str(ex)[:80], file=sys.stderr)
    e["sides"] = norm_sides(e.get("sides"))
    conf = max(x.get("confidence", 0) for x in recs)
    if len(recs) > 1:
        conf = min(1.0, conf + 0.05)      # more than one court noticed it
    if sum(1 for s in e["sides"] if s["circuits"]) < 2:
        conf = min(conf, 0.6)             # can't show both sides: send to review
    try:   # has the split been resolved since these opinions were written?
        st, _ = ask(STALE_SYS, json.dumps({"question": e["issue"], "provision": e.get("provision", ""),
                    "sides": e["sides"], "most_recent_opinion": recs[0]["date"]}, indent=1), model=SMART)
    except Exception:
        st = {"resolved": "unsure"}
    if st.get("resolved") == "yes" and st.get("by"):
        conf = min(conf, 0.5)             # a lawyer should confirm before it is published or dropped
        e["note"] = ("Possibly resolved by " + st["by"].rstrip(".") + ". Confirm before relying on this split. "
                     + (e.get("note") or "")).strip()
        e["possibly_resolved"] = True
    e.update(
        id=sid, confidence=round(conf, 2),
        status="unreviewed" if conf >= AUTO_PUBLISH else "needs_review",
        latest=recs[0]["date"], first=recs[-1]["date"],
        opinions=[{"cite": x["cite"], "url": x["url"], "date": x["date"], "court": x["court"],
                   "takes": x.get("this_court", ""), "source": x.get("source", "majority"),
                   "quote": x.get("quote", "")} for x in recs])
    e["title"] = title_for(e)
    cache[sid] = {"members": members, "entry": e}
    return e


def main():
    rows = load("llm.json", [])
    live = [r for r in rows if r.get("status") == "live" and r.get("criminal") and r.get("issue")]
    groups = load("groups.json", {})
    cache = load("entries.json", {})
    assign_new(live, groups)
    (OUT / "groups.json").write_text(json.dumps(groups, indent=0, sort_keys=True))

    by_split = {}
    for r in live:
        by_split.setdefault(groups[str(r["cluster_id"])], []).append(r)
    with ThreadPoolExecutor(8) as ex:
        entries = list(ex.map(lambda kv: make(kv[0], kv[1], cache), by_split.items()))
    entries.sort(key=lambda e: e["latest"], reverse=True)
    (OUT / "entries.json").write_text(json.dumps({k: cache[k] for k in sorted(by_split)}, indent=0))
    (OUT / "splits_machine.json").write_text(json.dumps(entries, indent=1))
    print(f"{len(live)} opinions -> {len(entries)} splits")
    publish.main()


if __name__ == "__main__":
    main()
