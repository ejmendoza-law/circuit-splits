"""Shared helpers: load opinions, pull out the passages that talk about splits."""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data"

# Language that signals a court is talking about disagreement among circuits.
TRIGGER = re.compile(
    r"circuit[- ]split|inter-?circuit|circuit conflict"
    r"|split (?:among|between|in|of|with|on)\b[^.]{0,40}(?:circuits?|courts of appeals|authority)"
    r"|circuits (?:are|have|remain|were|is|has)[^.]{0,30}(?:split|divided|disagree|at odds|conflict)"
    r"|(?:courts of appeals|sister circuits|our sister courts)[^.]{0,40}(?:split|divided|disagree|at odds|conflict)"
    r"|circuits disagree|divided on (?:this|the|whether)"
    r"|(?:disagree|part(?:s|ed)? ways|decline[sd]? to follow)[^.]{0,60}(?:Circuit|sister)"
    r"|(?:create|creating|deepen|widen|acknowledg)\w*[^.]{0,40}split",
    re.I)

CIRCUITS = ["1st", "2d", "3d", "4th", "5th", "6th", "7th", "8th", "9th", "10th", "11th", "D.C."]
_WORDS = {"first": "1st", "second": "2d", "third": "3d", "fourth": "4th", "fifth": "5th",
          "sixth": "6th", "seventh": "7th", "eighth": "8th", "ninth": "9th",
          "tenth": "10th", "eleventh": "11th", "d.c.": "D.C.", "district of columbia": "D.C."}
_ABBR = {"1st": "1st", "2d": "2d", "2nd": "2d", "3d": "3d", "3rd": "3d", "4th": "4th",
         "5th": "5th", "6th": "6th", "7th": "7th", "8th": "8th", "9th": "9th",
         "10th": "10th", "11th": "11th", "d.c.": "D.C."}
COURT_ID = {"ca1": "1st", "ca2": "2d", "ca3": "3d", "ca4": "4th", "ca5": "5th", "ca6": "6th",
            "ca7": "7th", "ca8": "8th", "ca9": "9th", "ca10": "10th", "ca11": "11th", "cadc": "D.C."}
_CIRC_RE = re.compile(
    r"\b(First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|Eleventh|D\.C\.|District of Columbia)\s+Circuit"
    r"|\((1st|2d|2nd|3d|3rd|4th|5th|6th|7th|8th|9th|10th|11th|D\.C\.)\s+Cir\.", re.I)

STATUTE = re.compile(
    r"\b\d+\s+U\.\s?S\.\s?C\.\s+§+\s*\d+[a-zA-Z]?(?:\([a-zA-Z0-9]+\))*"
    r"|U\.\s?S\.\s?S\.\s?G\.\s+§+\s*\d[A-Z]\d+\.\d+(?:\([a-zA-Z0-9]+\))*"
    r"|§\s*\d[A-Z]\d+\.\d+(?:\([a-zA-Z0-9]+\))*"
    r"|Fed(?:eral|\.)\s+R(?:ule|\.)s?\s+(?:of\s+)?(?:Crim(?:inal|\.)\s+P(?:rocedure|\.)|Evid(?:ence|\.))\s+\d+(?:\([a-z0-9]+\))*"
    r"|(?:First|Fourth|Fifth|Sixth|Eighth|Second|Fourteenth) Amendment"
    r"|First Step Act|Armed Career Criminal Act|ACCA\b|AEDPA\b")


def circuits_in(text):
    found = []
    for m in _CIRC_RE.finditer(text):
        c = _WORDS.get((m.group(1) or "").lower()) or _ABBR.get((m.group(2) or "").lower())
        if c and c not in found:
            found.append(c)
    return found


def clean(text):
    text = re.sub(r"-\n(?=[a-z])", "", text)          # re-join hyphenated line breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", " ", text)          # keep paragraph breaks
    text = re.sub(r"\s*\n\s*", " ", text)
    return text.replace(" ", "\n\n")


def passages(text, window=1100, cap=14000):
    """Return the stretches of text around each trigger phrase, merged."""
    text = clean(text)
    spans = []
    for m in TRIGGER.finditer(text):
        a, b = max(0, m.start() - window), min(len(text), m.end() + window)
        if spans and a <= spans[-1][1]:
            spans[-1][1] = b
        else:
            spans.append([a, b])
    out, total = [], 0
    for a, b in spans:
        chunk = text[a:b].strip()
        if total + len(chunk) > cap:
            chunk = chunk[: max(0, cap - total)]
        if chunk:
            out.append(chunk)
            total += len(chunk)
        if total >= cap:
            break
    return out


def load_all():
    """Yield each downloaded case with its combined text."""
    for f in sorted(RAW.glob("*.json")):
        d = json.loads(f.read_text())
        d["text"] = "\n\n".join(o["text"] for o in d["opinions"])
        yield d


def cite(d):
    """Short citation, e.g. 'United States v. Smith, 12 F.4th 345 (5th Cir. 2022)'."""
    c = next((x for x in d.get("citation", []) if "F." in x), None)
    mid = c if c else f"No. {d['docket_number']}"
    return f"{d['case_name']}, {mid} ({d['court']} {d['date_filed'][:4]})"
