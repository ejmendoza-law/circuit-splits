"""Call the AI model. Uses the Anthropic API if ANTHROPIC_API_KEY is set,
otherwise the `claude` command-line tool. Returns (parsed JSON, usage)."""
import json, os, re, subprocess, time, urllib.error, urllib.request

CHEAP = "claude-haiku-5-5"


def _parse(text):
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0))


def ask(system, prompt, model=CHEAP, max_tokens=8000):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps({"model": model, "max_tokens": max_tokens, "system": system,
                             "messages": [{"role": "user", "content": prompt}]}).encode(),
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    d = json.load(r)
                break
            except urllib.error.HTTPError as e:   # rate limit or server trouble: wait and retry
                if e.code not in (429, 500, 502, 503, 529) or attempt == 4:
                    raise
                time.sleep(10 * (attempt + 1))
        u = d["usage"]
        text = "".join(b.get("text", "") for b in d["content"] if b.get("type") == "text")
        return _parse(text), {"in": u["input_tokens"], "out": u["output_tokens"]}
    r = subprocess.run(
        ["claude", "-p", "--model", model, "--system-prompt", system, "--tools", "",
         "--strict-mcp-config", "--no-session-persistence", "--output-format", "json"],
        input=prompt, capture_output=True, text=True, timeout=600, cwd="/tmp")
    d = json.loads(r.stdout[r.stdout.index("{"):])
    return _parse(d["result"]), {"in": len(system + prompt) // 4, "out": d["usage"]["output_tokens"]}
