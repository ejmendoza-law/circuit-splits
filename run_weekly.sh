#!/bin/sh
# Weekly update. Needs COURTLISTENER_TOKEN. For the AI option, also ANTHROPIC_API_KEY.
set -e
cd "$(dirname "$0")"
python3 pipeline/collect.py --after "${AFTER:-2020-01-01}"   # skips opinions already classified
cd pipeline
python3 classify_keyword.py     # free option, kept for comparison
python3 classify_llm.py         # AI option: only pays for new opinions
python3 build.py                # add new opinions to splits, apply reviews, write site/data/splits.json
