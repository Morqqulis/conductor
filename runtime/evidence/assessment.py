"""Compare only observed conditions; never label an old execution a new pass."""
from .contract import Assessment, ProjectIdentity, Snapshot, to_json


def assess(record: dict, project: ProjectIdentity, current: Snapshot) -> Assessment:
    limitations = record["limitations"]
    if record["project"]["key"] != project.key:
        return Assessment("INDETERMINATE", ["different_project"], limitations)
    snapshots = [record["before"], record["after"], to_json(current)]
    unknown = list(project.issues) + list(record["project"]["issues"])
    if record["spec"]["external_state"] == "unknown":
        unknown.append("external_state_unknown")
    for item in snapshots:
        unknown.extend(item["issues"])
        if item["environment_hmac"] is None or item["environment_key_id"] is None:
            unknown.append("environment_key_unavailable")
    if len({item["environment_key_id"] for item in snapshots}) != 1:
        unknown.append("environment_key_changed")
    if unknown:
        return Assessment("INDETERMINATE", sorted(set(unknown)), limitations)
    process = record["process"]
    if process["execution"] != "succeeded" or process["exit_code"] != 0:
        return Assessment("NOT_SUCCESSFUL", ["saved_execution_not_successful"], limitations)
    if not process["output_complete"]:
        return Assessment("INDETERMINATE", ["saved_output_incomplete"], limitations)
    changed = []
    for field in ("digest", "entries", "environment_hmac", "executable", "tool_digest"):
        if snapshots[0][field] != snapshots[1][field]:
            changed.append("changed_during_run:" + field)
        if snapshots[1][field] != snapshots[2][field]:
            changed.append("changed_since_run:" + field)
    if changed:
        return Assessment("CHANGED", changed, limitations)
    return Assessment("MATCH", ["observed_conditions_match_saved_run"], limitations)
