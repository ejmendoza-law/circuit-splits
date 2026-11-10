#!/usr/bin/env python3
"""Step 2a (free option): flag circuit splits with keyword rules only.

For each downloaded opinion, score the sentences that mention a split.
Sentences that affirm a live split add points; sentences that deny one,
or say the Supreme Court resolved it, subtract. Writes data/keyword.json.
"""
import json, re
from common import OUT, STATUTE, COURT_ID, circuits_in, cite, load_all, passages, TRIGGER

POS = [(re.compile(p, re.I), w) for p, w in [
    (r"circuits (?:are|remain|have been|is|were)[^.]{0,25}(?:split|divided|at odds|in conflict)", 3),
    (r"circuits (?:have|has) (?:split|divided|disagreed|reached (?:different|conflicting))", 3),
    (r"(?:sister circuits|courts of appeals|our sister courts)[^.]{0,40}(?:are|have|remain)[^.]{0,20}(?:split|divided|disagree)", 3),
    (r"(?:deepen|widen|exacerbat|add to|enter|join|take sides? in|weigh in on|acknowledg|recogniz|note|aware of|existing|entrenched|mature)\w*[^.]{0,40}(?:circuit[- ])?split", 3),
    (r"(?:is|there is|there exists|has (?:developed|emerged))[^.]{0,15}(?:a|an)[^.]{0,25}(?:circuit[- ]split|split (?:among|between|in|of) (?:the )?(?:circuits|authority))", 3),
    (r"(?:we|court)[^.]{0,30}(?:respectfully )?(?:disagree|part ways|decline to follow)[^.]{0,60}(?:Circuit|sister)", 2),
    (r"(?:majority|minority) (?:of (?:the |our sister )?circuits|view|approach|position|rule)", 2),
    (r"we (?:join|agree with|side with|adopt the (?:view|approach|reasoning) of)[^.]{0,80}Circuit", 1),
    (r"circuit[- ]split|split (?:among|between|in|of) (?:the |our sister )?(?:circuits|courts of appeals|authority)|circuits disagree|circuit conflict", 1),
]]
NEG = [(re.compile(p, re.I), w) for p, w in [
    (r"\b(?:no|not a|without (?:a|any)|absence of (?:a|any)|isn't a|is not a|nor is there a)\s+(?:true |real |genuine |actual )?(?:circuit[- ])?(?:split|conflict)", 4),
    (r"(?:avoid|declin\w+ to creat|not creat|without creat|reluctan\w+ to creat|loath to creat|hesita\w+ to creat|wary of creat)\w*[^.]{0,30}split", 3),
    (r"(?:would|could|might) create[^.]{0,20}split", 2),
    (r"(?:resolv|settl|end|abrogat|put to rest)\w*[^.]{0,40}(?:circuit[- ])?(?:split|conflict|disagreement)", 3),
    (r"(?:granted|grant) cert\w*[^.]{0,60}(?:split|conflict|divi)", 2),
    (r"every (?:other )?circuit|all (?:of )?(?:our|the other) sister circuits|unanimous|uniformly|each of our sister circuits", 2),
    (r"(?:illusory|overstated|not implicated|does not exist|more apparent than real)", 3),
]]
# Rough test for "is this a criminal case", from the caption and the text.
CIVIL_CAPTION = re.compile(r" v\. .*(Garland|Bondi|Noem|Mayorkas|Barr|Trump|Biden|Attorney General|Whitmer|Commissioner|Inc\.|LLC|Corp|Board|Department|County|City of)", re.I)
CRIM_TEXT = re.compile(r"§\s*225[45]|habeas|compassionate release|3582\(c\)|Sentencing Guidelines|U\.S\.S\.G\.|indictment|convicted", re.I)


def criminal(d):
    name = d["case_name"]
    if re.match(r"(United States|USA) v\.", name) or re.match(r"In re", name):
        return not re.search(r"(Inc\.|LLC|Corp)", name)
    if CIVIL_CAPTION.search(name) and not re.search(r"§\s*225[45]", d["text"]):
        return False
    return len(CRIM_TEXT.findall(d["text"])) >= 8


SENT = re.compile(r"(?<=[.?!])\s+(?=[A-Z\"“(])")


def classify(d):
    ps = passages(d["text"])
    best, score, hits = "", 0, 0
    for p in ps:
        for s in SENT.split(p):
            if not TRIGGER.search(s):
                continue
            pos = sum(w for r, w in POS if r.search(s))
            neg = sum(w for r, w in NEG if r.search(s))
            sc = pos - neg
            hits += 1
            score += max(-4, min(4, sc))
            if sc > 0 and (not best or sc > best[0]):
                best = (sc, s.strip())
    joined = "\n".join(ps)
    stat = {}
    for m in STATUTE.finditer(joined):
        k = re.sub(r"\s+", " ", m.group(0))
        stat[k] = stat.get(k, 0) + 1
    statutes = sorted(stat, key=lambda k: -stat[k])[:3]
    circs = [c for c in circuits_in(joined) if c != COURT_ID[d["court_id"]]]
    is_split = score >= 3 and bool(best) and len(circs) >= 1 and criminal(d)
    return {
        "cluster_id": d["cluster_id"], "cite": cite(d), "court": COURT_ID[d["court_id"]],
        "date": d["date_filed"], "url": d["url"],
        "is_split": is_split, "score": score,
        "key_sentence": best[1][:600] if best else "",
        "statutes": statutes, "circuits_mentioned": circs,
    }


def main():
    out = OUT / "keyword.json"
    old = {r["cluster_id"]: r for r in json.loads(out.read_text())} if out.exists() else {}
    old.update({d["cluster_id"]: classify(d) for d in load_all()})
    rows = list(old.values())
    (OUT / "keyword.json").write_text(json.dumps(rows, indent=1))
    print(f"{len(rows)} opinions; {sum(r['is_split'] for r in rows)} flagged as live splits")


if __name__ == "__main__":
    main()
