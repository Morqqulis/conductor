"""Validate untrusted saved metadata before any consumer uses it."""
from datetime import datetime
from pathlib import Path
import re
import uuid

from .contract import (DirectoryIdentity, EvidenceError, ProcessResult, ProjectIdentity,
                       Snapshot, fields, parse_spec, relative_path, string)


def invalid(message="Invalid evidence record"):
    raise EvidenceError("invalid_record", message)


def integer(value, minimum=None):
    if type(value) is not int or (minimum is not None and value < minimum):
        invalid()


def digest(value, nullable=False):
    if nullable and value is None:
        return
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        invalid("Invalid content fingerprint")


def strings(values):
    if not isinstance(values, list):
        invalid()
    for value in values:
        string(value)


def run_id(value):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            invalid("Expected canonical UUID")
    except (ValueError, AttributeError) as exc:
        raise EvidenceError("invalid_id", "Expected canonical UUID") from exc
    return value


def directory(value):
    fields(value, DirectoryIdentity.__dataclass_fields__)
    string(value["device"])
    string(value["file_id"])
    if value["birth_ns"] is not None:
        integer(value["birth_ns"], 0)


def snapshot(value):
    fields(value, Snapshot.__dataclass_fields__)
    digest(value["digest"])
    digest(value["tool_digest"])
    digest(value["environment_hmac"], True)
    digest(value["environment_key_id"], True)
    strings(value["issues"])
    executable = value["executable"]
    if not isinstance(executable, dict):
        invalid("Executable observation must be an object")
    if executable or not value["issues"]:
        fields(executable, ("path", "size", "sha256"))
        string(executable["path"])
        integer(executable["size"], 0)
        digest(executable["sha256"])
    if not isinstance(value["entries"], list):
        invalid()
    seen = set()
    for entry in value["entries"]:
        fields(entry, ("path", "kind", "size", "executable_bits", "sha256"))
        relative_path(entry["path"])
        if entry["path"] in seen:
            invalid("Duplicate snapshot path")
        seen.add(entry["path"])
        if entry["kind"] not in ("file", "directory"):
            invalid("Unknown snapshot entry kind")
        integer(entry["size"], 0)
        integer(entry["executable_bits"], 0)
        digest(entry["sha256"], True)
        if entry["kind"] == "file" and entry["sha256"] is None:
            invalid("File content fingerprint missing")


def from_record(data: dict) -> dict:
    fields(data, ("schema_version", "id", "created_at", "finalized", "project",
                  "spec", "before", "after", "process", "limitations"))
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        invalid("Unsupported record version")
    if data["finalized"] is not True:
        invalid("Unfinished record")
    run_id(data["id"])
    try:
        stamp = datetime.fromisoformat(string(data["created_at"]))
        if stamp.utcoffset() is None:
            invalid("Timestamp must include timezone")
    except ValueError as exc:
        raise EvidenceError("invalid_record", "Invalid timestamp") from exc
    project = data["project"]
    fields(project, ProjectIdentity.__dataclass_fields__)
    if not Path(string(project["root"])).is_absolute():
        invalid("Project root must be absolute")
    digest(project["key"])
    if project["kind"] not in ("git", "directory"):
        invalid()
    directory(project["directory_id"])
    if project["git_directory_id"] is not None:
        directory(project["git_directory_id"])
    if (project["kind"] == "git") != (project["git_directory_id"] is not None):
        invalid()
    strings(project["issues"])
    parse_spec(data["spec"])
    snapshot(data["before"])
    snapshot(data["after"])
    process = data["process"]
    fields(process, ProcessResult.__dataclass_fields__)
    if process["execution"] not in ("succeeded", "failed", "interrupted", "recording_error"):
        invalid()
    if process["exit_code"] is not None:
        integer(process["exit_code"])
    for field in ("duration_ms", "stdout_bytes", "stderr_bytes"):
        integer(process[field], 0)
    if process["stdout_bytes"] + process["stderr_bytes"] > 67108864:
        invalid("Output exceeds capture limit")
    for field in ("stdout_sha256", "stderr_sha256"):
        digest(process[field])
    if type(process["output_complete"]) is not bool:
        invalid()
    strings(process["errors"])
    if process["execution"] == "succeeded" and (
        process["exit_code"] != 0 or not process["output_complete"] or process["errors"]
    ):
        invalid("Contradictory success record")
    if process["execution"] == "failed" and process["exit_code"] in (0, None):
        invalid("Failure lacks nonzero process result")
    strings(data["limitations"])
    return data
