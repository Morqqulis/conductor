# Owner decisions for this project: one line each, "YYYY-MM-DD | instruction | revisit when".
# Each line is a precise instruction for an AI agent, not the owner's words. Read at the
# start of every session (lessons-inject.sh). A later line on a topic overrides an earlier one.
2026-07-28 | Do not propose a weekly or scheduled Conductor self-test (declined twice) | the owner asks for one
2026-08-15 | Write visible reasoning in the chosen reply language; never default it to English | the owner changes it
2026-09-27 | Keep RTK and Graphify updating automatically to their latest stable versions; do not propose pinning their versions | an automatic update breaks an installation
2026-11-04 | Push proven work directly to main; do not create other long-lived branches or pull requests unless the owner asks | the owner changes the workflow
2026-11-04 | In every reply, explain in plain words, where it first appears, each term a non-programmer may not know | never
2026-11-04 | Do not propose distributing Conductor as a Claude Code plugin; if it is ever built, it is for the owner and hand-picked people only, through a private repository | several people need access, settings.json breakage recurs, or Claude Code changes how hooks are wired
2026-11-04 | Do not trim Conductor's rules or build new bench trap tasks; results would vary with the session's effort level | the owner asks to revisit
2026-11-04 | Keep the pre-edit file snapshots, the fix-falsification check (break the fix, the test must fail) and the essence->method line; in the owner's experience they prevented serious mistakes. Any speed-up of Conductor must not lower code quality | the owner asks to revisit
