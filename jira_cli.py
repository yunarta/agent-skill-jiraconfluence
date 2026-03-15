#!/usr/bin/env python3
"""Minimal Jira CRUD CLI with inspectable request mapping."""

from __future__ import annotations

import argparse
import base64
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


WRITE_ACTIONS = {"create", "update", "delete"}


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
}


def parse_args() -> argparse.Namespace:
    actions = sorted({action for entity_routes in ROUTES.values() for action in entity_routes})
    parser = argparse.ArgumentParser(description="Jira CRUD CLI")
    parser.add_argument("entity", choices=sorted(ROUTES))
    parser.add_argument("action", choices=actions)
    parser.add_argument("--resource", help="Issue key/id, project key/id, or sprint id")
    parser.add_argument("--payload", help="Inline JSON payload")
    parser.add_argument("--payload-file", help="Path to JSON payload file")
    parser.add_argument("--query", action="append", default=[], help="Extra query param in key=value form")
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
) -> tuple[int, Any | None]:
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(url=url, method=route.method, headers=headers, data=body)

    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else None
            return response.status, parsed
    except urllib.error.HTTPError as exc:
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


def main() -> None:
    load_dotenv_if_present()
    args = parse_args()
    route = resolve_route(args.entity, args.action)
    enforce_guardrails(args)

    base_url = require_env("JIRA_BASE_URL")
    user = require_env("ATL_USER")
    token = require_env("ATL_TOKEN")

    payload = parse_payload(args, route)
    query = parse_query_pairs(args.query)
    endpoint = build_url(base_url, route, args.resource, query)
    headers = build_headers(user, token, payload is not None)
    target = args.resource or "<new>"

    if args.dry_run:
        emit_result(
            entity=args.entity,
            action=args.action,
            target=target,
            endpoint=endpoint,
            dry_run=True,
            method=route.method,
            headers=headers,
            payload=payload,
        )
        raise SystemExit(0)

    status, response_body = send_request(
        entity=args.entity,
        action=args.action,
        url=endpoint,
        route=route,
        headers=headers,
        payload=payload,
    )
    emit_result(
        entity=args.entity,
        action=args.action,
        target=target,
        endpoint=endpoint,
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
