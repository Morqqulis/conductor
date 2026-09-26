"""Explicit run orchestration and read-only evidence commands."""
import argparse
import json
import os
from pathlib import Path
import sys

from .assessment import assess
from .contract import EvidenceError, parse_spec, read_json, to_json
from .identity import identify_project, resolve_executable
from .inputs import capture_inputs
from .process import capture_process
from .store import begin_run, evidence_home, finish_run, list_runs, load_key, load_run


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise EvidenceError("invalid_arguments", "Invalid command arguments; see --help")


def parser():
    result = Parser(description="Save verification output locally; arguments/output may contain secrets.")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("run", "list", "show", "check"):
        command = commands.add_parser(name)
        command.add_argument("--project", type=Path, required=True)
        if name == "run":
            command.add_argument("--spec", type=Path, required=True)
        elif name in ("show", "check"):
            command.add_argument("--id", required=True)
        else:
            command.add_argument("--limit", type=int, default=20)
    return result


def exit_for_process(process):
    if process.exit_code not in (None, 0):
        if "timeout" in process.errors:
            return 124
        if "interrupt" in process.errors:
            return 130
        return process.exit_code if process.exit_code > 0 else 128 - process.exit_code
    return 0 if process.execution == "succeeded" and process.output_complete else 2


def run_command(args, project, home, env):
    spec = parse_spec(read_json(args.spec.read_text(encoding="utf-8")))
    cwd = (project.root / spec.cwd).resolve(strict=True)
    if not cwd.is_dir() or not cwd.is_relative_to(project.root):
        raise EvidenceError("invalid_cwd", "Working directory must be inside the project")
    executable = resolve_executable(spec.argv[0], cwd, env)
    handle = begin_run(home, project)
    key = load_key(home, create=True)
    before = capture_inputs(project, spec, env, key)
    print("Evidence: command arguments and raw output are saved locally and may contain secrets.", file=sys.stderr)
    result = capture_process((str(executable), *spec.argv[1:]), cwd, env, handle.directory,
                             spec.timeout_seconds)
    after = capture_inputs(project, spec, env, key)
    finish_run(handle, spec, before, after, result)
    return exit_for_process(result), dict(id=handle.id, execution=result.execution,
        exit_code=result.exit_code, output_complete=result.output_complete,
        issues=sorted(set(before.issues + after.issues + result.errors)),
        record_path=str(handle.directory / "record.json"),
        stdout_path=str(handle.directory / "stdout.bin"), stderr_path=str(handle.directory / "stderr.bin"))


def execute(args, project, home, env):
    if args.command == "run":
        return run_command(args, project, home, env)
    if args.command == "list":
        return 0, dict(runs=list_runs(home, project, args.limit))
    record = load_run(home, project, args.id)
    directory = home / "projects" / project.key / "runs" / args.id
    if args.command == "show":
        return 0, dict(record=record, stdout_path=str(directory / "stdout.bin"),
                       stderr_path=str(directory / "stderr.bin"))
    spec = parse_spec(record["spec"])
    key = load_key(home, create=False)
    current = capture_inputs(project, spec, env, key)
    outcome = assess(record, project, current)
    return (0 if outcome.status == "MATCH" else 1), dict(to_json(outcome),
        id=args.id, scope=record["spec"], observed=to_json(current),
        stdout_path=str(directory / "stdout.bin"), stderr_path=str(directory / "stderr.bin"),
        saved_execution=record["process"])


def main(argv=None):
    args = None
    try:
        args = parser().parse_args(argv)
        env = dict(os.environ)
        project = identify_project(args.project)
        code, body = execute(args, project, evidence_home(env), env)
        body["project_key"] = project.key
    except EvidenceError as exc:
        unknown = exc.code in ("record_missing", "project_identity", "git_identity", "key_io", "invalid_key")
        code = 1 if args and args.command == "check" and unknown else 2
        body = dict(status="INDETERMINATE" if code == 1 else "INVALID",
                    error=exc.code, message=str(exc))
        print(json.dumps(dict(module="evidence", error=exc.code)), file=sys.stderr)
    except (OSError, UnicodeError, ValueError) as exc:
        code = 2
        body = dict(status="INVALID", error="io_error", message="Cannot complete evidence operation")
        print(json.dumps(dict(module="evidence", error="io_error", kind=type(exc).__name__)), file=sys.stderr)
    body["schema_version"] = 1
    print(json.dumps(body, ensure_ascii=True, sort_keys=True, allow_nan=False))
    return code
