from __future__ import annotations

import argparse
import os
import unittest
from unittest import mock

from _loader import load_module


confluence_cli = load_module("confluence_cli_module", "confluence_cli.py")


class ConfluenceCliTest(unittest.TestCase):
    def test_resolve_page_representation_prefers_adf_for_upstream_jira(self) -> None:
        args = argparse.Namespace(representation="auto", link_jira=[], link_upstream_jira=False)
        report = {"traceability": {"upstream_jira_keys": ["EXAMPLE-3"]}}
        self.assertEqual(confluence_cli.resolve_page_representation(args, report), "atlas_doc_format")

    def test_render_atlas_doc_format_keeps_metadata_plain_text(self) -> None:
        original_base_url = os.environ.get("JIRA_BASE_URL")
        os.environ["JIRA_BASE_URL"] = "https://example.atlassian.net"
        report = {
            "title": "Demo",
            "report_id": "ARC-001-jira-crud-skill-SPR-002-sync",
            "arc_id": "ARC-001-jira-crud-skill",
            "sprint_id": "SPR-002",
            "stage": "Execution Sync",
            "status": "draft",
            "summary": {"executive": "Exec", "outcome": "Outcome"},
            "context": {"defaults_chosen": [], "blockers": []},
            "sections": [{"title": "Evidence", "markdown": "- `EXAMPLE-3` was linked"}],
            "traceability": {
                "source_path": "demo.md",
                "source_type": "local",
                "upstream_jira_keys": ["EXAMPLE-3"],
                "labels": [],
            },
        }
        try:
            doc = confluence_cli.render_atlas_doc_format(report)
            text_nodes = []
            inline_cards = []

            def walk(node):
                if isinstance(node, dict):
                    if node.get("type") == "text" and "text" in node:
                        text_nodes.append(node["text"])
                    if node.get("type") == "inlineCard":
                        inline_cards.append(node["attrs"]["url"])
                    for value in node.values():
                        walk(value)
                elif isinstance(node, list):
                    for item in node:
                        walk(item)

            walk(doc)
            self.assertIn("Arc: ARC-001-jira-crud-skill", text_nodes)
            self.assertIn("Sprint: SPR-002", text_nodes)
            self.assertIn("https://example.atlassian.net/browse/EXAMPLE-3", inline_cards)
            self.assertNotIn("https://example.atlassian.net/browse/ARC-001", inline_cards)
        finally:
            if original_base_url is None:
                os.environ.pop("JIRA_BASE_URL", None)
            else:
                os.environ["JIRA_BASE_URL"] = original_base_url

    def test_build_sprint_review_report_synthesizes_traceable_document(self) -> None:
        jira_config = confluence_cli.JiraConfig(
            base_url="https://example.atlassian.net",
            user="user@example.test",
            token="token",
        )

        def fake_jira_request(config, *, method, path, payload=None):
            self.assertEqual(config, jira_config)
            if path == "/rest/agile/1.0/sprint/42":
                return {
                    "id": 42,
                    "name": "Validation Sprint",
                    "state": "closed",
                    "goal": "Validate sprint reporting",
                    "startDate": "2026-03-01T00:00:00.000Z",
                    "endDate": "2026-03-14T00:00:00.000Z",
                    "completeDate": "2026-03-14T12:00:00.000Z",
                }
            if path.startswith("/rest/agile/1.0/sprint/42/issue"):
                return {
                    "issues": [
                        {
                            "key": "EXAMPLE-1",
                            "fields": {
                                "summary": "First item",
                                "status": {"name": "Done"},
                                "assignee": {"displayName": "Alice"},
                            },
                        },
                        {
                            "key": "EXAMPLE-2",
                            "fields": {
                                "summary": "Second item",
                                "status": {"name": "To Do"},
                            },
                        },
                    ],
                    "total": 2,
                }
            raise AssertionError(f"Unexpected Jira path: {path}")

        with mock.patch.object(confluence_cli, "jira_request", side_effect=fake_jira_request):
            report = confluence_cli.build_sprint_review_report(
                jira_config=jira_config,
                project_key="EXAMPLE",
                board_id="7",
                sprint_id="42",
            )

        self.assertEqual(report["report_type"], "sprint_review")
        self.assertEqual(report["sprint_id"], "42")
        self.assertEqual(report["traceability"]["upstream_jira_keys"], ["EXAMPLE-1", "EXAMPLE-2"])
        self.assertEqual(report["traceability"]["source_path"], "jira://board/7/sprint/42")
        self.assertIn("Validation Sprint", report["title"])
        self.assertEqual(report["sections"][1]["title"], "Status Breakdown")
        self.assertIn("Done: 1", report["sections"][1]["markdown"])
        self.assertIn("`EXAMPLE-1`", report["sections"][2]["markdown"])


if __name__ == "__main__":
    unittest.main()
