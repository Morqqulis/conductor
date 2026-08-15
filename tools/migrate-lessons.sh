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
#   lessons/INDEX.md    CURATED - one line per lesson, newest first. Rebuilt from the store
#                       on every run, so a re-run or a hand-added lesson file never makes
#                       an older entry vanish from the index.
#   lessons/<file>.md   the lesson itself.
#
# Distillation moves inbox lines into the store and generalizes them. This script performs
# the mechanical half: nothing is summarized, nothing is dropped. The inbox is ROTATED
# before reading (mv, then a fresh inbox is recreated), so a lesson appended by a parallel
# session lands in the fresh inbox instead of being read-then-truncated away. Unparseable
# lines go back into the fresh inbox for a human; the processed batch is kept as a
# timestamped backup under the store.
#
#   tools/migrate-lessons.sh --dry-run
#   tools/migrate-lessons.sh [--ledger PATH] [--store PATH]
set -euo pipefail

LEDGER="${CONDUCTOR_LESSONS:-$HOME/.claude/conductor/lessons.md}"
STORE=''
DRY_RUN=0
STAMP="$(date +%Y%m%d-%H%M%S)"

while [ $# -gt 0 ]; do
    case "$1" in
        -n|--dry-run) DRY_RUN=1; shift ;;
        --ledger)     LEDGER="$2"; shift 2 ;;
        --store)      STORE="$2"; shift 2 ;;
        -h|--help)    sed -n '2,/^set /p' "$0" | sed '$d'; exit 0 ;;
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

# Rebuild INDEX.md from what is actually IN the store. The previous design wrote the index
# from the current batch only, so every run erased the entries of every earlier run - the
# lesson file survived on disk, but the only entry point (the index) forgot it: exactly the
# "memory that silently stops being memory" failure this tool exists to prevent.
rebuild_index() {
    local tmp f base rule date_part slug
    tmp="$(mktemp)"
    for f in "$STORE"/*.md; do
        [ -e "$f" ] || continue
        case "$f" in */INDEX.md) continue ;; esac
        base="$(basename "$f")"
        rule="$(sed -n '1{s/^# //p;q}' "$f")"
        date_part="$(sed -n 's/^- date: //p' "$f" | head -n1)"
        [ -n "$date_part" ] || date_part='undated'
        slug="${base%.md}"
        case "$slug" in "$date_part"-*) slug="${slug#"$date_part"-}" ;; esac
        printf -- '- %s [%s](%s) — %s\n' "$date_part" "$slug" "$base" "$rule" >> "$tmp"
    done
    {
        printf '# Lessons index\n\n'
        printf 'One line per lesson, newest first. Read this file whenever the task touches an area a\n'
        printf 'lesson might cover; open the lesson file for the full entry. New lessons arrive in\n'
        printf '../lessons.md (the inbox) and are filed here during distillation.\n\n'
        sort -r "$tmp"
    } > "$STORE/INDEX.md"
    rm -f "$tmp"
}

# --- pick the batch to process --------------------------------------------------------
# Dry run reads the live ledger in place. A real run rotates it first: after the mv, a
# parallel append recreates a fresh (headerless) inbox instead of writing into the file
# being consumed. The header is put back preserving anything that arrived in between.
BATCH="$LEDGER"
if [ "$DRY_RUN" -eq 0 ]; then
    BATCH="$LEDGER.processing-$$"
    mv "$LEDGER" "$BATCH"
    header="$(grep -E '^[[:space:]]*#' "$BATCH" || true)"
    # Append-only on purpose: >> creates the file when absent and never truncates, so a
    # lesson appended by a parallel session in this exact window is preserved whichever
    # side wins. Worst case the header lands below that lesson - cosmetic, every reader
    # filters header lines by pattern, not position.
    if [ -n "$header" ]; then
        printf '%s\n' "$header" >> "$LEDGER"
    fi
fi

count=0
skipped=0
tmp_index="$(mktemp)"
skipped_lines="$(mktemp)"

# `|| [ -n "$line" ]`: a final line with no trailing newline still gets processed -
# read returns non-zero at EOF but has filled $line; without the guard that lesson would
# vanish into the batch backup with no SKIP, no count, no trace.
while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac

    # cut -s on the field reads: a line with NO '|' at all would otherwise come back whole
    # for every field, sail past the emptiness check below, and get filed as garbage.
    date_part="$(printf '%s' "$line" | cut -d'|' -s -f1 | sed 's/[[:space:]]*$//')"
    trigger="$(printf '%s' "$line" | cut -d'|' -s -f2 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    rule="$(printf '%s' "$line" | cut -d'|' -s -f3- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

    # A line without all three fields is data we do not understand well enough to file.
    # Losing it silently would be worse than leaving it in the inbox for a human to look at.
    # The date is validated STRICTLY because it becomes part of a file path: anything but
    # a plain ISO date (a slash, a '..') would send the redirect outside the store or into
    # a directory that does not exist - and under set -e that kills the run mid-batch.
    case "$date_part" in
        [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;;
        *) trigger='' ;;
    esac
    if [ -z "$trigger" ] || [ -z "$rule" ]; then
        skipped=$((skipped + 1))
        echo "  SKIP (not date|trigger|rule): $line" >&2
        printf '%s\n' "$line" >> "$skipped_lines"
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
    printf -- '- %s [%s](%s)\n' "$date_part" "$slug" "$file" >> "$tmp_index"
    count=$((count + 1))
done < "$BATCH"

if [ "$DRY_RUN" -eq 1 ]; then
    echo "dry run: $count lessons would be filed into $STORE ($skipped unparseable, left in the inbox)"
    rm -f "$tmp_index" "$skipped_lines"
    exit 0
fi

# Unparseable lines really do go back into the inbox - "left for review" must be literal.
if [ "$skipped" -gt 0 ]; then
    cat "$skipped_lines" >> "$LEDGER"
fi
rm -f "$tmp_index" "$skipped_lines"

mkdir -p "$STORE"
rebuild_index

# The processed batch is cheap insurance: the ledger itself is not versioned anywhere.
mv "$BATCH" "$STORE/.filed-$STAMP.inbox"

printf 'filed %s lessons -> %s (batch kept: lessons/.filed-%s.inbox)\n' "$count" "$STORE" "$STAMP"
printf 'index: %s (%s bytes, %s entries)\n' "$STORE/INDEX.md" \
    "$(wc -c < "$STORE/INDEX.md" | tr -d '[:space:]')" \
    "$(grep -c '^- ' "$STORE/INDEX.md" || true)"
[ "$skipped" -gt 0 ] && printf 'left in the inbox for review: %s line(s)\n' "$skipped"
exit 0
