# Circuit Split Tracker

Finds acknowledged circuit splits in federal criminal law from CourtListener and publishes them as a website.

## How it works

1. `pipeline/collect.py` searches CourtListener for published opinions from the 12 regional circuits (2020 on) that use split language and look criminal. It saves each opinion's text in `data/raw/`.
2. Two classifiers read each opinion. Both are kept so they can be compared.
   - `pipeline/classify_keyword.py` is free. It scores sentences with keyword rules.
   - `pipeline/classify_llm.py` sends only the split passages to a low-cost AI model, which reports the question, the sides, and its confidence.
3. `pipeline/build.py` groups opinions that discuss the same split, merges them, applies reviewer decisions, and writes `site/data/splits.json`.
4. `site/index.html` is the website. It needs no server.

`./run_weekly.sh` runs all four steps. Each step skips work it has already done.

## Review

Entries with confidence of 0.8 or more publish as "Unreviewed". The rest wait in the review queue. A reviewer can approve, reject, or edit any entry. Reviewer decisions override the software and survive later updates.

## Secrets

Set `COURTLISTENER_TOKEN` and (for the AI option) `ANTHROPIC_API_KEY` as environment variables. Do not put them in the code.
