from __future__ import annotations

import argparse
import os
import unittest

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


if __name__ == "__main__":
    unittest.main()
