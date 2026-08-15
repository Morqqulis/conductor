#!/usr/bin/env bash
# Shared reply-language helpers for the installers (install.sh, install-global.sh,
# install-project.sh). Sourced, never executed.
#
# One rule, one token: every rule file this repo ships is written in English and carries the
# literal phrase "Answer in Russian". Switching the reply language is a single substitution of
# that token - the rest of the corpus STAYS English on purpose. A model tends to reason in the
# language its instruction corpus is written in, so the old mostly-Russian global CLAUDE.md
# kept pulling the visible reasoning into Russian no matter what the reply line said.
#
# The chosen name is persisted at $CLAUDE_HOME/conductor/reply-language so a later re-run of
# either installer reuses it instead of silently reverting to the default.

# reply_language_file <claude_home> -> path of the persisted choice
reply_language_file() { printf '%s/conductor/reply-language' "$1"; }

# saved_reply_language <claude_home> -> the saved name on stdout, or nothing.
# A locked or unreadable file degrades to "no saved choice" instead of killing the caller
# through set -e/pipefail: the caller then falls back to its prompt or default.
saved_reply_language() {
    local f line=''
    f="$(reply_language_file "$1")"
    if [ -f "$f" ]; then
        line="$(head -n1 "$f" 2>/dev/null | tr -d '\r')" || line=''
    fi
    printf '%s' "$line"
}

# normalize_reply_language <name> -> the name with surrounding whitespace trimmed
normalize_reply_language() { printf '%s' "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'; }

# validate_reply_language <name> -> 0 if usable; else reason on stderr, return 1.
# The name is substituted into rule files, so it is validated as a name, not trusted as input.
validate_reply_language() {
    local name="$1"
    case "$name" in
        '') echo "empty language name" >&2; return 1 ;;
        [A-Za-z]*) : ;;
        *) echo "invalid language name: '$name' (use an English language name, e.g. 'Russian')" >&2; return 1 ;;
    esac
    if [ "${#name}" -gt 30 ]; then
        echo "language name too long: '$name' (30 characters max)" >&2; return 1
    fi
    case "$name" in
        *[!A-Za-z\ -]*) echo "invalid language name: '$name' (letters, spaces and hyphens only)" >&2; return 1 ;;
    esac
    case "$name" in
        *[!A-Za-z]) echo "invalid language name: '$name' (must end with a letter)" >&2; return 1 ;;
    esac
    return 0
}

# prompt_reply_language <default> -> chosen name on stdout (menu goes to stderr).
# A piped or otherwise non-interactive run gets the default rather than an error.
prompt_reply_language() {
    local default="$1" answer=''
    {
        echo 'Reply language / Язык ответов / Cavab dili:'
        echo '  1 - Русский'
        echo '  2 - Azərbaycanca'
        echo '  3 - English'
        echo '  or type a language name in English (e.g. Azerbaijani)'
    } >&2
    read -r -p "Choice [$default]: " answer || answer=''
    case "$(printf '%s' "$answer" | tr -d '[:space:]')" in
        '') printf '%s' "$default" ;;
        1)  printf 'Russian' ;;
        2)  printf 'Azerbaijani' ;;
        3)  printf 'English' ;;
        *)  printf '%s' "$answer" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' ;;
    esac
}

# apply_reply_language <language> <file> -> file text on stdout with the token substituted.
# "Answer in Russian" is the ONLY localized phrase; everything else is English by design.
apply_reply_language() { sed "s/Answer in Russian/Answer in $1/g" "$2"; }

# save_reply_language <claude_home> <language>
save_reply_language() {
    local f
    f="$(reply_language_file "$1")"
    mkdir -p "$(dirname "$f")"
    printf '%s\n' "$2" > "$f"
}
