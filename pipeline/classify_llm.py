#!/usr/bin/env python3
"""Step 2b (AI option): have a low-cost AI model read each opinion's
split passages and report whether the court acknowledges a live split.

Only the passages around split language are sent, not the whole opinion,
which keeps the cost to a fraction of a cent per opinion. Results are
cached in data/llm/, so re-runs only pay for new opinions.
"""
import json, sys
from concurrent.futures import ThreadPoolExecutor
from common import OUT, COURT_ID, cite, load_all, passages
from llm import ask

CACHE = OUT / "llm"

SYSTEM = """You are a federal criminal appellate lawyer. You will read excerpts from a federal court of appeals opinion. Decide whether the opinion acknowledges a LIVE circuit split on a question of federal criminal law.

"Criminal law" means: federal criminal offenses, criminal procedure, constitutional rights of the accused, sentencing and the Guidelines, supervised release, habeas corpus (28 U.S.C. 2254 / 2255 / 2241 challenges to a conviction or sentence), and compassionate release / sentence reduction. It does NOT include immigration cases (even ones turning on a criminal conviction), section 1983 or Bivens civil suits, or other civil matters.

A LIVE split means the opinion says that two or more federal courts of appeals have reached conflicting holdings on the same legal question, and the opinion does not say the Supreme Court, an en banc court, a statute, or a Guidelines amendment has since resolved it. Count it if this opinion itself creates the conflict by expressly rejecting another circuit's holding. Count a split a concurrence or dissent identifies, but say so.

Do NOT count: statements that there is no split; a split the opinion says has been resolved; disagreement only among district courts or state courts; a court merely joining unanimous sister circuits; tension within a single circuit; a split on a non-criminal question.

Reply with ONLY a JSON object:
{
 "criminal": true/false,
 "status": "live" | "resolved" | "none",
 "resolved_by": "how it was resolved, if status is resolved, else empty",
 "issue": "the legal question, as one plain-English question a practitioner would recognize. Empty if status is none.",
 "provision": "main statute, guideline, rule, or constitutional provision, e.g. '18 U.S.C. § 3582(c)(1)(A)'. Empty if none.",
 "topic": one of "Sentencing & Guidelines" | "Compassionate release & sentence reduction" | "Supervised release & probation" | "Habeas & post-conviction" | "Firearms" | "Drug offenses" | "Fraud & white-collar" | "Search & seizure" | "Trial rights & procedure" | "Pleas & appeal waivers" | "Evidence" | "Other offenses" | "Other",
 "sides": [ {"position": "short statement of this side's rule", "circuits": ["1st","2d","3d","4th","5th","6th","7th","8th","9th","10th","11th","D.C."], "cases": ["Name v. Name, 1 F.4th 1 (5th Cir. 2021)"]} ],
 "this_court": "which position this court takes, or 'does not decide'",
 "source": "majority" | "concurrence" | "dissent",
 "confidence": 0.0-1.0,
 "quote": "the one sentence from the opinion that best shows the split, verbatim"
}
Use only circuits and cases the excerpts actually name. Every side must list at least one circuit; if the excerpts do not say which circuits hold a position, the split is not adequately shown, so lower your confidence. Include the deciding court in the side it takes, and cite this case in that side's cases. If the opinion discusses more than one split, report the one most central to the holding."""


def run(d):
    out = CACHE / f"{d['cluster_id']}.json"
    if out.exists():
        return json.loads(out.read_text())
    ps = passages(d["text"])
    if not ps:
        res = {"criminal": None, "status": "none", "confidence": 1.0, "no_passage": True}
        usage = {"in": 0, "out": 0}
    else:
        prompt = (f"Case: {cite(d)}\nDeciding court: {COURT_ID[d['court_id']]} Circuit\n\n"
                  "EXCERPTS:\n\n" + "\n\n[...]\n\n".join(ps))
        try:
            res, usage = ask(SYSTEM, prompt)
        except Exception as e:
            print("  failed:", d["cluster_id"], str(e)[:100], file=sys.stderr)
            return None
    res.update(cluster_id=d["cluster_id"], cite=cite(d), court=COURT_ID[d["court_id"]],
               date=d["date_filed"], url=d["url"], usage=usage)
    out.write_text(json.dumps(res, indent=1))
    return res


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    cases = list(load_all())[:limit]
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(run, cases))
    rows = [json.loads(f.read_text()) for f in sorted(CACHE.glob("*.json"))]
    (OUT / "llm.json").write_text(json.dumps(rows, indent=1))
    live = [r for r in rows if r.get("status") == "live" and r.get("criminal")]
    tin = sum(r["usage"]["in"] for r in rows); tout = sum(r["usage"]["out"] for r in rows)
    print(f"{len(rows)} opinions; {len(live)} live criminal splits; "
          f"~{tin:,} input tokens, {tout:,} output tokens")


if __name__ == "__main__":
    main()
