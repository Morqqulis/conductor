#!/usr/bin/env python3
"""Lessons for the user's message, found automatically (UserPromptSubmit helper).

The session-start block only tells the agent where memory is; the agent then had to
remember to search, and often did not, so recorded lessons repeated as mistakes. This
reads the hook payload on stdin, and for a task-like message (enough content words) prints
up to three lesson candidates that share at least two distinct words with it. Short replies
("continue", "yes") and weak matches print nothing. Lexical matches are candidates, never
instructions: the agent opens the source and judges whether the lesson applies.

Fails quiet by design: any problem prints nothing and exits 0, so a reminder is never
blocked by memory.
"""
import sys

sys.dont_write_bytecode = True

import json
import os
from pathlib import Path

from corpus import Corpus
from recall import rank, tokens
from wordforms import fold

MIN_CONTENT_KEYS = 4
MAX_QUERY_WORDS = 30
MAX_CANDIDATES = 3
MIN_SHARED_KEYS = 2
MAX_CHARS = 900

# Function words and generic request words in the three supported languages: they appear
# in almost every message and every lesson, so they would only add noise.
STOPWORDS = {fold(w) for w in """
это этот эта эти тот как что чтобы если когда где почему зачем или также тоже уже ещё
еще очень просто можно нужно надо есть был была были будет быть который которая которые
сделай сделать сделали давай пожалуйста посмотри проверь исправь почини хочу хотел
продолжай продолжить спасибо хорошо ладно сейчас потом теперь здесь там тогда всё все
this that these those what when where which with from have will would should could please
make made just also into about then than there their them they your yours some more most
continue thanks okay fine check look need want here
bu şu nə necə niyə harada həm də ilə üçün amma çünki indi sonra artıq zəhmət olmasa
""".split()}


# Messages the harness writes, not the owner: background-task notifications, agent
# hand-backs, webhook payloads. Their fixed vocabulary ("code, command, exit, failed, file")
# matched lessons on every notification and buried the useful suggestions.
AUTOMATIC_MARKERS = ("<task-notification>", "[SYSTEM NOTIFICATION", "<agent-message",
                     "<webhook-payload>", "<wake reason=", "<system-reminder>")


def automatic(prompt):
    return any(marker in prompt[:2000] for marker in AUTOMATIC_MARKERS)


def query_words(prompt):
    seen, words = set(), []
    for word in tokens(prompt[:4000]):
        key = fold(word)
        if len(word) < 4 or key in STOPWORDS or key in seen:
            continue
        seen.add(key)
        words.append(word)
    return sorted(words)[:MAX_QUERY_WORDS]


def lesson_paths():
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
    home = Path(os.environ.get("CONDUCTOR_HOME", str(config / "conductor")))
    ledger = Path(os.path.abspath(os.path.expanduser(
        os.environ.get("CONDUCTOR_LESSONS", str(home / "lessons.md")))))
    return ledger, ledger.parent / "lessons"


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        prompt = payload.get("prompt") if isinstance(payload, dict) else None
        if not isinstance(prompt, str) or automatic(prompt):
            return 0
        words = query_words(prompt)
        if len(words) < MIN_CONTENT_KEYS:
            return 0
        ledger, store = lesson_paths()
        corpus = Corpus().load(ledger, store)
        lines, best = [], 0
        for item in rank(corpus.entries, set(words), MAX_CANDIDATES * 3):
            shared = len({fold(term) for term in item["matched_terms"]})
            best = max(best, shared)
            # Weak matches are noise: keep only lessons nearly as close as the best one.
            if shared < MIN_SHARED_KEYS or shared < best - 1:
                continue
            title = " ".join(item["title"].split())[:120]
            lines.append(f"- {title} ({item['source']}:{item['line']}; shared: "
                         f"{', '.join(item['matched_terms'][:5])})")
            if len(lines) == MAX_CANDIDATES:
                break
        if not lines:
            return 0
        block = ("Lessons that may apply to this message (word match only: open the source "
                 "and judge before applying):\n" + "\n".join(lines))
        print(block[:MAX_CHARS])
    except Exception:  # noqa: BLE001 - memory must never block the reminder
        return 0
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout,):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
