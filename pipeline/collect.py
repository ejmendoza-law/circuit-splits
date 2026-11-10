#!/usr/bin/env python3
"""Step 1: find candidate opinions on CourtListener and save their text.

Finds published federal appellate opinions that (a) use circuit-split
language and (b) look like criminal cases. Saves one JSON file per
opinion cluster in data/raw/. Safe to re-run: skips what it already has.

Usage:  COURTLISTENER_TOKEN=... python3 pipeline/collect.py [--after 2020-01-01]
"""
import argparse, html, json, os, re, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
API = "https://www.courtlistener.com/api/rest/v4"
COURTS = "ca1 ca2 ca3 ca4 ca5 ca6 ca7 ca8 ca9 ca10 ca11 cadc"

# Phrases courts use when they acknowledge a split. Cast wide here;
# the classifiers downstream decide what is real.
SPLIT_TERMS = [
    "circuit split", "split among the circuits", "split of authority",
    "circuits are split", "circuits are divided", "circuits have split",
    "circuits have divided", "split in the circuits",
    "conflict among the circuits", "circuit conflict", "intercircuit",
    "inter-circuit", "disagree with our sister", "decline to follow",
    "sister circuits have", "circuits disagree", "divided on",
    "create a split",
]
# Rough criminal-law filter (direct appeals, sentencing, supervised
# release, habeas / 2255, compassionate release).
CRIM = ('(caseName:"United States v." OR "habeas" OR "2255" OR '
        '"compassionate release" OR "sentencing guidelines")')
QUERY = "(" + " OR ".join(f'"{t}"' for t in SPLIT_TERMS) + ") AND " + CRIM


STORAGE = "https://storage.courtlistener.com/"
_last = [0.0]


def get(url, token, tries=8):
    """API call. CourtListener allows 5 requests a minute, so pace to that."""
    for i in range(tries):
        wait = 12.5 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"Authorization": f"Token {token}"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limit (5 a minute, 50 an hour): wait as told
                wait = int(e.headers.get("Retry-After") or 60) + 5
                print(f"  rate limited; waiting {wait // 60} min", flush=True)
                time.sleep(wait)
            elif i == tries - 1:
                raise
            else:
                time.sleep(15)
        except Exception:  # network hiccup
            if i == tries - 1:
                raise
            time.sleep(15)


def pdf_text(local_path):
    """Get opinion text from CourtListener's file server (no rate limit)."""
    if not local_path or not local_path.endswith(".pdf"):
        return ""
    try:
        with urllib.request.urlopen(STORAGE + urllib.parse.quote(local_path), timeout=90) as r:
            data = r.read()
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(data); f.flush()
            return subprocess.run(["pdftotext", f.name, "-"], capture_output=True,
                                  text=True, timeout=120).stdout
    except Exception:
        return ""


def to_text(op):
    if op.get("plain_text"):
        return op["plain_text"]
    for k in ("html_with_citations", "html", "html_lawbox", "html_columbia", "xml_harvard"):
        if op.get(k):
            t = re.sub(r"<(br|/p|/div|/h\d)[^>]*>", "\n", op[k], flags=re.I)
            return html.unescape(re.sub(r"<[^>]+>", "", t))
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--after", default="2020-01-01")
    ap.add_argument("--before", default="", help="only opinions filed on or before this date")
    args = ap.parse_args()
    token = os.environ.get("COURTLISTENER_TOKEN")
    if not token:
        sys.exit("Set COURTLISTENER_TOKEN")
    RAW.mkdir(parents=True, exist_ok=True)

    params = {"q": QUERY, "type": "o", "court": COURTS, "filed_after": args.after,
              "stat_Published": "on", "order_by": "dateFiled desc"}
    if args.before:
        params["filed_before"] = args.before
    url = f"{API}/search/?" + urllib.parse.urlencode(params)
    new = seen = 0
    while url:
        page = get(url, token)
        for r in page["results"]:
            seen += 1
            out = RAW / f"{r['cluster_id']}.json"
            done = ROOT / "data" / "llm" / f"{r['cluster_id']}.json"
            if out.exists() or done.exists():
                continue
            ops = []
            for o in r.get("opinions", []):
                text = pdf_text(o.get("local_path"))
                if len(text) < 2000:  # no usable PDF: fall back to the API
                    text = to_text(get(f"{API}/opinions/{o['id']}/", token))
                ops.append({"id": o["id"], "type": o.get("type"), "text": text})
            out.write_text(json.dumps({
                "cluster_id": r["cluster_id"],
                "case_name": r["caseName"],
                "court_id": r["court_id"],
                "court": r["court_citation_string"],
                "date_filed": r["dateFiled"],
                "docket_number": r["docketNumber"],
                "citation": r.get("citation") or [],
                "url": "https://www.courtlistener.com" + r["absolute_url"],
                "opinions": ops,
            }))
            new += 1
            if new % 50 == 0:
                print(f"  saved {new} new ({seen} seen)", flush=True)
        url = page.get("next")
    print(f"Done. {seen} candidates found, {new} newly saved.")


if __name__ == "__main__":
    main()
