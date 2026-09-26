"""Versioned public types and strict run-description parsing."""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import json
import math
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath


class EvidenceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RunSpec:
    schema_version: int
    name: str
    argv: tuple[str, ...]
    cwd: str
    inputs: tuple[str, ...]
    environment: tuple[str, ...]
    external_state: str
    timeout_seconds: float


@dataclass(frozen=True)
class DirectoryIdentity:
    device: str
    file_id: str
    birth_ns: int | None


@dataclass(frozen=True)
class ProjectIdentity:
    root: Path
    key: str
    kind: str
    directory_id: DirectoryIdentity
    git_directory_id: DirectoryIdentity | None
    issues: tuple[str, ...]


@dataclass
class Snapshot:
    digest: str
    entries: list[dict]
    environment_hmac: str | None
    environment_key_id: str | None
    executable: dict
    tool_digest: str
    issues: list[str]


@dataclass
class ProcessResult:
    execution: str
    exit_code: int | None
    duration_ms: int
    stdout_bytes: int
    stderr_bytes: int
    stdout_sha256: str
    stderr_sha256: str
    output_complete: bool
    errors: list[str]


@dataclass(frozen=True)
class RunHandle:
    id: str
    directory: Path
    project: ProjectIdentity


@dataclass
class Assessment:
    status: str
    reasons: list[str]
    limitations: list[str]


def to_json(value):
    if is_dataclass(value):
        return to_json(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: to_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_json(item) for item in value]
    return value


def canonical(value) -> bytes:
    return json.dumps(to_json(value), ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def read_json(text: str):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise EvidenceError("invalid_json", "Duplicate JSON field")
            result[key] = value
        return result

    def constant(_):
        raise EvidenceError("invalid_json", "Non-finite JSON number")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, RecursionError) as exc:
        raise EvidenceError("invalid_json", "Malformed JSON") from exc


def fields(data, expected):
    if not isinstance(data, dict) or set(data) != set(expected):
        raise EvidenceError("invalid_fields", "Missing or unknown fields")


def string(value, *, empty=False):
    if not isinstance(value, str) or "\0" in value or (not empty and not value.strip()):
        raise EvidenceError("invalid_string", "Expected a nonempty string without NUL")
    return value


def relative_path(value: str) -> str:
    string(value)
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    if posix.is_absolute() or windows.drive or windows.root or ".." in windows.parts:
        raise EvidenceError("invalid_path", "Expected a relative path within the project")
    if any(part.casefold() == ".git" for part in windows.parts):
        raise EvidenceError("invalid_path", "Git metadata is not a verification input")
    return value


def parse_spec(data: dict) -> RunSpec:
    fields(data, RunSpec.__dataclass_fields__)
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise EvidenceError("unsupported_version", "Expected run schema version 1")
    string(data["name"])
    for name in ("argv", "inputs", "environment"):
        values = data[name]
        if not isinstance(values, list) or (name != "environment" and not values):
            raise EvidenceError("invalid_list", "Expected an array of strings")
        for index, value in enumerate(values):
            string(value, empty=(name == "argv" and index > 0))
    relative_path(data["cwd"])
    for value in data["inputs"]:
        relative_path(value)
    if any("=" in value for value in data["environment"]):
        raise EvidenceError("invalid_environment", "Environment entries must be names")
    if data["external_state"] not in ("none_declared", "unknown"):
        raise EvidenceError("invalid_external_state", "Unknown external-state declaration")
    timeout = data["timeout_seconds"]
    if (type(timeout) not in (int, float) or timeout > sys.float_info.max or
            not math.isfinite(timeout) or timeout <= 0):
        raise EvidenceError("invalid_timeout", "Timeout must be finite and positive")
    return RunSpec(1, data["name"], tuple(data["argv"]), data["cwd"],
                   tuple(data["inputs"]), tuple(data["environment"]),
                   data["external_state"], timeout)
