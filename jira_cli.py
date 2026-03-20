#!/usr/bin/env python3
"""Minimal Jira CRUD CLI with inspectable request mapping."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tool_contract import attach_agentic_contract, build_error_payload, emit_json, parse_exit_payload


WRITE_ACTIONS = {"create", "update", "delete", "execute", "set", "clear"}
SPRINT_CUSTOM_ACTIONS = {"add-items", "remove-items", "start", "complete", "finish"}


@dataclass(frozen=True)
class Route:
    method: str
    path_template: str
    requires_resource: bool
    requires_payload: bool
    required_query_keys: tuple[str, ...] = ()


ROUTES: dict[str, dict[str, Route]] = {
    "issue": {
        "create": Route("POST", "/rest/api/3/issue", False, True),
        "get": Route("GET", "/rest/api/3/issue/{resource}", True, False),
        "update": Route("PUT", "/rest/api/3/issue/{resource}", True, True),
        "delete": Route("DELETE", "/rest/api/3/issue/{resource}", True, False),
    },
    "project": {
        "create": Route("POST", "/rest/api/3/project", False, True),
        "get": Route("GET", "/rest/api/3/project/{resource}", True, False),
        "update": Route("PUT", "/rest/api/3/project/{resource}", True, True),
        "delete": Route("DELETE", "/rest/api/3/project/{resource}", True, False),
    },
    "sprint": {
        "create": Route("POST", "/rest/agile/1.0/sprint", False, True),
        "get": Route("GET", "/rest/agile/1.0/sprint/{resource}", True, False),
        "update": Route("PUT", "/rest/agile/1.0/sprint/{resource}", True, True),
        "delete": Route("DELETE", "/rest/agile/1.0/sprint/{resource}", True, False),
    },
    "field": {
        "list": Route("GET", "/rest/api/3/field", False, False),
        "create": Route("POST", "/rest/api/3/field", False, True),
    },
    "metadata": {
        "list": Route("GET", "/rest/api/3/issue/createmeta/{resource}/issuetypes", True, False),
        "get": Route(
            "GET",
            "/rest/api/3/issue/createmeta/{resource}/issuetypes/{issuetypeId}",
            True,
            False,
            ("issuetypeId",),
        ),
    },
    "remotelink": {
        "list": Route("GET", "/rest/api/2/issue/{resource}/remotelink", True, False),
        "create": Route("POST", "/rest/api/2/issue/{resource}/remotelink", True, True),
        "delete": Route(
            "DELETE",
            "/rest/api/2/issue/{resource}/remotelink/{linkId}",
            True,
            False,
            ("linkId",),
        ),
    },
    "transition": {
        "list": Route("GET", "/rest/api/3/issue/{resource}/transitions", True, False),
        "execute": Route("POST", "/rest/api/3/issue/{resource}/transitions", True, False),
    },
    "assignee": {
        "get": Route("GET", "/rest/api/3/issue/{resource}", True, False),
        "set": Route("PUT", "/rest/api/3/issue/{resource}/assignee", True, False),
        "clear": Route("PUT", "/rest/api/3/issue/{resource}/assignee", True, False),
    },
    "issuelink": {
        "types": Route("GET", "/rest/api/3/issueLinkType", False, False),
        "list": Route("GET", "/rest/api/3/issue/{resource}", True, False),
        "create": Route("POST", "/rest/api/3/issueLink", False, False),
        "delete": Route("DELETE", "/rest/api/3/issueLink/{resource}", True, False),
    },
    "board": {
        "list": Route("GET", "/rest/agile/1.0/board", False, False),
        "issues": Route("GET", "/rest/agile/1.0/board/{resource}/issue", True, False),
        "backlog": Route("GET", "/rest/agile/1.0/board/{resource}/backlog", True, False),
    },
    "comment": {
        "list": Route("GET", "/rest/api/3/issue/{resource}/comment", True, False),
        "create": Route("POST", "/rest/api/3/issue/{resource}/comment", True, False),
        "delete": Route(
            "DELETE",
            "/rest/api/3/issue/{resource}/comment/{commentId}",
            True,
            False,
            ("commentId",),
        ),
    },
    "search": {
        "list": Route("GET", "/rest/api/3/search/jql", False, False),
    },
    "epic": {
        "get": Route("GET", "/rest/agile/1.0/epic/{resource}", True, False),
        "issues": Route("GET", "/rest/agile/1.0/epic/{resource}/issue", True, False),
        "set": Route("POST", "/rest/agile/1.0/epic/{resource}/issue", True, False),
        "clear": Route("POST", "/rest/agile/1.0/epic/none/issue", False, False),
    },
    "rank": {
        "execute": Route("PUT", "/rest/agile/1.0/issue/rank", False, False),
    },
}


def parse_args() -> argparse.Namespace:
    actions = sorted({action for entity_routes in ROUTES.values() for action in entity_routes} | SPRINT_CUSTOM_ACTIONS)
    parser = argparse.ArgumentParser(description="Jira CRUD CLI")
    parser.add_argument("entity", choices=sorted(ROUTES))
    parser.add_argument("action", choices=actions)
    parser.add_argument("--resource", help="Issue key/id, project key/id, or sprint id")
    parser.add_argument("--payload", help="Inline JSON payload")
    parser.add_argument("--payload-file", help="Path to JSON payload file")
    parser.add_argument("--query", action="append", default=[], help="Extra query param in key=value form")
    parser.add_argument("--issue", action="append", default=[], help="Issue key/id. Repeat or provide comma-separated values.")
    parser.add_argument("--start-date", help="Sprint start date in Jira ISO format")
    parser.add_argument("--end-date", help="Sprint end date in Jira ISO format")
    parser.add_argument("--goal", help="Sprint goal override")
    parser.add_argument("--rank-before-issue", help="Rank moved issues before this issue key")
    parser.add_argument("--rank-after-issue", help="Rank moved issues after this issue key")
    parser.add_argument("--rank-custom-field-id", type=int, help="Ranking custom field id for sprint issue moves")
    parser.add_argument("--transition-id", help="Jira transition id")
    parser.add_argument("--transition-name", help="Jira transition name")
    parser.add_argument("--account-id", help="Jira accountId for assignee updates")
    parser.add_argument("--link-type", help="Jira issue link type name, for example 'Relates'")
    parser.add_argument("--inward-issue", help="Issue key/id for the inward side of a Jira issue link")
    parser.add_argument("--outward-issue", help="Issue key/id for the outward side of a Jira issue link")
    parser.add_argument("--start-at", type=int, help="Pagination start index for board reads")
    parser.add_argument("--max-results", type=int, help="Pagination size for board reads")
    parser.add_argument("--jql", help="JQL string for search inspection")
    parser.add_argument("--field", action="append", default=[], help="Field name for search inspection. Repeat or provide comma-separated values.")
    parser.add_argument("--expand", action="append", default=[], help="Expand token. Repeat or provide comma-separated values.")
    parser.add_argument("--next-page-token", help="Search pagination token for /search/jql")
    parser.add_argument("--comment-body", help="Plain-text Jira comment body")
    parser.add_argument("--comment-id", help="Jira comment id for comment delete")
    parser.add_argument("--dry-run", action="store_true", help="Print request details without sending")
    parser.add_argument("--confirm", action="store_true", help="Required for destructive actions")
    return parser.parse_args()


def load_dotenv_if_present() -> None:
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def parse_payload(args: argparse.Namespace, route: Route) -> Any | None:
    if not route.requires_payload:
        return None

    raw_payload = None
    if args.payload_file:
        with open(args.payload_file, "r", encoding="utf-8") as handle:
            raw_payload = handle.read()
    elif args.payload:
        raw_payload = args.payload

    if raw_payload is None:
        raise SystemExit("This action requires --payload or --payload-file")

    try:
        return json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON payload: {exc}") from exc


def parse_optional_payload(args: argparse.Namespace) -> Any | None:
    if not args.payload and not args.payload_file:
        return None

    raw_payload = None
    if args.payload_file:
        with open(args.payload_file, "r", encoding="utf-8") as handle:
            raw_payload = handle.read()
    elif args.payload:
        raw_payload = args.payload

    try:
        return json.loads(raw_payload) if raw_payload is not None else None
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON payload: {exc}") from exc


def parse_query_pairs(query_pairs: list[str]) -> dict[str, str]:
    query: dict[str, str] = {}
    for item in query_pairs:
        if "=" not in item:
            raise SystemExit(f"Invalid query parameter '{item}'. Use key=value.")
        key, value = item.split("=", 1)
        query[key] = value
    return query


def resolve_route(entity: str, action: str) -> Route:
    try:
        return ROUTES[entity][action]
    except KeyError as exc:
        raise SystemExit(f"Unsupported entity/action pair: {entity}/{action}") from exc


def is_custom_sprint_action(entity: str, action: str) -> bool:
    return entity == "sprint" and action in SPRINT_CUSTOM_ACTIONS


def build_url(base_url: str, route: Route, resource: str | None, query: dict[str, str]) -> str:
    path = route.path_template
    format_values: dict[str, str] = {}
    if route.requires_resource:
        if not resource:
            raise SystemExit("This action requires --resource")
        format_values["resource"] = urllib.parse.quote(resource, safe="")

    remaining_query = dict(query)
    for key in route.required_query_keys:
        value = remaining_query.pop(key, None)
        if not value:
            raise SystemExit(f"This action requires --query {key}=...")
        format_values[key] = urllib.parse.quote(value, safe="")

    if format_values:
        path = path.format(**format_values)

    url = f"{base_url.rstrip('/')}{path}"
    if remaining_query:
        url = f"{url}?{urllib.parse.urlencode(remaining_query)}"
    return url


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted = dict(headers)
    if "Authorization" in redacted:
        redacted["Authorization"] = "Basic ***"
    return redacted


def build_headers(user: str, token: str, has_payload: bool) -> dict[str, str]:
    credentials = f"{user}:{token}".encode("utf-8")
    auth = base64.b64encode(credentials).decode("ascii")
    headers = {
        "Accept": "application/json",
        "Authorization": f"Basic {auth}",
    }
    if has_payload:
        headers["Content-Type"] = "application/json"
    return headers


def enforce_guardrails(args: argparse.Namespace) -> None:
    if args.action == "delete" and not args.confirm:
        raise SystemExit("Delete requires --confirm")
    if args.entity == "project" and args.action in {"create", "delete"} and not args.confirm:
        raise SystemExit("Project create/delete requires --confirm")


def parse_issue_keys(raw_items: list[str]) -> list[str]:
    keys: list[str] = []
    for item in raw_items:
        for part in item.split(","):
            key = part.strip()
            if key and key not in keys:
                keys.append(key)
    return keys


def parse_csv_values(raw_items: list[str]) -> list[str]:
    values: list[str] = []
    for item in raw_items:
        for part in item.split(","):
            value = part.strip()
            if value and value not in values:
                values.append(value)
    return values


def fetch_issue(
    base_url: str,
    headers: dict[str, str],
    issue_key: str,
    *,
    fields: str | None = None,
) -> tuple[str, dict[str, Any]]:
    route = resolve_route("issue", "get")
    query: dict[str, str] = {}
    if fields:
        query["fields"] = fields
    endpoint = build_url(base_url, route, issue_key, query)
    _, body = fetch_jira_json(endpoint, route.method, headers)
    return endpoint, body or {}


def select_transition_id(transitions: list[dict[str, Any]], args: argparse.Namespace) -> str:
    if args.transition_id:
        return args.transition_id

    if not args.transition_name:
        raise SystemExit("Transition execute requires --transition-id or --transition-name.")

    matches = [
        transition
        for transition in transitions
        if str(transition.get("name", "")).strip().lower() == args.transition_name.strip().lower()
    ]
    if not matches:
        raise SystemExit(f"No Jira transition named '{args.transition_name}' was returned for this issue.")
    if len(matches) > 1:
        ids = ", ".join(str(match.get("id", "<unknown>")) for match in matches)
        raise SystemExit(
            f"Transition name '{args.transition_name}' is ambiguous for this issue. Use --transition-id instead. Matches: {ids}"
        )

    transition_id = matches[0].get("id")
    if not transition_id:
        raise SystemExit(f"Transition '{args.transition_name}' did not include an id.")
    return str(transition_id)


def build_transition_execute_payload(args: argparse.Namespace, transitions: list[dict[str, Any]]) -> dict[str, Any]:
    optional_payload = parse_optional_payload(args)
    if optional_payload is not None and not isinstance(optional_payload, dict):
        raise SystemExit("Transition execute payload must be a JSON object.")

    payload = dict(optional_payload or {})
    payload["transition"] = {"id": select_transition_id(transitions, args)}
    return payload


def build_assignee_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.action == "clear":
        return {"accountId": None}
    if not args.account_id:
        raise SystemExit("Assignee set requires --account-id.")
    return {"accountId": args.account_id}


def build_issue_link_payload(args: argparse.Namespace) -> dict[str, Any]:
    optional_payload = parse_optional_payload(args)
    if optional_payload is not None and not isinstance(optional_payload, dict):
        raise SystemExit("Issue link create payload must be a JSON object.")
    if not args.link_type:
        raise SystemExit("Issue link create requires --link-type.")
    if not args.inward_issue or not args.outward_issue:
        raise SystemExit("Issue link create requires both --inward-issue and --outward-issue.")

    payload = dict(optional_payload or {})
    payload["type"] = {"name": args.link_type}
    payload["inwardIssue"] = {"key": args.inward_issue}
    payload["outwardIssue"] = {"key": args.outward_issue}
    return payload


def build_comment_adf(text: str) -> dict[str, Any]:
    paragraphs = []
    for line in text.splitlines() or [""]:
        if line.strip():
            paragraphs.append(
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": line}],
                }
            )
        else:
            paragraphs.append({"type": "paragraph", "content": []})
    return {"type": "doc", "version": 1, "content": paragraphs}


def normalize_issue_rich_text_fields(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        return payload

    normalized = dict(payload)
    normalized_fields = dict(fields)
    description = normalized_fields.get("description")
    if isinstance(description, str):
        normalized_fields["description"] = build_comment_adf(description)
    normalized["fields"] = normalized_fields
    return normalized


def build_comment_payload(args: argparse.Namespace) -> dict[str, Any]:
    optional_payload = parse_optional_payload(args)
    if optional_payload is not None:
        if not isinstance(optional_payload, dict):
            raise SystemExit("Comment create payload must be a JSON object.")
        return optional_payload
    if not args.comment_body:
        raise SystemExit("Comment create requires --comment-body or --payload/--payload-file.")
    return {"body": build_comment_adf(args.comment_body)}


def build_search_query(args: argparse.Namespace, query: dict[str, str]) -> dict[str, str]:
    output = dict(query)
    if args.jql:
        output["jql"] = args.jql
    if "jql" not in output:
        raise SystemExit("Search list requires --jql or --query jql=...")
    fields = parse_csv_values(args.field)
    if fields:
        output["fields"] = ",".join(fields)
    expands = parse_csv_values(args.expand)
    if expands:
        output["expand"] = ",".join(expands)
    if args.max_results is not None:
        output["maxResults"] = str(args.max_results)
    elif "maxResults" not in output:
        output["maxResults"] = "25"
    if args.next_page_token:
        output["nextPageToken"] = args.next_page_token
    return output


def build_epic_issue_payload(args: argparse.Namespace) -> dict[str, Any]:
    optional_payload = parse_optional_payload(args)
    if optional_payload is not None:
        if not isinstance(optional_payload, dict):
            raise SystemExit("Epic set/clear payload must be a JSON object.")
        return optional_payload
    issues = parse_issue_keys(args.issue)
    if not issues:
        raise SystemExit("Epic set/clear requires at least one --issue value.")
    if len(issues) > 50:
        raise SystemExit("Epic set/clear supports at most 50 issues per request.")
    return {"issues": issues}


def build_epic_search_query(epic_key: str, query: dict[str, str], args: argparse.Namespace) -> dict[str, str]:
    output = dict(query)
    output["jql"] = f"parentEpic = {epic_key}"
    fields = parse_csv_values(args.field)
    if not fields:
        fields = ["summary", "issuetype", "parent", "customfield_10014", "status"]
    elif "parent" not in fields:
        fields.append("parent")
    output["fields"] = ",".join(fields)
    expands = parse_csv_values(args.expand)
    if expands:
        output["expand"] = ",".join(expands)
    if args.max_results is not None:
        output["maxResults"] = str(args.max_results)
    elif "maxResults" not in output:
        output["maxResults"] = "50"
    if args.next_page_token:
        output["nextPageToken"] = args.next_page_token
    return output


def filter_epic_search_issues(epic_key: str, response: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        return []
    issues = response.get("issues", [])
    if not isinstance(issues, list):
        return []

    filtered: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        if issue.get("key") == epic_key:
            continue
        fields = issue.get("fields", {})
        if not isinstance(fields, dict):
            continue
        parent = fields.get("parent")
        parent_key = parent.get("key") if isinstance(parent, dict) else None
        epic_link = fields.get("customfield_10014")
        if parent_key == epic_key or epic_link == epic_key:
            filtered.append(issue)
    return filtered


def build_rank_payload(args: argparse.Namespace) -> dict[str, Any]:
    optional_payload = parse_optional_payload(args)
    if optional_payload is not None:
        if not isinstance(optional_payload, dict):
            raise SystemExit("Rank execute payload must be a JSON object.")
        return optional_payload

    issues = parse_issue_keys(args.issue)
    if not issues:
        raise SystemExit("Rank execute requires at least one --issue value.")
    if len(issues) > 50:
        raise SystemExit("Rank execute supports at most 50 issues per request.")
    if args.rank_before_issue and args.rank_after_issue:
        raise SystemExit("Use only one of --rank-before-issue or --rank-after-issue.")
    if not args.rank_before_issue and not args.rank_after_issue:
        raise SystemExit("Rank execute requires --rank-before-issue or --rank-after-issue.")

    payload: dict[str, Any] = {"issues": issues}
    if args.rank_before_issue:
        payload["rankBeforeIssue"] = args.rank_before_issue
    if args.rank_after_issue:
        payload["rankAfterIssue"] = args.rank_after_issue
    if args.rank_custom_field_id is not None:
        payload["rankCustomFieldId"] = args.rank_custom_field_id
    return payload


def with_default_paging(query: dict[str, str], args: argparse.Namespace) -> dict[str, str]:
    output = dict(query)
    if args.start_at is not None and "startAt" not in output:
        output["startAt"] = str(args.start_at)
    if args.max_results is not None and "maxResults" not in output:
        output["maxResults"] = str(args.max_results)
    if "startAt" not in output:
        output["startAt"] = "0"
    if "maxResults" not in output:
        output["maxResults"] = "50"
    return output


def _json_body(payload: Any | None) -> bytes | None:
    if payload is None:
        return None
    return json.dumps(payload).encode("utf-8")


def request_json(url: str, method: str, headers: dict[str, str], payload: Any | None = None) -> tuple[int, Any | None]:
    request = urllib.request.Request(url=url, method=method, headers=headers, data=_json_body(payload))
    with urllib.request.urlopen(request) as response:
        raw = response.read().decode("utf-8")
        parsed = json.loads(raw) if raw else None
        return response.status, parsed


def fetch_jira_json(url: str, method: str, headers: dict[str, str], payload: Any | None = None) -> tuple[int, Any | None]:
    try:
        return request_json(url, method, headers, payload)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        parsed = json.loads(raw) if raw else None
        raise SystemExit(
            json.dumps(
                {
                    "message": "Command failed.",
                    "status": exc.code,
                    "response": parsed,
                },
                indent=2,
            )
        ) from exc


def emit_result(
    *,
    entity: str,
    action: str,
    target: str,
    endpoint: str,
    dry_run: bool,
    method: str,
    headers: dict[str, str],
    payload: Any | None,
    response_status: int | None = None,
    response_body: Any | None = None,
) -> None:
    output: dict[str, Any] = {
        "entity": entity,
        "action": action,
        "target": target,
        "endpoint": endpoint,
        "method": method,
        "mode": "dry-run" if dry_run else "live",
        "headers": redact_headers(headers),
    }
    if payload is not None:
        output["payload"] = payload
    if response_status is not None:
        output["status"] = response_status
    if response_body is not None:
        output["response"] = response_body
    emit_json(attach_agentic_contract("jira", output))


def send_request(
    *,
    entity: str,
    action: str,
    url: str,
    route: Route,
    headers: dict[str, str],
    payload: Any | None,
) -> tuple[int, Any | None, str]:
    def try_search_fallback(original_url: str) -> tuple[int, Any | None, str] | None:
        if entity != "search" or action != "list" or route.method != "GET":
            return None

        parsed = urllib.parse.urlsplit(original_url)
        path = parsed.path
        if "/rest/api/3/search/jql" not in path and "/rest/api/3/search" not in path:
            return None

        query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        candidates: list[tuple[str, set[str]]] = []

        if "/rest/api/3/search/jql" in path:
            candidates.append(("/rest/api/3/search", {"nextPageToken"}))
        candidates.append(("/rest/api/2/search", {"nextPageToken"}))

        for suffix, drop_params in candidates:
            candidate_path = path.replace("/rest/api/3/search/jql", suffix).replace("/rest/api/3/search", suffix)
            filtered_pairs = [(k, v) for (k, v) in query_pairs if k not in drop_params]
            candidate_query = urllib.parse.urlencode(filtered_pairs)
            candidate_url = urllib.parse.urlunsplit(
                (parsed.scheme, parsed.netloc, candidate_path, candidate_query, parsed.fragment)
            )
            try:
                status, body = request_json(candidate_url, route.method, headers, payload)
                return status, body, candidate_url
            except urllib.error.HTTPError:
                continue

        return None

    try:
        status, body = request_json(url, route.method, headers, payload)
        return status, body, url
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            fallback = try_search_fallback(url)
            if fallback is not None:
                return fallback
        raw = exc.read().decode("utf-8")
        parsed = json.loads(raw) if raw else None
        raise SystemExit(
            json.dumps(
                {
                    "entity": entity,
                    "action": action,
                    "endpoint": url,
                    "status": exc.code,
                    "response": parsed,
                },
                indent=2,
            )
        ) from exc


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def default_end_date(start_date: str) -> str:
    try:
        normalized = start_date.replace("Z", "+00:00")
        base = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SystemExit("Sprint start date must be a valid ISO timestamp.") from exc
    end = base + dt.timedelta(days=14)
    return end.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sprint_issue_route(path_template: str) -> Route:
    return Route("POST", path_template, True, True)


def fetch_sprint(base_url: str, headers: dict[str, str], sprint_id: str) -> tuple[str, dict[str, Any], str]:
    route = resolve_route("sprint", "get")
    endpoint = build_url(base_url, route, sprint_id, {})
    status, body = fetch_jira_json(endpoint, route.method, headers)
    return endpoint, body or {}, sprint_id


def fetch_sprint_issue_keys(base_url: str, headers: dict[str, str], sprint_id: str) -> set[str]:
    start_at = 0
    max_results = 50
    issue_keys: set[str] = set()

    while True:
        query = urllib.parse.urlencode({"startAt": start_at, "maxResults": max_results})
        endpoint = f"{base_url.rstrip('/')}/rest/agile/1.0/sprint/{urllib.parse.quote(sprint_id, safe='')}/issue?{query}"
        _, body = fetch_jira_json(endpoint, "GET", headers)
        payload = body or {}
        issues = payload.get("issues", [])
        for issue in issues:
            key = issue.get("key")
            if isinstance(key, str) and key:
                issue_keys.add(key)

        total = payload.get("total")
        if not isinstance(total, int):
            total = len(issue_keys)
        start_at += len(issues)
        if start_at >= total or not issues:
            break

    return issue_keys


def ensure_issues_belong_to_sprint(base_url: str, headers: dict[str, str], sprint_id: str, issue_keys: list[str]) -> None:
    sprint_issue_keys = fetch_sprint_issue_keys(base_url, headers, sprint_id)
    missing = [issue_key for issue_key in issue_keys if issue_key not in sprint_issue_keys]
    if missing:
        joined = ", ".join(missing)
        raise SystemExit(f"These issues are not currently in sprint {sprint_id}: {joined}")


def build_sprint_membership_payload(args: argparse.Namespace) -> dict[str, Any]:
    issues = parse_issue_keys(args.issue)
    if not issues:
        raise SystemExit("Sprint item operations require at least one --issue value.")
    if len(issues) > 50:
        raise SystemExit("Sprint item operations support at most 50 issues per request.")
    payload: dict[str, Any] = {"issues": issues}
    if args.rank_before_issue and args.rank_after_issue:
        raise SystemExit("Use only one of --rank-before-issue or --rank-after-issue.")
    if args.rank_before_issue:
        payload["rankBeforeIssue"] = args.rank_before_issue
    if args.rank_after_issue:
        payload["rankAfterIssue"] = args.rank_after_issue
    if args.rank_custom_field_id is not None:
        payload["rankCustomFieldId"] = args.rank_custom_field_id
    return payload


def build_sprint_transition_payload(
    action: str,
    sprint: dict[str, Any],
    *,
    start_date: str | None,
    end_date: str | None,
    goal: str | None,
) -> dict[str, Any]:
    state = str(sprint.get("state", "")).lower()
    if action == "start":
        if state != "future":
            raise SystemExit(f"Only future sprints can be started. Current sprint state is '{state or 'unknown'}'.")
        name = sprint.get("name")
        if not name:
            raise SystemExit("Sprint name is required before a sprint can be started.")
        chosen_start = start_date or sprint.get("startDate") or iso_now()
        chosen_end = end_date or sprint.get("endDate") or default_end_date(chosen_start)
        payload: dict[str, Any] = {
            "name": name,
            "state": "active",
            "startDate": chosen_start,
            "endDate": chosen_end,
        }
        chosen_goal = goal if goal is not None else sprint.get("goal")
        if chosen_goal is not None:
            payload["goal"] = chosen_goal
        return payload

    if state != "active":
        raise SystemExit(f"Only active sprints can be completed. Current sprint state is '{state or 'unknown'}'.")
    name = sprint.get("name")
    if not name:
        raise SystemExit("Sprint name is required before a sprint can be completed.")
    payload: dict[str, Any] = {
        "name": name,
        "state": "closed",
    }
    if sprint.get("startDate"):
        payload["startDate"] = sprint["startDate"]
    if sprint.get("endDate"):
        payload["endDate"] = sprint["endDate"]
    chosen_goal = goal if goal is not None else sprint.get("goal")
    if chosen_goal is not None:
        payload["goal"] = chosen_goal
    return payload


def handle_sprint_custom_action(
    args: argparse.Namespace,
    base_url: str,
    *,
    read_headers: dict[str, str],
    write_headers: dict[str, str],
) -> None:
    if not args.resource:
        raise SystemExit("This sprint action requires --resource")

    sprint_endpoint, sprint, target = fetch_sprint(base_url, read_headers, args.resource)
    sprint_state = str(sprint.get("state", "")).lower()

    if args.action == "add-items":
        if sprint_state not in {"future", "active"}:
            raise SystemExit(f"Issues can only be added to future or active sprints. Current sprint state is '{sprint_state or 'unknown'}'.")
        route = sprint_issue_route("/rest/agile/1.0/sprint/{resource}/issue")
        payload = build_sprint_membership_payload(args)
        endpoint = build_url(base_url, route, args.resource, {})
        if args.dry_run:
            emit_result(
                entity="sprint",
                action=args.action,
                target=target,
                endpoint=endpoint,
                dry_run=True,
                method=route.method,
                headers=write_headers,
                payload=payload,
                response_body={"sprint": sprint, "issueCount": len(payload["issues"])},
            )
            raise SystemExit(0)
        status, response_body = fetch_jira_json(endpoint, route.method, write_headers, payload)
        emit_result(
            entity="sprint",
            action=args.action,
            target=target,
            endpoint=endpoint,
            dry_run=False,
            method=route.method,
            headers=write_headers,
            payload=payload,
            response_status=status,
            response_body={"sprint": sprint, "issueCount": len(payload["issues"]), "result": response_body},
        )
        return

    if args.action == "remove-items":
        if sprint_state not in {"future", "active"}:
            raise SystemExit(f"Issues can only be removed from future or active sprints. Current sprint state is '{sprint_state or 'unknown'}'.")
        route = Route("POST", "/rest/agile/1.0/backlog/issue", False, True)
        payload = build_sprint_membership_payload(args)
        ensure_issues_belong_to_sprint(base_url, read_headers, args.resource, payload["issues"])
        endpoint = build_url(base_url, route, None, {})
        if args.dry_run:
            emit_result(
                entity="sprint",
                action=args.action,
                target=target,
                endpoint=endpoint,
                dry_run=True,
                method=route.method,
                headers=write_headers,
                payload=payload,
                response_body={
                    "sprint": sprint,
                    "issueCount": len(payload["issues"]),
                    "note": "This operation moves issues back to the backlog and removes them from future or active sprints.",
                },
            )
            raise SystemExit(0)
        status, response_body = fetch_jira_json(endpoint, route.method, write_headers, payload)
        emit_result(
            entity="sprint",
            action=args.action,
            target=target,
            endpoint=endpoint,
            dry_run=False,
            method=route.method,
            headers=write_headers,
            payload=payload,
            response_status=status,
            response_body={
                "sprint": sprint,
                "issueCount": len(payload["issues"]),
                "note": "Issues were moved to backlog; Jira removes them from future or active sprints with this operation.",
                "result": response_body,
            },
        )
        return

    mapped_action = "complete" if args.action in {"complete", "finish"} else "start"
    route = resolve_route("sprint", "update")
    payload = build_sprint_transition_payload(
        mapped_action,
        sprint,
        start_date=args.start_date,
        end_date=args.end_date,
        goal=args.goal,
    )
    endpoint = build_url(base_url, route, args.resource, {})
    if args.dry_run:
        emit_result(
            entity="sprint",
            action=args.action,
            target=target,
            endpoint=endpoint,
            dry_run=True,
            method=route.method,
            headers=write_headers,
            payload=payload,
            response_body={"sprint": sprint, "transition": mapped_action},
        )
        raise SystemExit(0)
    status, response_body = fetch_jira_json(endpoint, route.method, write_headers, payload)
    emit_result(
        entity="sprint",
        action=args.action,
        target=target,
        endpoint=endpoint,
        dry_run=False,
        method=route.method,
        headers=write_headers,
        payload=payload,
        response_status=status,
        response_body={"sprintBefore": sprint, "transition": mapped_action, "result": response_body},
    )


def prepare_custom_route_request(
    args: argparse.Namespace,
    *,
    base_url: str,
    read_headers: dict[str, str],
    route: Route,
    query: dict[str, str],
) -> tuple[Route, str, str, dict[str, str], Any | None, Any | None]:
    target = args.resource or "<new>"
    response_context: Any | None = None

    if args.entity == "transition" and args.action == "list":
        query = dict(query)
        query.setdefault("expand", "transitions.fields")
        endpoint = build_url(base_url, route, args.resource, query)
        return route, endpoint, target, query, None, response_context

    if args.entity == "transition" and args.action == "execute":
        list_route = resolve_route("transition", "list")
        list_endpoint = build_url(base_url, list_route, args.resource, {"expand": "transitions.fields"})
        _, body = fetch_jira_json(list_endpoint, list_route.method, read_headers)
        transitions = body.get("transitions", []) if isinstance(body, dict) else []
        payload = build_transition_execute_payload(args, transitions)
        endpoint = build_url(base_url, route, args.resource, {})
        response_context = {
            "availableTransitions": [
                {"id": item.get("id"), "name": item.get("name")}
                for item in transitions
                if isinstance(item, dict)
            ]
        }
        return route, endpoint, target, {}, payload, response_context

    if args.entity == "assignee":
        if args.action == "get":
            query = dict(query)
            query.setdefault("fields", "assignee")
            endpoint = build_url(base_url, route, args.resource, query)
            return route, endpoint, target, query, None, response_context
        payload = build_assignee_payload(args)
        endpoint = build_url(base_url, route, args.resource, {})
        return route, endpoint, target, {}, payload, response_context

    if args.entity == "issuelink":
        if args.action == "types":
            endpoint = build_url(base_url, route, None, query)
            return route, endpoint, target, query, None, response_context
        if args.action == "list":
            query = dict(query)
            query.setdefault("fields", "issuelinks")
            endpoint = build_url(base_url, route, args.resource, query)
            return route, endpoint, target, query, None, response_context
        if args.action == "create":
            payload = build_issue_link_payload(args)
            endpoint = build_url(base_url, route, None, {})
            target = f"{args.inward_issue}->{args.outward_issue}"
            return route, endpoint, target, {}, payload, response_context
        endpoint = build_url(base_url, route, args.resource, query)
        return route, endpoint, target, query, None, response_context

    if args.entity == "board":
        query = with_default_paging(query, args)
        endpoint = build_url(base_url, route, args.resource, query)
        return route, endpoint, target, query, None, response_context

    if args.entity == "comment":
        if args.action == "list":
            query = with_default_paging(query, args)
            endpoint = build_url(base_url, route, args.resource, query)
            return route, endpoint, target, query, None, response_context
        if args.action == "create":
            payload = build_comment_payload(args)
            endpoint = build_url(base_url, route, args.resource, {})
            return route, endpoint, target, {}, payload, response_context
        query = dict(query)
        if args.comment_id:
            query["commentId"] = args.comment_id
        endpoint = build_url(base_url, route, args.resource, query)
        return route, endpoint, target, query, None, response_context

    if args.entity == "search":
        query = build_search_query(args, query)
        target = args.jql or query.get("jql", "<jql>")
        endpoint = build_url(base_url, route, None, query)
        return route, endpoint, target, query, None, response_context

    if args.entity == "epic":
        if args.action == "issues":
            query = build_epic_search_query(args.resource, query, args)
            endpoint = build_url(base_url, route, args.resource, query)
            response_context = {
                "inspectionMode": "search_fallback",
                "searchJql": query.get("jql"),
                "searchFields": query.get("fields"),
            }
            search_route = resolve_route("search", "list")
            search_endpoint = build_url(base_url, search_route, None, query)
            return search_route, search_endpoint, target, query, None, response_context
        if args.action in {"set", "clear"}:
            payload = build_epic_issue_payload(args)
            endpoint = build_url(base_url, route, args.resource, {})
            target = args.resource or "<no-epic>"
            response_context = {"issueCount": len(payload["issues"])}
            return route, endpoint, target, {}, payload, response_context
        endpoint = build_url(base_url, route, args.resource, query)
        return route, endpoint, target, query, None, response_context

    if args.entity == "rank":
        payload = build_rank_payload(args)
        target = ",".join(payload["issues"])
        endpoint = build_url(base_url, route, None, {})
        return route, endpoint, target, {}, payload, response_context

    endpoint = build_url(base_url, route, args.resource, query)
    return route, endpoint, target, query, None, response_context


def main() -> None:
    load_dotenv_if_present()
    args = parse_args()
    enforce_guardrails(args)

    base_url = require_env("JIRA_BASE_URL")
    user = require_env("ATL_USER")
    token = require_env("ATL_TOKEN")
    read_headers = build_headers(user, token, False)
    write_headers = build_headers(user, token, True)

    if is_custom_sprint_action(args.entity, args.action):
        handle_sprint_custom_action(args, base_url, read_headers=read_headers, write_headers=write_headers)
        return

    route = resolve_route(args.entity, args.action)

    query = parse_query_pairs(args.query)
    payload: Any | None = None
    response_context: Any | None = None

    route, endpoint, target, query, custom_payload, response_context = prepare_custom_route_request(
        args,
        base_url=base_url,
        read_headers=read_headers,
        route=route,
        query=query,
    )
    payload = custom_payload if custom_payload is not None else parse_payload(args, route)
    if args.entity == "issue" and args.action in {"create", "update"}:
        payload = normalize_issue_rich_text_fields(payload)
    headers = build_headers(user, token, payload is not None)

    if args.dry_run:
        response_body = response_context if response_context is not None else None
        emit_result(
            entity=args.entity,
            action=args.action,
            target=target,
            endpoint=endpoint,
            dry_run=True,
            method=route.method,
            headers=headers,
            payload=payload,
            response_body=response_body,
        )
        raise SystemExit(0)

    status, response_body, effective_endpoint = send_request(
        entity=args.entity,
        action=args.action,
        url=endpoint,
        route=route,
        headers=headers,
        payload=payload,
    )
    if response_context is not None:
        if response_body is None:
            response_body = response_context
        elif isinstance(response_body, dict) and isinstance(response_context, dict):
            response_body = dict(response_body)
            response_body.update(response_context)
    if args.entity == "epic" and args.action == "issues" and isinstance(response_body, dict):
        filtered_issues = filter_epic_search_issues(target, response_body)
        response_body = dict(response_body)
        response_body["issues"] = filtered_issues
        response_body["total"] = len(filtered_issues)
        response_body["isLast"] = True
    emit_result(
        entity=args.entity,
        action=args.action,
        target=target,
        endpoint=effective_endpoint,
        dry_run=False,
        method=route.method,
        headers=headers,
        payload=payload,
        response_status=status,
        response_body=response_body,
    )


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, int):
            raise
        message, status, response = parse_exit_payload(str(code))
        emit_json(
            build_error_payload(
                tool="jira",
                command="jira-cli",
                message=message,
                status=status,
                response=response,
            )
        )
        raise SystemExit(1)
