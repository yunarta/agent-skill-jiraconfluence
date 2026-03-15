from __future__ import annotations

import json
import sys
from typing import Any


SUCCESS = "SUCCESS"
PARTIAL = "PARTIAL"
BLOCKED = "BLOCKED"


def emit_json(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _normalize_status(status: Any) -> int | None:
    if isinstance(status, int):
        return status
    return None


def _status_outcome(status: int | None) -> tuple[str, str, float]:
    if status is None:
        return PARTIAL, "observe", 0.7
    if 200 <= status < 300:
        return SUCCESS, "proceed", 0.98
    if 300 <= status < 400:
        return PARTIAL, "observe", 0.75
    if status == 404:
        return BLOCKED, "double_check", 0.92
    return BLOCKED, "block", 0.96


def _append_next_action(next_actions: list[str], text: str) -> None:
    if text not in next_actions:
        next_actions.append(text)


def _summarize_jira(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]], list[str]]:
    entity = payload.get("entity", "unknown")
    action = payload.get("action", "unknown")
    target = payload.get("target", "<unknown>")
    mode = payload.get("mode", "live")
    status = _normalize_status(payload.get("status"))
    anomalies: list[dict[str, Any]] = []
    next_actions: list[str] = []

    if mode == "dry-run":
        return (
            f"Prepared Jira {entity} {action} request for {target}.",
            anomalies,
            ["Review the endpoint and payload, then rerun without --dry-run if it still looks correct."],
        )

    summary = f"Jira {entity} {action} completed for {target}."
    if status is not None:
        summary = f"Jira {entity} {action} returned HTTP {status} for {target}."

    response = payload.get("response")
    if action == "list" and isinstance(response, list) and not response:
        anomalies.append(
            {
                "code": "empty_result",
                "severity": "medium",
                "message": f"{entity} {action} returned no records for {target}.",
            }
        )
        _append_next_action(next_actions, "Double-check whether the target should exist before taking follow-up action.")

    if entity == "remotelink" and action == "list" and isinstance(response, list) and len(response) > 1:
        anomalies.append(
            {
                "code": "multiple_remote_links",
                "severity": "medium",
                "message": f"{target} has {len(response)} remote links; verify which one is canonical.",
            }
        )
        _append_next_action(next_actions, "Review duplicate or historical remote links before assuming a single canonical page.")

    if entity == "metadata" and action == "list" and isinstance(response, dict):
        if not response.get("values") and not response.get("results"):
            anomalies.append(
                {
                    "code": "metadata_empty",
                    "severity": "medium",
                    "message": f"No metadata entries were returned for {target}.",
                }
            )
            _append_next_action(next_actions, "Double-check the project key and issue type availability on the Jira tenant.")

    return summary, anomalies, next_actions


def _summarize_confluence(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]], list[str]]:
    command = payload.get("command", "unknown")
    mode = payload.get("mode", "live")
    anomalies: list[dict[str, Any]] = []
    next_actions: list[str] = []

    if command == "validate":
        return ("Validated local report input against report.v1 contract.", anomalies, next_actions)

    if command == "publish":
        target_title = payload.get("target_title") or payload.get("page", {}).get("title") or "<unknown>"
        if mode == "dry-run":
            action = payload.get("action", "create")
            return (
                f"Prepared Confluence publish dry-run for '{target_title}' with action '{action}'.",
                anomalies,
                ["Review the representation, body preview, and Jira backlink targets before publishing live."],
            )

        page = payload.get("page", {})
        page_id = page.get("id", "<unknown>")
        summary = f"Published Confluence page '{target_title}' as page {page_id}."
        remote_links = payload.get("jira_remote_links", [])
        if remote_links:
            missing = [item for item in remote_links if not item.get("remote_link_id")]
            if missing:
                anomalies.append(
                    {
                        "code": "missing_remote_link_id",
                        "severity": "high",
                        "message": "One or more Jira backlink writes did not return a remote_link_id.",
                    }
                )
                _append_next_action(next_actions, "Double-check Jira issue backlinks before assuming the page is fully cross-linked.")
        else:
            _append_next_action(next_actions, "If this page should connect back to Jira artifacts, rerun publish with --link-jira or --link-upstream-jira.")
        return summary, anomalies, next_actions

    if command == "space-create":
        action = payload.get("action", "create")
        space = payload.get("space", {})
        return (f"Confluence space {action} completed for '{space.get('key', '<unknown>')}'.", anomalies, next_actions)

    if command == "space-link-project":
        space = payload.get("space", {})
        return (f"Updated Jira project linkage metadata for Confluence space '{space.get('key', '<unknown>')}'.", anomalies, next_actions)

    if command == "space-get":
        space = payload.get("space", {})
        properties = payload.get("properties", [])
        if not properties:
            anomalies.append(
                {
                    "code": "space_has_no_properties",
                    "severity": "low",
                    "message": f"Space '{space.get('key', '<unknown>')}' has no Confluence space properties.",
                }
            )
            _append_next_action(next_actions, "If this space should be project-linked, check whether openclaw.project_link has been set.")
        return (f"Read Confluence space '{space.get('key', '<unknown>')}'.", anomalies, next_actions)

    if command == "space-list":
        count = payload.get("count", 0)
        return (f"Listed {count} Confluence spaces.", anomalies, next_actions)

    return ("Confluence command completed.", anomalies, next_actions)


def attach_agentic_contract(tool: str, payload: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(payload)
    status = _normalize_status(enriched.get("status"))

    if tool == "jira":
        summary, anomalies, next_actions = _summarize_jira(enriched)
    else:
        summary, anomalies, next_actions = _summarize_confluence(enriched)

    outcome, decision, confidence = _status_outcome(status)
    if enriched.get("mode") == "dry-run":
        outcome, decision, confidence = PARTIAL, "review_then_proceed", 0.9

    if anomalies and decision == "proceed":
        decision = "double_check"
        confidence = min(confidence, 0.82)
        if outcome == SUCCESS:
            outcome = PARTIAL

    enriched["agentic"] = {
        "summary": summary,
        "outcome": outcome,
        "decision": decision,
        "confidence": confidence,
        "anomalies": anomalies,
        "next_actions": next_actions,
    }
    return enriched


def build_error_payload(
    *,
    tool: str,
    command: str,
    message: str,
    status: int | None = None,
    response: Any | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "tool": tool,
        "command": command,
        "status": status,
        "error": {
            "message": message,
            "response": response,
            "details": details or {},
        },
    }
    outcome, decision, confidence = _status_outcome(status)
    if status is None:
        outcome, decision, confidence = BLOCKED, "double_check", 0.86
    output["agentic"] = {
        "summary": message,
        "outcome": outcome,
        "decision": decision,
        "confidence": confidence,
        "anomalies": [
            {
                "code": "command_error",
                "severity": "high",
                "message": message,
            }
        ],
        "next_actions": [
            "Inspect the reported error details before retrying.",
        ],
    }
    return output


def parse_exit_payload(raw: str) -> tuple[str, int | None, Any | None]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw, None, None
    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error") or payload.get("path") or "Command failed."
        status = payload.get("status") if isinstance(payload.get("status"), int) else None
        response = payload.get("response")
        return str(message), status, response
    return raw, None, payload
