"""Blinded plain-language scoring of bench replies.

usage: judge.py OUT.json label=path/to/run.json [label=...]
Each reply is scored twice: an LLM judge (fixed rubric, labels hidden behind shuffled ids)
and a mechanical proxy (Latin-script words outside code, glossed status token).
"""
import hashlib
import json
import re
import subprocess
import sys
import tempfile

RUBRIC = """You grade how understandable a reply is for a person with NO technical background
who reads Russian. List every word or phrase in the reply that such a person may not know
(technical terms, English words, abbreviations, tool, command or file names, status labels).
For each, decide whether the reply explains it in plain words in the same sentence or right
next to it where it first appears. A name inside backticks counts as a term too unless its
purpose is stated in plain words nearby. Output ONLY JSON:
{"terms": [{"term": "...", "explained": true|false}]}
Reply to grade:
---
"""


def mechanical(text):
    prose = re.sub(r"```.*?```", " ", text, flags=re.S)
    prose = re.sub(r"`[^`]*`", " ", prose)
    latin = re.findall(r"\b[A-Za-z][A-Za-z_-]{2,}\b", prose)
    status = re.search(r"(Статус|Status):\s*(DONE_WITH_CONCERNS|DONE|BLOCKED|NEEDS_CONTEXT)(.*)", text)
    glossed = bool(status and re.match(r"\s*[(—-]", status.group(3)))
    return {"latin_words_outside_code": len(latin), "status_glossed": glossed if status else None}


def judge(text):
    with tempfile.TemporaryDirectory() as cwd:
        out = subprocess.run(["claude", "-p", RUBRIC + text, "--output-format", "json",
                              "--setting-sources", "local"], cwd=cwd, capture_output=True,
                             text=True, encoding="utf-8", timeout=300)
    data = json.loads(out.stdout)
    raw = data.get("result", "")
    match = re.search(r"\{.*\}", raw, re.S)
    terms = json.loads(match.group(0))["terms"] if match else []
    return {"terms": terms, "unexplained": sum(1 for t in terms if not t.get("explained")),
            "total": len(terms), "judge_cost_usd": data.get("total_cost_usd")}


def main():
    out_path, pairs = sys.argv[1], [a.split("=", 1) for a in sys.argv[2:]]
    order = sorted(pairs, key=lambda p: hashlib.sha256(p[1].encode()).hexdigest())
    results = []
    for blind, (label, path) in enumerate(order):
        run = json.load(open(path, encoding="utf-8"))
        text = run.get("result", "")
        score = judge(text)
        results.append({"blind_id": blind, "label": label, "run_cost_usd": run.get("total_cost_usd"),
                        "turns": run.get("num_turns"), **mechanical(text), **score})
        print(f"scored blind #{blind}", file=sys.stderr)
    json.dump(results, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
