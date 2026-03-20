#!/usr/bin/env python3
"""Confluence reporting CLI for validating, previewing, and publishing reports."""

from __future__ import annotations

import argparse
import base64
from collections import Counter
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tool_contract import attach_agentic_contract, build_error_payload, emit_json as contract_emit_json, parse_exit_payload

try:
    import yaml
except ImportError:  # pragma: no cover - exercised by runtime usage
    yaml = None


JIRA_KEY_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


@dataclass(frozen=True)
class ConfluenceConfig:
    base_url: str
    user: str
    token: str
    space_key: str | None = None


@dataclass(frozen=True)
class JiraConfig:
    base_url: str
    user: str
    token: str


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Confluence report publishing CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("validate", "render-preview", "publish"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("input", help="Path to local report (.md, .yaml, .yml)")
        subparser.add_argument("--title", help="Override page/report title")
        subparser.add_argument(
            "--format",
            choices=("atlas_doc_format", "storage", "json"),
            default="atlas_doc_format",
            help="Render-preview output format",
        )
        subparser.add_argument("--output", help="Write preview output to a file")

    publish = subparsers.choices["publish"]
    publish.add_argument("--space-key", help="Confluence space key; falls back to env")
    publish.add_argument("--parent-id", help="Optional parent page id")
    publish.add_argument("--page-id", help="Explicit page id to update")
    publish.add_argument("--status", choices=("current", "draft"), default="current")
    publish.add_argument("--message", default="Updated by agentic-skill-jiraconfluence")
    publish.add_argument(
        "--overwrite",
        action="store_true",
        help="When a page with the same title already exists, update it instead of failing the publish.",
    )
    publish.add_argument(
        "--representation",
        choices=("auto", "atlas_doc_format", "storage"),
        default="auto",
        help="Confluence page body representation to publish",
    )
    publish.add_argument("--link-jira", action="append", default=[], help="Jira issue key to backlink with a remote link")
    publish.add_argument(
        "--link-upstream-jira",
        action="store_true",
        help="Also backlink Jira keys found in report.traceability.upstream_jira_keys",
    )
    publish.add_argument("--dry-run", action="store_true", help="Print publish plan without sending")

    sprint_review = subparsers.add_parser("publish-sprint-review")
    sprint_review.add_argument("--board-id", required=True, help="Jira board id")
    sprint_review.add_argument("--sprint-id", required=True, help="Jira sprint id")
    sprint_review.add_argument("--project-key", required=True, help="Jira project key for traceability")
    sprint_review.add_argument("--space-key", help="Confluence space key; falls back to env")
    sprint_review.add_argument("--title", help="Override page/report title")
    sprint_review.add_argument("--parent-id", help="Optional parent page id")
    sprint_review.add_argument("--page-id", help="Explicit page id to update")
    sprint_review.add_argument("--status", choices=("current", "draft"), default="current")
    sprint_review.add_argument("--message", default="Updated by agentic-skill-jiraconfluence")
    sprint_review.add_argument(
        "--overwrite",
        action="store_true",
        help="When a page with the same title already exists, update it instead of failing the publish.",
    )
    sprint_review.add_argument(
        "--representation",
        choices=("auto", "atlas_doc_format", "storage"),
        default="auto",
        help="Confluence page body representation to publish",
    )
    sprint_review.add_argument("--link-jira", action="append", default=[], help="Additional Jira issue key to backlink")
    sprint_review.add_argument("--dry-run", action="store_true", help="Print publish plan without sending")

    spaces = subparsers.add_parser("space-list")
    spaces.add_argument("--format", choices=("json", "summary"), default="summary")

    space_get = subparsers.add_parser("space-get")
    space_get.add_argument("--space-key", required=True)

    space_create = subparsers.add_parser("space-create")
    space_create.add_argument("--space-key", required=True)
    space_create.add_argument("--space-name", required=True)
    space_create.add_argument("--description", default="")
    space_create.add_argument("--type", choices=("global", "personal"), default="global")
    space_create.add_argument("--project-key", help="Optional Jira project key to attach as metadata")
    space_create.add_argument("--project-url", help="Optional Jira project URL override")
    space_create.add_argument("--homepage-title", help="Optional project landing page title to publish after space creation")
    space_create.add_argument("--dry-run", action="store_true")

    space_link = subparsers.add_parser("space-link-project")
    space_link.add_argument("--space-key", required=True)
    space_link.add_argument("--project-key", required=True)
    space_link.add_argument("--project-url", help="Optional Jira project URL override")
    space_link.add_argument("--dry-run", action="store_true")

    return parser.parse_args()


def emit_json(payload: dict[str, Any]) -> None:
    contract_emit_json(attach_agentic_contract("confluence", payload))


def require_yaml() -> Any:
    if yaml is None:
        raise SystemExit("PyYAML is required. Install dependencies from agentic-skill-jiraconfluence/requirements.txt")
    return yaml


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "report"


def infer_report_id(source_path: Path, metadata: dict[str, str]) -> str:
    arc = metadata.get("Arc", "local")
    sprint = metadata.get("Sprint", "adhoc")
    stem = source_path.stem
    parts = [slugify(arc).upper(), slugify(sprint).upper(), slugify(stem).upper()]
    return "-".join(part for part in parts if part)


def parse_markdown_sections(lines: list[str]) -> tuple[str | None, dict[str, str], list[dict[str, str]]]:
    title: str | None = None
    metadata: dict[str, str] = {}
    sections: list[dict[str, str]] = []
    current_title: str | None = None
    current_lines: list[str] = []
    metadata_open = True

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        if title is None and line.startswith("# "):
            title = line[2:].strip()
            continue

        if line.startswith("## "):
            metadata_open = False
            if current_title is not None:
                sections.append({"title": current_title, "markdown": "\n".join(current_lines).strip()})
            current_title = line[3:].strip()
            current_lines = []
            continue

        if metadata_open and line.startswith("- ") and ":" in line:
            key, value = line[2:].split(":", 1)
            metadata[key.strip()] = value.strip()
            continue

        if current_title is not None:
            current_lines.append(line)

    if current_title is not None:
        sections.append({"title": current_title, "markdown": "\n".join(current_lines).strip()})

    return title, metadata, sections


def markdown_to_report_document(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    title, metadata, sections = parse_markdown_sections(lines)
    body_text = path.read_text(encoding="utf-8")
    related_jira_keys = sorted(set(JIRA_KEY_PATTERN.findall(body_text)))

    summary = {
        "executive": metadata.get("Progress") or metadata.get("Goal") or "Imported from local markdown report.",
        "outcome": metadata.get("Blockers", "No explicit outcome captured in the markdown header."),
    }
    context = {
        "goal": metadata.get("Goal"),
        "progress": metadata.get("Progress"),
        "blockers": [metadata["Blockers"]] if metadata.get("Blockers") else [],
        "decisions": [],
    }

    for section in sections:
        if section["title"].lower().startswith("outcome"):
            summary["outcome"] = section["markdown"] or summary["outcome"]
        if section["title"].lower().startswith("mapping"):
            context["decisions"].append("Mapping section preserved from source markdown report.")

    report = {
        "schema_version": "report.v1",
        "report_id": infer_report_id(path, metadata),
        "title": title or path.stem.replace("-", " ").title(),
        "report_type": slugify(metadata.get("Ceremony", path.stem)).replace("-", "_"),
        "arc_id": metadata.get("Arc"),
        "sprint_id": metadata.get("Sprint"),
        "stage": metadata.get("Ceremony"),
        "status": "draft",
        "summary": summary,
        "context": context,
        "sections": sections,
        "traceability": {
            "source_path": str(path.relative_to(Path.cwd())),
            "source_type": "local-markdown-report",
            "upstream_jira_keys": related_jira_keys,
            "confluence_page_id": None,
            "confluence_page_url": None,
            "labels": [
                slugify(metadata.get("Arc", "local-report")),
                slugify(metadata.get("Sprint", "adhoc")),
                slugify(metadata.get("Ceremony", "report")),
            ],
        },
        "publisher": {
            "render_target": "confluence",
            "renderer_version": "0.1.0",
            "publish_mode": "draft",
        },
    }
    return report


def yaml_to_report_document(path: Path) -> dict[str, Any]:
    loader = require_yaml()
    docs = list(loader.safe_load_all(path.read_text(encoding="utf-8")))
    if not docs:
        raise SystemExit(f"No YAML document found in {path}")
    if not isinstance(docs[0], dict):
        raise SystemExit(f"First YAML document in {path} must be a mapping")

    report = dict(docs[0])
    if len(docs) > 1:
        narrative_doc = docs[1]
        if isinstance(narrative_doc, str):
            report["narrative_markdown"] = narrative_doc
        elif isinstance(narrative_doc, dict):
            report.update(narrative_doc)
        else:
            raise SystemExit("Optional second YAML document must be a string or mapping")

    return report


def normalize_report(report: dict[str, Any], source_path: Path) -> dict[str, Any]:
    normalized = dict(report)
    normalized.setdefault("schema_version", "report.v1")
    normalized.setdefault("report_id", infer_report_id(source_path, {}))
    normalized.setdefault("title", source_path.stem.replace("-", " ").title())
    normalized.setdefault("report_type", "generic_report")
    normalized.setdefault("status", "draft")

    summary = normalized.get("summary") or {}
    if not isinstance(summary, dict):
        raise SystemExit("'summary' must be a mapping")
    summary.setdefault("executive", "Report imported into structured reporting flow.")
    summary.setdefault("outcome", "Outcome not yet captured.")
    normalized["summary"] = summary

    context = normalized.get("context") or {}
    if not isinstance(context, dict):
        raise SystemExit("'context' must be a mapping")
    context.setdefault("defaults_chosen", [])
    context.setdefault("blockers", [])
    normalized["context"] = context

    sections = normalized.get("sections") or []
    if not isinstance(sections, list):
        raise SystemExit("'sections' must be a list")
    normalized["sections"] = sections

    traceability = normalized.get("traceability") or {}
    if not isinstance(traceability, dict):
        raise SystemExit("'traceability' must be a mapping")
    traceability.setdefault("source_path", str(source_path.relative_to(Path.cwd())))
    traceability.setdefault("source_type", "local-structured-report")
    traceability.setdefault("upstream_jira_keys", [])
    traceability.setdefault("confluence_page_id", None)
    traceability.setdefault("confluence_page_url", None)
    traceability.setdefault("labels", [])
    normalized["traceability"] = traceability

    publisher = normalized.get("publisher") or {}
    if not isinstance(publisher, dict):
        raise SystemExit("'publisher' must be a mapping")
    publisher.setdefault("render_target", "confluence")
    publisher.setdefault("renderer_version", "0.1.0")
    publisher.setdefault("publish_mode", "draft")
    normalized["publisher"] = publisher

    if normalized["schema_version"] != "report.v1":
        raise SystemExit(f"Unsupported schema_version: {normalized['schema_version']}")

    if not normalized.get("title"):
        raise SystemExit("Report title is required")

    return normalized


def load_report(path_str: str) -> dict[str, Any]:
    path = Path(path_str).resolve()
    if not path.exists():
        raise SystemExit(f"Input file does not exist: {path}")

    if path.suffix.lower() in {".yaml", ".yml"}:
        report = yaml_to_report_document(path)
    elif path.suffix.lower() == ".md":
        report = markdown_to_report_document(path)
    else:
        raise SystemExit("Supported input extensions are .md, .yaml, and .yml")

    return normalize_report(report, path)


def render_list(items: list[Any]) -> str:
    if not items:
        return "<p>None.</p>"
    rendered = []
    for item in items:
        if isinstance(item, dict):
            rendered.append(f"<li><pre>{html.escape(json.dumps(item, indent=2, ensure_ascii=False))}</pre></li>")
        else:
            rendered.append(f"<li>{html.escape(str(item))}</li>")
    return "<ul>" + "".join(rendered) + "</ul>"


def make_storage_external_link(url: str, label: str) -> str:
    safe_url = html.escape(url, quote=True)
    safe_label = label.replace("]]>", "]]]]><![CDATA[>")
    return (
        "<ac:link>"
        f"<ri:url ri:value=\"{safe_url}\" />"
        f"<ac:plain-text-link-body><![CDATA[{safe_label}]]></ac:plain-text-link-body>"
        "</ac:link>"
    )


def get_jira_base_url() -> str | None:
    return os.environ.get("JIRA_BASE_URL")


def build_jira_issue_url(issue_key: str) -> str | None:
    jira_base = get_jira_base_url()
    if not jira_base:
        return None
    return jira_base.rstrip("/") + "/browse/" + urllib.parse.quote(issue_key, safe="")


def render_inline_text(value: str) -> str:
    parts: list[str] = []
    last_end = 0
    for match in JIRA_KEY_PATTERN.finditer(value):
        parts.append(html.escape(value[last_end:match.start()]))
        issue_key = match.group(0)
        issue_url = build_jira_issue_url(issue_key)
        if issue_url:
            parts.append(make_storage_external_link(issue_url, issue_key))
        else:
            parts.append(html.escape(issue_key))
        last_end = match.end()
    parts.append(html.escape(value[last_end:]))
    return "".join(parts)


def render_sections(sections: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for section in sections:
        title = html.escape(str(section.get("title", "Section")))
        markdown = str(section.get("markdown", "")).strip()
        chunks.append(f"<h2>{title}</h2>")
        if markdown:
            paragraphs = [p.strip() for p in markdown.split("\n\n") if p.strip()]
            for paragraph in paragraphs:
                if paragraph.startswith("- "):
                    items = [f"<li>{render_inline_text(line[2:].strip())}</li>" for line in paragraph.splitlines() if line.startswith("- ")]
                    chunks.append("<ul>" + "".join(items) + "</ul>")
                else:
                    chunks.append(f"<p>{render_inline_text(paragraph)}</p>")
    return "".join(chunks)


def render_storage(report: dict[str, Any]) -> str:
    summary = report["summary"]
    context = report["context"]
    traceability = report["traceability"]

    parts = [
        f"<h1>{html.escape(report['title'])}</h1>",
        "<table><tbody>",
        f"<tr><th>Report ID</th><td>{html.escape(str(report['report_id']))}</td></tr>",
        f"<tr><th>Arc</th><td>{html.escape(str(report.get('arc_id') or ''))}</td></tr>",
        f"<tr><th>Sprint</th><td>{html.escape(str(report.get('sprint_id') or ''))}</td></tr>",
        f"<tr><th>Stage</th><td>{html.escape(str(report.get('stage') or ''))}</td></tr>",
        f"<tr><th>Status</th><td>{html.escape(str(report.get('status') or 'draft'))}</td></tr>",
        "</tbody></table>",
        "<h2>Summary</h2>",
        f"<p>{html.escape(str(summary.get('executive', '')))}</p>",
        f"<p>{html.escape(str(summary.get('outcome', '')))}</p>",
        "<h2>Context</h2>",
        f"<h3>Defaults Chosen</h3>{render_list(context.get('defaults_chosen', []))}",
        f"<h3>Blockers</h3>{render_list(context.get('blockers', []))}",
    ]

    for key in ("decisions", "open_questions", "risks", "next_actions", "artifacts"):
        if key in report:
            label = key.replace("_", " ").title()
            parts.append(f"<h2>{label}</h2>{render_list(report.get(key, []))}")

    if report.get("sections"):
        parts.append(render_sections(report["sections"]))

    if report.get("narrative_markdown"):
        parts.extend(
            [
                "<h2>Narrative</h2>",
                f"<pre>{render_inline_text(str(report['narrative_markdown']))}</pre>",
            ]
        )

    upstream_jira_keys = traceability.get("upstream_jira_keys", [])
    if upstream_jira_keys:
        linked_keys = []
        for issue_key in upstream_jira_keys:
            issue_url = build_jira_issue_url(str(issue_key))
            if issue_url:
                linked_keys.append(f"<li>{make_storage_external_link(issue_url, str(issue_key))}</li>")
            else:
                linked_keys.append(f"<li>{html.escape(str(issue_key))}</li>")
        parts.extend(["<h2>Linked Jira Artifacts</h2>", "<ul>" + "".join(linked_keys) + "</ul>"])

    parts.extend(
        [
            "<h2>Traceability</h2>",
            "<table><tbody>",
            f"<tr><th>Source Path</th><td>{html.escape(str(traceability.get('source_path') or ''))}</td></tr>",
            f"<tr><th>Source Type</th><td>{html.escape(str(traceability.get('source_type') or ''))}</td></tr>",
            f"<tr><th>Jira Keys</th><td>{html.escape(', '.join(traceability.get('upstream_jira_keys', [])))}</td></tr>",
            f"<tr><th>Labels</th><td>{html.escape(', '.join(traceability.get('labels', [])))}</td></tr>",
            "</tbody></table>",
        ]
    )

    return "".join(parts)


def make_adf_text_node(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    return {"type": "text", "text": text}


def render_inline_adf(value: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    last_end = 0
    for match in JIRA_KEY_PATTERN.finditer(value):
        before = value[last_end:match.start()]
        if before:
            nodes.append({"type": "text", "text": before})
        issue_key = match.group(0)
        issue_url = build_jira_issue_url(issue_key)
        if issue_url:
            nodes.append({"type": "inlineCard", "attrs": {"url": issue_url}})
        else:
            nodes.append({"type": "text", "text": issue_key})
        last_end = match.end()
    tail = value[last_end:]
    if tail:
        nodes.append({"type": "text", "text": tail})
    return nodes or [{"type": "text", "text": ""}]


def make_adf_paragraph(text: str, *, smart_links: bool = True) -> dict[str, Any]:
    content = render_inline_adf(text) if smart_links else [{"type": "text", "text": text}]
    return {"type": "paragraph", "content": content}


def make_adf_heading(level: int, text: str) -> dict[str, Any]:
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": [{"type": "text", "text": text}],
    }


def make_adf_bullet_list(items: list[Any], *, smart_links: bool = True) -> dict[str, Any]:
    content = []
    for item in items:
        if isinstance(item, dict):
            paragraph = {
                "type": "paragraph",
                "content": [{"type": "text", "text": json.dumps(item, indent=2, ensure_ascii=False)}],
            }
        else:
            paragraph = make_adf_paragraph(str(item), smart_links=smart_links)
        content.append({"type": "listItem", "content": [paragraph]})
    return {"type": "bulletList", "content": content}


def make_adf_paragraphs_from_markdown(markdown: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    paragraphs = [p.strip() for p in markdown.split("\n\n") if p.strip()]
    for paragraph in paragraphs:
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if lines and all(line.startswith("- ") for line in lines):
            blocks.append(make_adf_bullet_list([line[2:].strip() for line in lines]))
        else:
            text = "\n".join(lines) if lines else paragraph
            blocks.append(make_adf_paragraph(text))
    return blocks


def render_atlas_doc_format(report: dict[str, Any]) -> dict[str, Any]:
    summary = report["summary"]
    context = report["context"]
    traceability = report["traceability"]

    content: list[dict[str, Any]] = [
        make_adf_heading(1, str(report["title"])),
        make_adf_bullet_list(
            [
                f"Report ID: {report['report_id']}",
                f"Arc: {report.get('arc_id') or ''}",
                f"Sprint: {report.get('sprint_id') or ''}",
                f"Stage: {report.get('stage') or ''}",
                f"Status: {report.get('status') or 'draft'}",
            ],
            smart_links=False,
        ),
        make_adf_heading(2, "Summary"),
        make_adf_paragraph(str(summary.get("executive", ""))),
        make_adf_paragraph(str(summary.get("outcome", ""))),
        make_adf_heading(2, "Context"),
        make_adf_heading(3, "Defaults Chosen"),
        make_adf_bullet_list(context.get("defaults_chosen", []) or ["None."]),
        make_adf_heading(3, "Blockers"),
        make_adf_bullet_list(context.get("blockers", []) or ["None."]),
    ]

    for key in ("decisions", "open_questions", "risks", "next_actions", "artifacts"):
        if key in report:
            label = key.replace("_", " ").title()
            content.append(make_adf_heading(2, label))
            content.append(make_adf_bullet_list(report.get(key, []) or ["None."]))

    for section in report.get("sections", []):
        content.append(make_adf_heading(2, str(section.get("title", "Section"))))
        markdown = str(section.get("markdown", "")).strip()
        if markdown:
            content.extend(make_adf_paragraphs_from_markdown(markdown))

    if report.get("narrative_markdown"):
        content.append(make_adf_heading(2, "Narrative"))
        content.extend(make_adf_paragraphs_from_markdown(str(report["narrative_markdown"])))

    upstream_jira_keys = traceability.get("upstream_jira_keys", [])
    if upstream_jira_keys:
        content.append(make_adf_heading(2, "Linked Jira Artifacts"))
        content.append(make_adf_bullet_list([str(issue_key) for issue_key in upstream_jira_keys]))

    content.extend(
        [
            make_adf_heading(2, "Traceability"),
            make_adf_bullet_list(
                [
                    f"Source Path: {traceability.get('source_path') or ''}",
                    f"Source Type: {traceability.get('source_type') or ''}",
                    f"Jira Keys: {', '.join(traceability.get('upstream_jira_keys', []))}",
                    f"Labels: {', '.join(traceability.get('labels', []))}",
                ],
                smart_links=False,
            ),
        ]
    )

    return {
        "type": "doc",
        "version": 1,
        "content": [node for node in content if node],
    }


def resolve_page_representation(args: argparse.Namespace, report: dict[str, Any]) -> str:
    if args.representation != "auto":
        return args.representation
    jira_keys = list(args.link_jira)
    if args.link_upstream_jira:
        jira_keys.extend(str(key) for key in report.get("traceability", {}).get("upstream_jira_keys", []))
    if jira_keys or report.get("traceability", {}).get("upstream_jira_keys"):
        return "atlas_doc_format"
    return "storage"


def write_output(text: str, output_path: str | None) -> None:
    if output_path:
        Path(output_path).write_text(text, encoding="utf-8")
        return
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")


def confluence_request(
    config: ConfluenceConfig,
    *,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    raw_auth = base64.b64encode(f"{config.user}:{config.token}".encode("utf-8")).decode("ascii")
    url = f"{config.base_url.rstrip('/')}{path}"
    data = None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Basic {raw_auth}",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url=url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        body = json.loads(raw) if raw else None
        raise SystemExit(json.dumps({"status": exc.code, "path": path, "response": body}, indent=2)) from exc


def resolve_confluence_config(space_key_override: str | None) -> ConfluenceConfig:
    base_url = os.environ.get("CONFLUENCE_BASE_URL")
    if not base_url:
        jira_base = os.environ.get("JIRA_BASE_URL")
        if jira_base:
            base_url = jira_base.rstrip("/") + "/wiki"
    user = os.environ.get("CONFLUENCE_USER") or os.environ.get("ATL_USER")
    token = os.environ.get("CONFLUENCE_TOKEN") or os.environ.get("ATL_TOKEN")
    space_key = space_key_override or os.environ.get("CONFLUENCE_SPACE_KEY")

    missing = [name for name, value in (("base_url", base_url), ("user", user), ("token", token), ("space_key", space_key)) if not value]
    if missing:
        raise SystemExit("Missing Confluence configuration: " + ", ".join(missing))

    return ConfluenceConfig(base_url=base_url, user=user, token=token, space_key=space_key)


def resolve_jira_config() -> JiraConfig:
    base_url = os.environ.get("JIRA_BASE_URL")
    user = os.environ.get("ATL_USER")
    token = os.environ.get("ATL_TOKEN")
    missing = [name for name, value in (("JIRA_BASE_URL", base_url), ("ATL_USER", user), ("ATL_TOKEN", token)) if not value]
    if missing:
        raise SystemExit("Missing Jira configuration: " + ", ".join(missing))
    return JiraConfig(base_url=base_url, user=user, token=token)


def fetch_all_jira_issues(config: JiraConfig, path: str, *, fields: list[str], max_results: int = 50) -> list[dict[str, Any]]:
    start_at = 0
    issues: list[dict[str, Any]] = []
    encoded_fields = urllib.parse.quote(",".join(fields), safe=",")
    while True:
        separator = "&" if "?" in path else "?"
        response = jira_request(
            config,
            method="GET",
            path=f"{path}{separator}startAt={start_at}&maxResults={max_results}&fields={encoded_fields}",
        )
        if not isinstance(response, dict):
            break
        batch = response.get("issues", [])
        if not isinstance(batch, list) or not batch:
            break
        issues.extend(item for item in batch if isinstance(item, dict))
        total = response.get("total")
        if not isinstance(total, int):
            total = len(issues)
        start_at += len(batch)
        if start_at >= total:
            break
    return issues


def build_issue_line(issue: dict[str, Any]) -> str:
    key = str(issue.get("key") or "<unknown>")
    fields = issue.get("fields", {})
    if not isinstance(fields, dict):
        fields = {}
    summary = str(fields.get("summary") or "")
    status = fields.get("status", {})
    status_name = status.get("name") if isinstance(status, dict) else None
    assignee = fields.get("assignee", {})
    assignee_name = assignee.get("displayName") if isinstance(assignee, dict) else None
    parts = [f"`{key}`"]
    if summary:
        parts.append(summary)
    if status_name:
        parts.append(f"status: {status_name}")
    if assignee_name:
        parts.append(f"assignee: {assignee_name}")
    return " - ".join(parts)


def build_status_breakdown_lines(issues: list[dict[str, Any]]) -> list[str]:
    counter: Counter[str] = Counter()
    for issue in issues:
        fields = issue.get("fields", {})
        if not isinstance(fields, dict):
            continue
        status = fields.get("status", {})
        status_name = status.get("name") if isinstance(status, dict) else None
        counter[status_name or "Unknown"] += 1
    return [f"{status}: {count}" for status, count in sorted(counter.items())]


def build_sprint_review_report(
    *,
    jira_config: JiraConfig,
    project_key: str,
    board_id: str,
    sprint_id: str,
    title_override: str | None = None,
) -> dict[str, Any]:
    sprint = jira_request(jira_config, method="GET", path=f"/rest/agile/1.0/sprint/{urllib.parse.quote(sprint_id, safe='')}")
    if not isinstance(sprint, dict):
        raise SystemExit(f"Could not load Jira sprint {sprint_id}.")
    issues = fetch_all_jira_issues(
        jira_config,
        f"/rest/agile/1.0/sprint/{urllib.parse.quote(sprint_id, safe='')}/issue",
        fields=["summary", "status", "assignee", "issuetype", "parent", "priority"],
    )
    issue_keys = [str(issue.get("key")) for issue in issues if issue.get("key")]
    status_lines = build_status_breakdown_lines(issues)
    sprint_name = str(sprint.get("name") or f"Sprint {sprint_id}")
    sprint_goal = str(sprint.get("goal") or "No sprint goal was recorded in Jira.")
    sprint_state = str(sprint.get("state") or "unknown")
    start_date = str(sprint.get("startDate") or "")
    end_date = str(sprint.get("endDate") or "")
    complete_date = str(sprint.get("completeDate") or "")

    snapshot_lines = [
        f"Project: {project_key}",
        f"Board: {board_id}",
        f"Sprint: {sprint_name}",
        f"State: {sprint_state}",
        f"Goal: {sprint_goal}",
    ]
    if start_date:
        snapshot_lines.append(f"Start Date: {start_date}")
    if end_date:
        snapshot_lines.append(f"End Date: {end_date}")
    if complete_date:
        snapshot_lines.append(f"Complete Date: {complete_date}")

    report = {
        "schema_version": "report.v1",
        "report_id": f"{project_key}-SPRINT-{sprint_id}-REVIEW",
        "title": title_override or f"{project_key} Sprint Review - {sprint_name}",
        "report_type": "sprint_review",
        "arc_id": None,
        "sprint_id": str(sprint_id),
        "stage": "Validation & Review",
        "status": "draft",
        "summary": {
            "executive": f"Jira sprint review for {sprint_name} on project {project_key}.",
            "outcome": f"Sprint {sprint_name} is currently {sprint_state} with {len(issues)} issues captured for review.",
        },
        "context": {
            "goal": sprint_goal,
            "defaults_chosen": [
                "Report was synthesized directly from Jira sprint and issue state.",
                "Status breakdown and item list were generated from the sprint issue window.",
            ],
            "blockers": [],
            "decisions": [],
        },
        "sections": [
            {"title": "Sprint Snapshot", "markdown": "\n".join(f"- {line}" for line in snapshot_lines)},
            {"title": "Status Breakdown", "markdown": "\n".join(f"- {line}" for line in (status_lines or ["No issues found."]))},
            {"title": "Sprint Items", "markdown": "\n".join(f"- {build_issue_line(issue)}" for issue in issues) or "- No issues found."},
        ],
        "traceability": {
            "source_path": f"jira://board/{board_id}/sprint/{sprint_id}",
            "source_type": "jira-sprint-review",
            "upstream_jira_keys": issue_keys,
            "confluence_page_id": None,
            "confluence_page_url": None,
            "labels": [slugify(project_key), "sprint-review", slugify(sprint_name)],
        },
        "publisher": {
            "render_target": "confluence",
            "renderer_version": "0.1.0",
            "publish_mode": "draft",
        },
        "artifacts": [
            {"type": "jira_board", "id": str(board_id)},
            {"type": "jira_sprint", "id": str(sprint_id), "name": sprint_name},
        ],
        "next_actions": [
            "Review the status mix and unresolved work before closing the sprint narrative.",
            "Confirm linked Jira issues still represent the intended sprint review scope.",
        ],
    }
    return normalize_report(report, Path.cwd() / f"{project_key.lower()}-sprint-{sprint_id}-review.yaml")


def jira_request(
    config: JiraConfig,
    *,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    raw_auth = base64.b64encode(f"{config.user}:{config.token}".encode("utf-8")).decode("ascii")
    url = f"{config.base_url.rstrip('/')}{path}"
    data = None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Basic {raw_auth}",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url=url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        body = json.loads(raw) if raw else None
        raise SystemExit(json.dumps({"status": exc.code, "path": path, "response": body}, indent=2)) from exc


def find_system_confluence_applink(jira_config: JiraConfig) -> dict[str, Any] | None:
    response = jira_request(jira_config, method="GET", path="/rest/applinks/3.0/applinks")
    if not isinstance(response, list):
        return None
    for applink in response:
        if applink.get("type") == "confluence" and applink.get("system"):
            return applink
    for applink in response:
        if applink.get("type") == "confluence":
            return applink
    return None


def list_spaces(config: ConfluenceConfig) -> list[dict[str, Any]]:
    response = confluence_request(config, method="GET", path="/api/v2/spaces?limit=250")
    return response.get("results", []) if isinstance(response, dict) else []


def get_space(config: ConfluenceConfig) -> dict[str, Any]:
    if not config.space_key:
        raise SystemExit("Confluence space key is required for this action")
    results = list_spaces(config)
    for space in results:
        if space.get("key") == config.space_key or space.get("currentActiveAlias") == config.space_key:
            return space
    raise SystemExit(f"Confluence space not found for key: {config.space_key}")


def build_project_url(project_key: str, project_url: str | None) -> str:
    if project_url:
        return project_url
    jira_base = os.environ.get("JIRA_BASE_URL")
    if not jira_base:
        raise SystemExit("Missing JIRA_BASE_URL and no --project-url was provided")
    return jira_base.rstrip("/") + f"/jira/software/projects/{project_key}"


def get_space_properties(config: ConfluenceConfig, space_id: str) -> list[dict[str, Any]]:
    response = confluence_request(config, method="GET", path=f"/api/v2/spaces/{space_id}/properties?limit=100")
    return response.get("results", []) if isinstance(response, dict) else []


def upsert_space_property(
    config: ConfluenceConfig,
    *,
    space_id: str,
    key: str,
    value: dict[str, Any],
) -> dict[str, Any]:
    properties = get_space_properties(config, space_id)
    for prop in properties:
        if prop.get("key") == key:
            payload = {
                "key": key,
                "value": value,
                "version": {
                    "number": int(prop["version"]["number"]) + 1,
                    "message": "Updated by agentic-skill-jiraconfluence",
                },
            }
            return confluence_request(
                config,
                method="PUT",
                path=f"/api/v2/spaces/{space_id}/properties/{prop['id']}",
                payload=payload,
            )
    return confluence_request(
        config,
        method="POST",
        path=f"/api/v2/spaces/{space_id}/properties",
        payload={"key": key, "value": value},
    )


def render_project_homepage(project_key: str, project_url: str) -> str:
    return (
        f"<h1>{html.escape(project_key)} Project Space</h1>"
        "<p>This Confluence space is managed as the reporting surface for the linked Jira project.</p>"
        "<table><tbody>"
        f"<tr><th>Jira Project Key</th><td>{html.escape(project_key)}</td></tr>"
        f"<tr><th>Jira Project URL</th><td><a href=\"{html.escape(project_url)}\">{html.escape(project_url)}</a></td></tr>"
        "</tbody></table>"
        "<h2>Operating Contract</h2>"
        "<ul>"
        "<li>Jira is the execution surface.</li>"
        "<li>Confluence is the reporting surface.</li>"
        "<li>Local report artifacts are promoted here after validation and rendering.</li>"
        "</ul>"
    )


def find_page_by_title_v2(
    config: ConfluenceConfig,
    space_id: str,
    title: str,
    *,
    status: str = "current",
) -> dict[str, Any] | None:
    title_q = urllib.parse.quote(title, safe="")
    response = confluence_request(
        config,
        method="GET",
        path=f"/api/v2/spaces/{space_id}/pages?limit=25&status={urllib.parse.quote(status, safe='')}&title={title_q}&body-format=storage",
    )
    results = response.get("results", []) if isinstance(response, dict) else []
    for page in results:
        if page.get("title") == title:
            return page
    return None


def find_page_by_title_v1(
    config: ConfluenceConfig,
    space_key: str,
    title: str,
    *,
    status: str = "current",
) -> dict[str, Any] | None:
    params = urllib.parse.urlencode(
        {
            "spaceKey": space_key,
            "title": title,
            "status": status,
            "expand": "version",
        }
    )
    response = confluence_request(config, method="GET", path=f"/rest/api/content?{params}")
    results = response.get("results", []) if isinstance(response, dict) else []
    for item in results:
        if item.get("type") == "page" and item.get("title") == title:
            return item
    return None


def find_page_by_title(
    config: ConfluenceConfig,
    *,
    space_id: str,
    space_key: str,
    title: str,
    include_drafts: bool = False,
) -> dict[str, Any] | None:
    page = find_page_by_title_v1(config, space_key, title, status="current")
    if not page and include_drafts:
        page = find_page_by_title_v1(config, space_key, title, status="draft")
    if page:
        return page

    page = find_page_by_title_v2(config, space_id, title, status="current")
    if not page and include_drafts:
        page = find_page_by_title_v2(config, space_id, title, status="draft")
    return page


def ensure_page_version(config: ConfluenceConfig, page: dict[str, Any]) -> dict[str, Any]:
    version = page.get("version")
    if isinstance(version, dict) and isinstance(version.get("number"), int):
        return page
    page_id = page.get("id")
    if not page_id:
        return page
    hydrated = confluence_request(config, method="GET", path=f"/api/v2/pages/{page_id}")
    if isinstance(hydrated, dict):
        hydrated_version = hydrated.get("version")
        if isinstance(hydrated_version, dict) and isinstance(hydrated_version.get("number"), int):
            return hydrated
    hydrated_v1 = confluence_request(config, method="GET", path=f"/rest/api/content/{page_id}?expand=version")
    if isinstance(hydrated_v1, dict):
        hydrated_version = hydrated_v1.get("version")
        if isinstance(hydrated_version, dict) and isinstance(hydrated_version.get("number"), int):
            return hydrated_v1
    return page


def is_confluence_title_conflict(status: int | None, response: Any | None) -> bool:
    if status != 400 or not isinstance(response, dict):
        return False
    title = str(response.get("title") or "").lower()
    detail = str(response.get("detail") or "").lower()
    return "title already exists" in title or "same title" in detail


def publish_report(args: argparse.Namespace, report: dict[str, Any]) -> None:
    config = resolve_confluence_config(args.space_key)
    page_title = args.title or report["title"]
    representation = resolve_page_representation(args, report)
    if representation == "atlas_doc_format":
        body_value = json.dumps(render_atlas_doc_format(report), ensure_ascii=False)
    else:
        body_value = render_storage(report)
    space = get_space(config)
    existing_page = None

    if args.page_id:
        existing_page = confluence_request(config, method="GET", path=f"/api/v2/pages/{args.page_id}")
    else:
        existing_page = find_page_by_title(
            config,
            space_id=str(space["id"]),
            space_key=config.space_key,
            title=page_title,
            include_drafts=bool(args.overwrite),
        )
    if existing_page and isinstance(existing_page, dict):
        existing_page = ensure_page_version(config, existing_page)

    if args.dry_run:
        emit_json(
            {
                "command": "publish",
                "mode": "dry-run",
                "space": {"key": config.space_key, "id": space["id"], "name": space["name"]},
                "target_title": page_title,
                "target_page_id": existing_page.get("id") if existing_page else None,
                "action": "update" if existing_page else "create",
                "representation": representation,
                "body_preview": body_value[:1200],
                "jira_remote_link_targets": sorted(
                    set(args.link_jira + ([str(key) for key in report.get("traceability", {}).get("upstream_jira_keys", [])] if args.link_upstream_jira else []))
                ),
            }
        )
        return

    payload: dict[str, Any] = {
        "status": args.status,
        "title": page_title,
        "body": {
            "representation": representation,
            "value": body_value,
        },
    }

    if existing_page:
        current_version = existing_page.get("version", {}).get("number") if isinstance(existing_page, dict) else None
        if not isinstance(current_version, int):
            raise SystemExit(f"Confluence page {existing_page.get('id', '<unknown>')} is missing version metadata required for update.")
        update_payload = dict(payload)
        update_payload["id"] = existing_page["id"]
        update_payload["version"] = {
            "number": current_version + 1,
            "message": args.message,
        }
        response = confluence_request(
            config,
            method="PUT",
            path=f"/api/v2/pages/{existing_page['id']}",
            payload=update_payload,
        )
    else:
        payload["spaceId"] = str(space["id"])
        if args.parent_id:
            payload["parentId"] = str(args.parent_id)
        try:
            response = confluence_request(config, method="POST", path="/api/v2/pages", payload=payload)
        except SystemExit as exc:
            code = exc.code
            if isinstance(code, int) or not args.overwrite:
                raise
            _, status, create_response = parse_exit_payload(str(code))
            if not is_confluence_title_conflict(status, create_response):
                raise
            existing_page = find_page_by_title(
                config,
                space_id=str(space["id"]),
                space_key=config.space_key,
                title=page_title,
                include_drafts=True,
            )
            if not existing_page:
                raise SystemExit(
                    json.dumps(
                        {
                            "message": "Publish failed: Confluence returned a title conflict but the page could not be resolved for update.",
                            "status": status,
                            "response": create_response,
                        },
                        indent=2,
                    )
                ) from exc
            existing_page = ensure_page_version(config, existing_page)
            current_version = existing_page.get("version", {}).get("number") if isinstance(existing_page, dict) else None
            if not isinstance(current_version, int):
                raise SystemExit(f"Confluence page {existing_page.get('id', '<unknown>')} is missing version metadata required for update.") from exc
            update_payload = dict(payload)
            update_payload.pop("spaceId", None)
            update_payload.pop("parentId", None)
            update_payload["id"] = existing_page["id"]
            update_payload["version"] = {
                "number": current_version + 1,
                "message": args.message,
            }
            response = confluence_request(
                config,
                method="PUT",
                path=f"/api/v2/pages/{existing_page['id']}",
                payload=update_payload,
            )

    page_url = config.base_url.rstrip("/") + response.get("_links", {}).get("webui", "")
    jira_link_keys = list(args.link_jira)
    if args.link_upstream_jira:
        jira_link_keys.extend(str(key) for key in report.get("traceability", {}).get("upstream_jira_keys", []))
    jira_link_keys = sorted(set(key for key in jira_link_keys if key))

    remote_links: list[dict[str, Any]] = []
    if jira_link_keys:
        jira_config = resolve_jira_config()
        remote_links = sync_jira_remote_links(
            jira_config=jira_config,
            issue_keys=jira_link_keys,
            page_id=str(response.get("id")),
            page_title=str(response.get("title") or page_title),
            page_url=page_url,
        )

    emit_json(
        {
            "command": "publish",
            "mode": "live",
            "space": {"key": config.space_key, "id": space["id"], "name": space["name"]},
            "page": {
                "id": response.get("id"),
                "title": response.get("title"),
                "status": response.get("status"),
                "version": response.get("version", {}).get("number"),
                "webui": response.get("_links", {}).get("webui"),
                "representation": representation,
            },
            "jira_remote_links": remote_links,
        }
    )


def command_publish_sprint_review(args: argparse.Namespace) -> None:
    jira_config = resolve_jira_config()
    report = build_sprint_review_report(
        jira_config=jira_config,
        project_key=args.project_key,
        board_id=args.board_id,
        sprint_id=args.sprint_id,
        title_override=args.title,
    )
    args.link_upstream_jira = True
    publish_report(args, report)


def sync_jira_remote_links(
    *,
    jira_config: JiraConfig,
    issue_keys: list[str],
    page_id: str,
    page_title: str,
    page_url: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    applink = find_system_confluence_applink(jira_config)
    applink_id = applink.get("id") if applink else None
    if applink_id:
        global_id = f"appId={applink_id}&pageId={page_id}"
        application_name = str(applink.get("name") or "System Confluence")
        relationship = "Wiki Page"
    else:
        global_id = f"system={jira_config.base_url.rstrip('/')}&pageId={page_id}"
        application_name = "Confluence"
        relationship = "documents"
    payload = {
        "globalId": global_id,
        "application": {
            "type": "com.atlassian.confluence",
            "name": application_name,
        },
        "relationship": relationship,
        "object": {
            "url": page_url,
            "title": page_title,
            "summary": "Published by agentic-skill-jiraconfluence",
            "icon": {
                "title": "Confluence",
                "url16x16": config_favicon_url(jira_config.base_url),
            },
        },
    }
    for issue_key in issue_keys:
        response = jira_request(
            jira_config,
            method="POST",
            path=f"/rest/api/2/issue/{urllib.parse.quote(issue_key, safe='')}/remotelink",
            payload=payload,
        )
        results.append(
            {
                "issue_key": issue_key,
                "remote_link_id": response.get("id") if isinstance(response, dict) else None,
                "global_id": global_id,
                "page_url": page_url,
                "applink_id": applink_id,
            }
        )
    return results


def config_favicon_url(jira_base_url: str) -> str:
    return jira_base_url.rstrip("/") + "/favicon.ico"


def command_space_list(args: argparse.Namespace) -> None:
    config = resolve_confluence_config(os.environ.get("CONFLUENCE_SPACE_KEY") or "~unused")
    spaces = list_spaces(config)
    if args.format == "json":
        emit_json({"command": "space-list", "count": len(spaces), "spaces": spaces})
        return
    emit_json(
        {
            "command": "space-list",
            "count": len(spaces),
            "spaces": [
                {
                    "id": space.get("id"),
                    "key": space.get("key"),
                    "name": space.get("name"),
                    "type": space.get("type"),
                    "status": space.get("status"),
                }
                for space in spaces
            ],
        }
    )


def command_space_get(args: argparse.Namespace) -> None:
    config = resolve_confluence_config(args.space_key)
    space = get_space(config)
    properties = get_space_properties(config, str(space["id"]))
    emit_json(
        {
            "command": "space-get",
            "space": space,
            "properties": properties,
        }
    )


def command_space_create(args: argparse.Namespace) -> None:
    config = resolve_confluence_config(args.space_key)
    existing = None
    try:
        existing = get_space(config)
    except SystemExit:
        existing = None

    project_url = build_project_url(args.project_key, args.project_url) if args.project_key else None
    description_text = args.description.strip()
    if args.project_key:
        project_line = f"Linked Jira project: {args.project_key}"
        if project_url:
            project_line += f" ({project_url})"
        description_text = "\n".join(part for part in [description_text, project_line] if part)

    if args.dry_run:
        emit_json(
            {
                "command": "space-create",
                "mode": "dry-run",
                "space_key": args.space_key,
                "space_name": args.space_name,
                "space_type": args.type,
                "action": "reuse" if existing else "create",
                "project_link": {
                    "project_key": args.project_key,
                    "project_url": project_url,
                }
                if args.project_key
                else None,
            }
        )
        return

    if existing is None:
        payload: dict[str, Any] = {
            "key": args.space_key,
            "name": args.space_name,
            "description": {
                "value": description_text,
                "representation": "plain",
            },
        }
        if args.type == "personal":
            payload["createPrivateSpace"] = True
        space = confluence_request(config, method="POST", path="/api/v2/spaces", payload=payload)
        action = "created"
    else:
        space = existing
        action = "reused"

    link_property = None
    homepage = None
    if args.project_key:
        link_value = {
            "project_key": args.project_key,
            "project_url": project_url,
            "link_type": "metadata",
            "linked_atlassian_product": "jira",
        }
        link_property = upsert_space_property(
            config,
            space_id=str(space["id"]),
            key="openclaw.project_link",
            value=link_value,
        )
        if args.homepage_title:
            payload = {
                "status": "current",
                "title": args.homepage_title,
                "spaceId": str(space["id"]),
                "body": {
                    "representation": "storage",
                    "value": render_project_homepage(args.project_key, project_url),
                },
            }
            existing_page = find_page_by_title(config, str(space["id"]), args.homepage_title)
            if existing_page:
                payload["id"] = existing_page["id"]
                payload["version"] = {
                    "number": int(existing_page["version"]["number"]) + 1,
                    "message": "Updated project landing page",
                }
                homepage = confluence_request(
                    config,
                    method="PUT",
                    path=f"/api/v2/pages/{existing_page['id']}",
                    payload=payload,
                )
            else:
                homepage = confluence_request(config, method="POST", path="/api/v2/pages", payload=payload)

    emit_json(
        {
            "command": "space-create",
            "mode": "live",
            "action": action,
            "space": {
                "id": space.get("id"),
                "key": space.get("key"),
                "name": space.get("name"),
                "type": space.get("type"),
                "webui": space.get("_links", {}).get("webui"),
            },
            "project_link_property": link_property,
            "homepage": homepage,
        }
    )


def command_space_link_project(args: argparse.Namespace) -> None:
    config = resolve_confluence_config(args.space_key)
    space = get_space(config)
    project_url = build_project_url(args.project_key, args.project_url)
    link_value = {
        "project_key": args.project_key,
        "project_url": project_url,
        "link_type": "metadata",
        "linked_atlassian_product": "jira",
    }

    if args.dry_run:
        emit_json(
            {
                "command": "space-link-project",
                "mode": "dry-run",
                "space": {"id": space.get("id"), "key": space.get("key"), "name": space.get("name")},
                "property": {"key": "openclaw.project_link", "value": link_value},
            }
        )
        return

    prop = upsert_space_property(
        config,
        space_id=str(space["id"]),
        key="openclaw.project_link",
        value=link_value,
    )
    emit_json(
        {
            "command": "space-link-project",
            "mode": "live",
            "space": {"id": space.get("id"), "key": space.get("key"), "name": space.get("name")},
            "property": prop,
        }
    )


def main() -> None:
    load_dotenv_if_present()
    args = parse_args()

    if args.command == "space-list":
        command_space_list(args)
        return

    if args.command == "space-get":
        command_space_get(args)
        return

    if args.command == "space-create":
        command_space_create(args)
        return

    if args.command == "space-link-project":
        command_space_link_project(args)
        return

    if args.command == "publish-sprint-review":
        command_publish_sprint_review(args)
        return

    report = load_report(args.input)
    if args.title:
        report["title"] = args.title

    if args.command == "validate":
        emit_json(
            {
                "command": "validate",
                "status": "ok",
                "schema_version": report["schema_version"],
                "report_id": report["report_id"],
                "title": report["title"],
                "report_type": report["report_type"],
                "traceability": report["traceability"],
            }
        )
        return

    if args.command == "render-preview":
        if args.format == "json":
            text = json.dumps(report, indent=2, ensure_ascii=False)
        elif args.format == "atlas_doc_format":
            text = json.dumps(render_atlas_doc_format(report), indent=2, ensure_ascii=False)
        else:
            text = render_storage(report)
        write_output(text, args.output)
        return

    if args.command == "publish":
        publish_report(args, report)
        return

    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, int):
            raise
        message, status, response = parse_exit_payload(str(code))
        contract_emit_json(
            build_error_payload(
                tool="confluence",
                command="confluence-cli",
                message=message,
                status=status,
                response=response,
            )
        )
        raise SystemExit(1)
