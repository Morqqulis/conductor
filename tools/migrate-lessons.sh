#!/usr/bin/env bash
# Migrates the flat lessons ledger into the curated store: one file per lesson plus an index.
#
# Why the split. The ledger was a single append-only file and the session hook could only
# afford to inject its top ~10 lines. Past that line the lessons were still on disk and
# still growing, but no session ever saw them again - memory that silently stops being
# memory. The store keeps them reachable: the index is small enough to read in full, and
# each lesson's own file holds the detail.
#
#   lessons.md          INBOX - agents append one line, "date | trigger | rule". Cheap to
#                       write, which is why it stays: a capture step that costs effort is
#                       a capture step that gets skipped.
#   lessons/INDEX.md    CURATED - one line per lesson, newest first.
#   lessons/<file>.md   the lesson itself.
#
# Distillation moves inbox lines into the store and generalizes them. This script performs
# the mechanical half: nothing is summarized, nothing is dropped.
#
#   tools/migrate-lessons.sh --dry-run
#   tools/migrate-lessons.sh [--ledger PATH] [--store PATH]
set -euo pipefail

LEDGER="${CONDUCTOR_LESSONS:-$HOME/.claude/conductor/lessons.md}"
STORE=''
DRY_RUN=0

while [ $# -gt 0 ]; do
    case "$1" in
        -n|--dry-run) DRY_RUN=1; shift ;;
        --ledger)     LEDGER="$2"; shift 2 ;;
        --store)      STORE="$2"; shift 2 ;;
        -h|--help)    sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done
[ -n "$STORE" ] || STORE="$(dirname "$LEDGER")/lessons"

[ -f "$LEDGER" ] || { echo "migrate-lessons: no ledger at $LEDGER" >&2; exit 1; }

slugify() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]' \
        | sed -e 's/[^a-z0-9]\+/-/g' -e 's/^-//' -e 's/-$//' \
        | cut -c1-52
}

count=0
skipped=0
tmp_index="$(mktemp)"

while IFS= read -r line; do
    case "$line" in ''|'#'*) continue ;; esac

    date_part="$(printf '%s' "$line" | cut -d'|' -f1 | sed 's/[[:space:]]*$//')"
    trigger="$(printf '%s' "$line" | cut -d'|' -f2 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    rule="$(printf '%s' "$line" | cut -d'|' -f3- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

    # A line without all three fields is data we do not understand well enough to file.
    # Losing it silently would be worse than leaving it in the inbox for a human to look at.
    if [ -z "$trigger" ] || [ -z "$rule" ]; then
        skipped=$((skipped + 1))
        echo "  SKIP (not date|trigger|rule): $line" >&2
        continue
    fi

    slug="$(slugify "$trigger")"
    [ -n "$slug" ] || slug="lesson"
    file="$date_part-$slug.md"
    # Two lessons can share a date and a trigger phrasing; never let one overwrite the other.
    n=2
    while [ -e "$STORE/$file" ] || grep -qF "($file)" "$tmp_index" 2>/dev/null; do
        file="$date_part-$slug-$n.md"
        n=$((n + 1))
    done

    if [ "$DRY_RUN" -eq 0 ]; then
        mkdir -p "$STORE"
        {
            printf '# %s\n\n' "$rule"
            printf -- '- date: %s\n' "$date_part"
            printf -- '- trigger: %s\n' "$trigger"
        } > "$STORE/$file"
    fi
    printf -- '- %s [%s](%s) — %s\n' "$date_part" "$slug" "$file" "$rule" >> "$tmp_index"
    count=$((count + 1))
done < "$LEDGER"

if [ "$DRY_RUN" -eq 1 ]; then
    echo "dry run: $count lessons would be filed into $STORE ($skipped unparseable, left in the inbox)"
    rm -f "$tmp_index"
    exit 0
fi

mkdir -p "$STORE"
{
    printf '# Lessons index\n\n'
    printf 'One line per lesson, newest first. Read this file whenever the task touches an area a\n'
    printf 'lesson might cover; open the lesson file for the full entry. New lessons arrive in\n'
    printf '../lessons.md (the inbox) and are filed here during distillation.\n\n'
    sort -r "$tmp_index"
} > "$STORE/INDEX.md"
rm -f "$tmp_index"

# The inbox keeps its header comments and loses the filed lines - that is what "filed" means.
header="$(grep -E '^[[:space:]]*#' "$LEDGER" || true)"
printf '%s\n' "$header" > "$LEDGER"

printf 'filed %s lessons -> %s\n' "$count" "$STORE"
printf 'index: %s (%s bytes)\n' "$STORE/INDEX.md" "$(wc -c < "$STORE/INDEX.md" | tr -d '[:space:]')"
[ "$skipped" -gt 0 ] && printf 'left in the inbox for review: %s line(s)\n' "$skipped"
exit 0
