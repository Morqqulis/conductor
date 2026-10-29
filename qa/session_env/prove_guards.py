"""Prove that every guard of the session-env cleanup is load-bearing (remove-only proof).

Not a test module (unittest discovery skips it); run it on purpose, it takes minutes:
  python -B qa/session_env/prove_guards.py [SOURCE_ROOT] [CASE_LABEL ...]
SOURCE_ROOT defaults to this repository. Each case copies CURRENT runtime/ and qa/ into a fresh
temporary directory, then:
  run the named tests            -> must pass
  apply ONE guarded hunk         (the original text must occur exactly once)
  run them again                 -> must FAIL on an assertion (an error is not a valid failure)
  reverse that hunk              (bytes must equal the pre-hunk bytes exactly)
  run them a third time          -> must pass
Nothing is written outside the temporary directories. A case whose test is skipped on this
platform (POSIX-only fixtures on Windows) is reported as SKIPPED-HERE, never as proven.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ARGS = sys.argv[1:]
SOURCE = Path(ARGS.pop(0)) if ARGS and Path(ARGS[0]).is_dir() else Path(__file__).resolve().parents[2]
ONLY = set(ARGS)
GUARD, HOST = "runtime/hooks/session-env.sh", "runtime/hooks/lessons-inject.sh"
D, G, I = "test_dedupe.DedupeTest.", "test_guards.GuardTest.", "test_integration.IntegrationTest."
M, R = "test_meaning.MeaningTest.", "test_robustness.RobustnessTest."

CASES = [
    ("ritual: guard call disarmed", HOST, 'if [ -f "$guard" ]; then', 'if false; then',
     [I + "test_original_symptom_bash_c_truncation_is_gone_after_cleanup",
      I + "test_registered_lessons_hook_hands_its_input_to_the_cleanup"]),
    # The hook consumes its stdin for the owner decisions; without the hand-over the guard reads nothing.
    ("hook input handed to the guard", HOST, '"$timeout_cmd" 5 "${BASH:-bash}" "$guard" 2>/dev/null <<< "$payload")"',
     '"$timeout_cmd" 5 "${BASH:-bash}" "$guard" 2>/dev/null)"',
     [I + "test_registered_lessons_hook_hands_its_input_to_the_cleanup"]),
    ("dedupe rewrite disarmed", GUARD, '        rewrite "${files[$i]}" "$name"', "        true",
     [D + "test_thirty_five_copies_collapse_to_one_per_file"]),
    ("plain-text eligibility", GUARD, "        bad = n\n        next", "        bad = 0\n        next",
     [G + "test_shell_code_is_never_line_deduplicated"]),
    ("special bash names", GUARD, '    if (name ~ ENVIRON["CONDUCTOR_ENV_SPECIAL"])', "    if (0)",
     [M + "test_special_bash_variables_are_never_collapsed"]),
    ("session-wide plainness", GUARD, '        5) block "$name" shell_text "${line//[!0-9]/}" ;;', "        5) ;;",
     [M + "test_integer_declared_in_a_neighbouring_file_blocks_the_whole_session"]),
    ("failed check forbids rewrites", GUARD,
     '        *) log error awk_failed "file=$name" "status=$status"\n           block "$name" unexamined ;;',
     '        *) log error awk_failed "file=$name" "status=$status" ;;', [M + "test_entry_whose_check_failed_forbids_rewrites"]),
    ("non-regular entry forbids rewrites", GUARD, '        log warn not_regular "file=$name"\n        block "$name" unexamined',
     '        log warn not_regular "file=$name"', [R + "test_non_regular_entries_are_never_read_and_forbid_rewrites"]),
    ("linked file forbids rewrites", GUARD, '        log warn linked_file "file=$name"\n        block "$name" unexamined',
     '        log warn linked_file "file=$name"', [G + "test_linked_file_is_not_followed_and_forbids_rewrites"]),
    ("oversized file forbids rewrites", GUARD, '        log warn too_large "file=$name" "bytes=$size"\n        block "$name" unexamined',
     '        log warn too_large "file=$name" "bytes=$size"', [G + "test_oversized_file_is_skipped_and_forbids_rewrites"]),
    ("entries past the limit forbid rewrites", GUARD,
     '[ "${#files[@]}" -le "$MAX_FILES" ] || block "${files[$MAX_FILES]##*/}" unexamined', "true",
     [G + "test_entries_past_the_limit_are_not_examined_and_forbid_rewrites"]),
    ("byte-sum / final newline", GUARD, 'if (bad || (mode == "write" && bytes != size)) {', "if (bad) {",
     [D + "test_missing_final_newline_leaves_the_file_alone"]),
    ("session id grammar", GUARD, '=~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$ ]]', "=~ ^.*$ ]]",
     [G + "test_unsafe_session_id_is_refused"]),
    ("env file cross-check", GUARD,
     'if [ "${env_dir##*/}" != "$SESSION" ] || [ "${env_base##*/}" != "session-env" ]; then', "if false; then",
     [G + "test_env_file_of_another_session_refuses_the_cleanup"]),
    ("compare before rename", GUARD, 'if cmp -s -- "$snap" "$file" 2>/dev/null; then', "if true; then",
     [G + "test_append_inside_the_check_window_is_not_lost"]),
    ("linked directory refusal", GUARD, 'if [ -L "$BASE" ] || [ -L "$DIR" ]; then', "if false; then",
     [G + "test_linked_session_directory_is_refused"]),
    ("linked file refusal", GUARD, 'if [ -L "$file" ]; then', "if false; then",
     [G + "test_linked_file_is_not_followed_and_forbids_rewrites"]),
    ("activation gate", GUARD, '[ -n "${CLAUDE_ENV_FILE:-}" ] || exit 0', "true || exit 0",
     [G + "test_without_claude_env_file_nothing_is_read_or_changed"]),
    ("untouched without repeats", GUARD, "        exit 4\n", "        repeats = 0\n",
     [D + "test_file_without_repeats_keeps_bytes_and_mtime"]),
    ("stdin read timeout", GUARD, "read -r -d '' -t 2 -n", "read -r -d '' -n",
     [G + "test_stdin_that_never_closes_cannot_hold_the_start"]),
    ("guard run timeout", HOST, 'if [ -n "$timeout_cmd" ]; then', "if false; then",
     [I + "test_hanging_guard_cannot_hold_the_lessons_or_the_start"]),
    ("per-file size limit", GUARD, 'if [ "$size" -gt "$MAX_FILE_BYTES" ]; then', "if false; then",
     [G + "test_oversized_file_is_skipped_and_forbids_rewrites"]),
    ("entry count limit", GUARD, '    [ "$i" -lt "$MAX_FILES" ] || break', "    true || break",
     [G + "test_entries_past_the_limit_are_not_examined_and_forbid_rewrites"]),
    ("log rotation", GUARD, '            mv -f -- "$LOG" "$LOG.1" 2>/dev/null', "            :",
     [G + "test_log_is_rotated_past_its_cap_and_holds_no_contents"]),
    ("late append carried over", GUARD, "ln -- \"$file\" \"$held\" 2>/dev/null || held=''", "held=''",
     [R + "test_append_between_check_and_rename_is_carried_over"]),
    ("classify before reading", GUARD, '    if [ ! -f "$file" ]; then', "    if false; then",
     [R + "test_non_regular_entries_are_never_read_and_forbid_rewrites"]),
    ("time budget", GUARD, '        over_budget "$name" && continue', "        false && continue",
     [R + "test_time_budget_stops_new_rewrites_and_still_reports"]),
    ("time budget while examining", GUARD, '    if over_budget "$name"; then', "    if false; then",
     [R + "test_time_budget_also_bounds_the_examination"]),
    ("interruption is logged", GUARD, "trap 'log warn interrupted; cleanup; exit 0' HUP INT TERM",
     "trap 'cleanup; exit 0' HUP INT TERM", [R + "test_guard_killed_by_the_callers_timeout_leaves_a_log_entry"]),
    ("only setup/sessionstart rewritten", GUARD, "REWRITE_RE='^(setup|sessionstart)-hook-[0-9]+\\.sh$'",
     'REWRITE_RE="$NAME_RE"', [D + "test_only_setup_and_sessionstart_files_are_rewritten"]),
    ("snapshot written past noclobber", GUARD, 'cat -- "$file" 2>/dev/null >| "$snap"', 'cat -- "$file" 2>/dev/null > "$snap"',
     [R + "test_inherited_noclobber_does_not_disable_the_cleanup"]),
    ("stale temporaries swept", GUARD,
     "find \"$DIR\" -maxdepth 1 -type f -name '.conductor-env.*' -mmin +10 -exec rm -f -- {} + 2>/dev/null \\\n"
     "            || log warn stale_sweep_failed", ":", [R + "test_stale_temporaries_are_swept_and_fresh_ones_kept"]),
    ("config folder mismatch reported", GUARD, "        log warn config_dir_mismatch\n", "        :\n",
     [R + "test_configured_folder_differing_from_claude_codes_is_reported"]),
    ("mismatch logged beside Claude Code's folder", GUARD,
     'if [ -z "$HOME_GIVEN" ] && [ ! -d "$CONDUCTOR_HOME" ] && [ -d "${env_base%/*}/conductor" ]; then', "if false; then",
     [R + "test_mismatch_is_logged_beside_claude_codes_folder_when_ours_is_absent"]),
    ("log only into a regular file", GUARD, '        [ -f "$LOG" ] && [ ! -L "$LOG" ] || return 0', "        true",
     [R + "test_log_that_is_not_a_regular_file_is_never_written"]),
    ("awk reads bytes, not text", GUARD, '    awk -v BINMODE=3 "$@" "$DEDUPE_AWK" "$file"',
     '    awk "$@" "$DEDUPE_AWK" "$file"', [G + "test_shell_code_is_never_line_deduplicated"]),
    ("missing tools reported", GUARD, '    command -v "$tool" >/dev/null 2>&1 || { log error missing_tool "tool=$tool"; exit 0; }',
     "    true", [R + "test_missing_tool_is_reported_not_retried"]),
    ("mode kept on rewrite", GUARD, 'chmod --reference="$file" -- "$out" 2>/dev/null || log warn mode_not_copied "file=$name"',
     ":", [R + "test_rewritten_file_keeps_its_mode"]),
    ("failed mode copy logged", GUARD, '|| log warn mode_not_copied "file=$name"', "|| :",
     [G + "test_failed_mode_copy_and_failed_sweep_are_logged_and_the_cleanup_goes_on"]),
    ("failed sweep logged", GUARD, "            || log warn stale_sweep_failed", "            || :",
     [G + "test_failed_mode_copy_and_failed_sweep_are_logged_and_the_cleanup_goes_on"]),
    ("failed rotation logged", GUARD, r'|| entry="$entry,\"log_rotation\":\"failed\""', "|| :",
     [G + "test_failures_inside_logging_cleanup_and_carry_over_are_logged"]),
    ("failed cleanup logged", GUARD, "|| log warn temp_cleanup_failed", "|| :",
     [G + "test_failures_inside_logging_cleanup_and_carry_over_are_logged"]),
    ("unknown carry-over logged", GUARD, 'log error late_append_unknown "file=$name"', ":",
     [G + "test_failures_inside_logging_cleanup_and_carry_over_are_logged"]),
    ("history expansion excluded", GUARD, r'"([^"\\$`![:cntrl:]]', r'"([^"\\$`[:cntrl:]]',
     [G + "test_shell_code_is_never_line_deduplicated"]),
]

RUNNER = (
    "import json, os, sys, unittest\n"
    "suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])\n"
    "with open(os.devnull, 'w') as sink:\n"
    "    r = unittest.TextTestRunner(stream=sink, verbosity=0).run(suite)\n"
    "print(json.dumps({'run': r.testsRun, 'failures': len(r.failures), 'errors': len(r.errors),"
    " 'skipped': len(r.skipped)}))\n"
)


def run(copy, ids):
    started = time.monotonic()
    out = subprocess.run([sys.executable, "-B", "-c", RUNNER, *ids], cwd=copy / "qa/session_env",
                         capture_output=True, text=True, timeout=600)
    lines = out.stdout.strip().splitlines()
    if not lines:
        return {"error": out.stderr[-400:]}
    result = json.loads(lines[-1])
    result["seconds"] = round(time.monotonic() - started, 1)
    return result


def passed(r):
    return r.get("run", 0) > 0 and r.get("failures") == 0 and r.get("errors") == 0 and r.get("skipped") == 0


# Guards that only have work to do on one platform: elsewhere their test passes either way.
PLATFORM_ONLY = {"awk reads bytes, not text": "nt"}

verdicts = []
for label, relative, original, disarmed, ids in CASES:
    if ONLY and label not in ONLY:
        continue
    if PLATFORM_ONLY.get(label, os.name) != os.name:
        print(f"SKIPPED-HERE {label}: guards a {PLATFORM_ONLY[label]}-only behavior")
        continue
    with tempfile.TemporaryDirectory(prefix="conductor-falsify-") as tmp:
        copy = Path(tmp)
        for part in ("runtime", "qa"):
            shutil.copytree(SOURCE / part, copy / part, ignore=shutil.ignore_patterns("__pycache__"))
        target = copy / relative
        before = target.read_bytes()
        text = before.decode("utf-8")
        if text.count(original) != 1:
            print(f"SETUP-ERROR {label}: hunk occurs {text.count(original)} times")
            verdicts.append(False)
            continue
        first = run(copy, ids)
        target.write_bytes(text.replace(original, disarmed).encode("utf-8"))
        second = run(copy, ids)
        target.write_bytes(before)
        if target.read_bytes() != before:
            print(f"SETUP-ERROR {label}: restore mismatch")
            verdicts.append(False)
            continue
        third = run(copy, ids)
    skipped = second.get("skipped", 0) > 0 or first.get("skipped", 0) > 0
    proven = passed(first) and second.get("failures", 0) > 0 and second.get("errors") == 0 and passed(third)
    verdict = "PROVEN" if proven else ("SKIPPED-HERE" if skipped else "NOT-PROVEN")
    verdicts.append(proven or skipped)
    print(f"{verdict:12} {label}: armed={first} disarmed={second} re-armed={third}")
print("ALL PROVEN OR PLATFORM-SKIPPED" if all(verdicts) else "SOME CASES NOT PROVEN")
sys.exit(0 if all(verdicts) else 1)
