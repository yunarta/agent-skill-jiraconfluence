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


def _search_pagination(response: dict[str, Any]) -> dict[str, Any]:
    issues = response.get("issues", [])
    returned = len(issues) if isinstance(issues, list) else 0

    next_page_token = response.get("nextPageToken")
    is_last = response.get("isLast")
    start_at = response.get("startAt")
    total = response.get("total")
    max_results = response.get("maxResults")

    has_more: bool | None = None
    if isinstance(next_page_token, str) and next_page_token:
        has_more = True
    elif isinstance(is_last, bool):
        has_more = not is_last
    elif isinstance(total, int) and isinstance(start_at, int):
        has_more = (start_at + returned) < total

    pagination: dict[str, Any] = {"returned": returned}
    if has_more is not None:
        pagination["has_more"] = has_more
    if isinstance(total, int):
        pagination["total"] = total
    if isinstance(start_at, int):
        pagination["start_at"] = start_at
    if isinstance(max_results, int):
        pagination["max_results"] = max_results
    if isinstance(next_page_token, str) and next_page_token:
        pagination["next_page_token_present"] = True
    return pagination


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

    if entity == "sprint" and action in {"add-items", "remove-items"}:
        issue_count = 0
        request_payload = payload.get("payload")
        if isinstance(request_payload, dict):
            issues = request_payload.get("issues")
            if isinstance(issues, list):
                issue_count = len(issues)
        summary = f"Jira sprint {action} returned HTTP {status} for {target} with {issue_count} issues."

    if entity == "sprint" and action in {"start", "complete", "finish"}:
        verb = "start" if action == "start" else "complete"
        summary = f"Jira sprint {verb} returned HTTP {status} for {target}."

    if entity == "transition" and action == "list" and isinstance(response, dict):
        transitions = response.get("transitions", [])
        summary = f"Jira transition list returned HTTP {status} for {target} with {len(transitions)} transitions."
        if not transitions:
            anomalies.append(
                {
                    "code": "no_transitions_available",
                    "severity": "medium",
                    "message": f"No workflow transitions were returned for {target}.",
                }
            )
            _append_next_action(next_actions, "Double-check the issue status and workflow before attempting a transition.")

    if entity == "transition" and action == "execute":
        summary = f"Jira transition execute returned HTTP {status} for {target}."
        available = []
        if isinstance(response, dict):
            available = response.get("availableTransitions", [])
        if available:
            _append_next_action(next_actions, "If the new status was not the intended one, review the available transition ids returned with the command.")

    if entity == "assignee" and action == "get" and isinstance(response, dict):
        fields = response.get("fields", {})
        assignee = fields.get("assignee") if isinstance(fields, dict) else None
        assignee_name = "<unassigned>"
        if isinstance(assignee, dict):
            assignee_name = assignee.get("displayName") or assignee.get("accountId") or assignee_name
        summary = f"Jira assignee get returned HTTP {status} for {target}: {assignee_name}."

    if entity == "assignee" and action in {"set", "clear"}:
        verb = "set" if action == "set" else "clear"
        summary = f"Jira assignee {verb} returned HTTP {status} for {target}."

    if entity == "issuelink" and action == "types" and isinstance(response, dict):
        link_types = response.get("issueLinkTypes", [])
        summary = f"Jira issue link types returned HTTP {status} with {len(link_types)} link types."

    if entity == "issuelink" and action == "list" and isinstance(response, dict):
        fields = response.get("fields", {})
        issue_links = fields.get("issuelinks", []) if isinstance(fields, dict) else []
        summary = f"Jira issue link list returned HTTP {status} for {target} with {len(issue_links)} links."
        if not issue_links:
            anomalies.append(
                {
                    "code": "issue_links_empty",
                    "severity": "low",
                    "message": f"No Jira issue links were returned for {target}.",
                }
            )

    if entity == "issuelink" and action in {"create", "delete"}:
        summary = f"Jira issue link {action} returned HTTP {status} for {target}."

    if entity == "comment" and action == "list" and isinstance(response, dict):
        comments = response.get("comments", [])
        summary = f"Jira comment list returned HTTP {status} for {target} with {len(comments)} comments."
        if not comments:
            anomalies.append(
                {
                    "code": "comments_empty",
                    "severity": "low",
                    "message": f"No Jira comments were returned for {target}.",
                }
            )

    if entity == "comment" and action == "create" and isinstance(response, dict):
        comment_id = response.get("id", "<unknown>")
        summary = f"Jira comment create returned HTTP {status} for {target} as comment {comment_id}."

    if entity == "comment" and action == "delete":
        summary = f"Jira comment delete returned HTTP {status} for {target}."

    if entity == "search" and action == "list" and isinstance(response, dict):
        pagination = _search_pagination(response)
        returned = pagination.get("returned", 0)
        has_more = pagination.get("has_more")
        suffix = ""
        if has_more is True:
            suffix = " More results are available."
        elif has_more is False:
            suffix = " End of results."
        summary = f"Jira search list returned HTTP {status} with {returned} issues.{suffix}"
        issues = response.get("issues", [])
        if not issues:
            anomalies.append(
                {
                    "code": "search_empty",
                    "severity": "medium",
                    "message": "Jira search returned no issues for the current JQL.",
                }
            )
            _append_next_action(next_actions, "Double-check the JQL, field projection, and project scope before assuming there is no matching work.")
        next_page_token = response.get("nextPageToken")
        if next_page_token:
            _append_next_action(next_actions, "Use --next-page-token to continue the search result window if you need more issues.")
        if has_more and not next_page_token:
            start_at = response.get("startAt")
            total = response.get("total")
            if isinstance(start_at, int) and isinstance(total, int) and returned:
                _append_next_action(
                    next_actions,
                    f"Use --query startAt={start_at + returned} to fetch the next page when nextPageToken is not available.",
                )

    if entity == "epic" and action == "get" and isinstance(response, dict):
        epic_name = response.get("name") or response.get("summary") or target
        summary = f"Jira epic get returned HTTP {status} for {epic_name}."

    if entity == "epic" and action == "issues" and isinstance(response, dict):
        issues = response.get("issues", [])
        summary = f"Jira epic issues returned HTTP {status} for {target} with {len(issues)} issues."
        inspection_mode = response.get("inspectionMode")
        if inspection_mode == "search_fallback":
            summary = f"Jira epic issues returned HTTP {status} for {target} with {len(issues)} issues via search fallback."
            anomalies.append(
                {
                    "code": "epic_inspection_search_fallback",
                    "severity": "low",
                    "message": f"Epic inspection for {target} used search fallback semantics instead of the direct Agile list endpoint.",
                }
            )
            _append_next_action(
                next_actions,
                "If the returned Epic membership still looks wrong, double-check the issue parent or Epic link fields on one sample issue.",
            )
        if not issues:
            anomalies.append(
                {
                    "code": "epic_issues_empty",
                    "severity": "medium" if inspection_mode == "search_fallback" else "low",
                    "message": f"No issues are currently assigned to epic {target}.",
                }
            )
            if inspection_mode == "search_fallback":
                _append_next_action(
                    next_actions,
                    "If you recently set Epic membership, re-read one issue directly to confirm whether Jira has applied the parent relationship yet.",
                )

    if entity == "epic" and action in {"set", "clear"} and isinstance(response, dict):
        issue_count = response.get("issueCount", 0)
        summary = f"Jira epic {action} returned HTTP {status} for {target} with {issue_count} issues."

    if entity == "rank" and action == "execute" and isinstance(response, dict):
        issue_count = response.get("issueCount", 0)
        summary = f"Jira rank execute returned HTTP {status} for {target} with {issue_count} issues."
        if issue_count == 0:
            anomalies.append(
                {
                    "code": "rank_issue_count_zero",
                    "severity": "medium",
                    "message": "Rank execute did not carry any issue keys.",
                }
            )
            _append_next_action(next_actions, "Double-check the issue selection before assuming the backlog order changed.")

    if entity == "board" and action in {"list", "issues", "backlog"} and isinstance(response, dict):
        items = response.get("values")
        if not isinstance(items, list):
            items = response.get("issues") if isinstance(response.get("issues"), list) else []
        label = "boards" if action == "list" else "issues"
        summary = f"Jira board {action} returned HTTP {status} for {target} with {len(items)} {label}."
        if not items:
            anomalies.append(
                {
                    "code": "board_result_empty",
                    "severity": "medium",
                    "message": f"Board {action} returned no records for {target}.",
                }
            )
            _append_next_action(next_actions, "Double-check the board id, filters, and sprint state before assuming the board is empty.")

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
        issue_types = response.get("issueTypes")
        if isinstance(issue_types, list):
            if issue_types:
                summary = f"Jira metadata list returned HTTP {status} for {target} with {len(issue_types)} issue types."
            else:
                anomalies.append(
                    {
                        "code": "metadata_empty",
                        "severity": "medium",
                        "message": f"No metadata entries were returned for {target}.",
                    }
                )
                _append_next_action(next_actions, "Double-check the project key and issue type availability on the Jira tenant.")
        elif not response.get("values") and not response.get("results"):
            anomalies.append(
                {
                    "code": "metadata_empty",
                    "severity": "medium",
                    "message": f"No metadata entries were returned for {target}.",
                }
            )
            _append_next_action(next_actions, "Double-check the project key and issue type availability on the Jira tenant.")

    if entity == "sprint" and action == "remove-items" and isinstance(response, dict):
        note = response.get("note")
        if isinstance(note, str) and "backlog" in note.lower():
            _append_next_action(next_actions, "Confirm the issues now sit in backlog and are no longer assigned to another open sprint.")

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
    if tool == "jira" and enriched.get("entity") == "search" and enriched.get("action") == "list":
        response = enriched.get("response")
        if isinstance(response, dict):
            enriched["agentic"]["pagination"] = _search_pagination(response)
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
