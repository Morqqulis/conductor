#!/usr/bin/env python3
"""Find lesson candidates locally; relevance must still be judged in context."""
import sys

# Also stay read-only when callers omit -B; set before importing local modules.
sys.dont_write_bytecode = True

import argparse
from collections import Counter
from datetime import date
import json
import os
from pathlib import Path
import re
import unicodedata

from corpus import Corpus


def tokens(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return {word for word in re.findall(r"[^\W_]+", normalized) if len(word) >= 2}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({"component": "lesson-recall", "error": message}, ensure_ascii=False),
              file=sys.stderr)
        self.exit(2)


def lesson_date(text):
    # A date is metadata, never a substitute for relevance. Ignore malformed dates.
    match = re.search(r"^(?:-\s*date:\s*)?(\d{4}-\d{2}-\d{2})(?:\s*\||\s*$)", text, re.M)
    if match:
        try:
            return date.fromisoformat(match[1]).isoformat()
        except ValueError:
            pass
    return ""


def excerpt(entry, query):
    lines = entry.text.splitlines()
    # Show a matching body line rather than only a title when both match.
    index = max(range(len(lines)), key=lambda i: (
        len(tokens(lines[i]) & query), not lines[i].startswith("#"), -i))
    line = lines[index]
    words = list(re.finditer(r"[^\W_]+", line))
    match = next((m for m in words if tokens(m[0]) & query), None)
    start = max(0, (match.start() if match else 0) - 100)
    sample = line[start:start + 600]
    if start:
        sample = "…" + sample
    if start + 600 < len(line):
        sample += "…"
    return entry.line + index, sample


def rank(entries, query, limit):
    sets = [tokens(entry.text) for entry in entries]
    counts = Counter(term for terms in sets for term in terms & query)
    ranked = []
    for entry, terms in zip(entries, sets):
        matched = query & terms
        if not matched:
            continue
        line, sample = excerpt(entry, query)
        item = {"source": entry.source, "line": line, "title": entry.title[:200],
                "excerpt": sample, "date": lesson_date(entry.text), "matched_terms": sorted(matched)}
        # Distinct concepts dominate; repeated words cannot inflate the rank.
        key = (len(matched), sum(1 / counts[term] for term in sorted(matched)),
               len(tokens(entry.title) & query), item["date"])
        ranked.append((key, item))
    # Stable tie order, independent of filesystem directory iteration order.
    ranked.sort(key=lambda pair: (pair[1]["source"], pair[1]["line"]))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in ranked[:limit]]


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = Parser(description=__doc__)
    parser.add_argument("--query", action="append", required=True, help="Task terms; repeat for synonyms/languages")
    parser.add_argument("--limit", type=int, default=5, help="Maximum candidates (1 to 10)")
    parser.add_argument("--ledger", help="Inbox path; default from Conductor environment")
    parser.add_argument("--store", help="Curated directory; default lessons/ beside inbox")
    args = parser.parse_args(argv)
    query_text = " ".join(args.query)
    query = tokens(query_text)
    if not query or len(query_text) > 4096 or len(query) > 100:
        parser.error("use 1 to 100 task terms of at least two characters, within 4096 characters")
    if not 1 <= args.limit <= 10:
        parser.error("limit must be between 1 and 10")
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
    home = Path(os.environ.get("CONDUCTOR_HOME", str(config / "conductor")))
    # abspath normalizes without resolving a link before the reader can reject it.
    ledger = Path(os.path.abspath(os.path.expanduser(
        args.ledger or os.environ.get("CONDUCTOR_LESSONS", str(home / "lessons.md")))))
    store = Path(os.path.abspath(os.path.expanduser(args.store or str(ledger.parent / "lessons"))))
    corpus = Corpus().load(ledger, store)
    candidates = rank(corpus.entries, query, args.limit)
    result = {"status": "PARTIAL" if corpus.issues else "CANDIDATES" if candidates else "NO_MATCH",
              "scan_complete": not corpus.issues, "candidates": candidates, "issues": corpus.issues}
    print(json.dumps(result, ensure_ascii=False))
    return 1 if corpus.issues else 0


if __name__ == "__main__":
    sys.exit(main())
