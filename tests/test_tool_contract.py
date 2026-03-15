from __future__ import annotations

import unittest

from _loader import load_module


tool_contract = load_module("tool_contract_module", "tool_contract.py")


class ToolContractTest(unittest.TestCase):
    def test_jira_dry_run_contains_review_then_proceed(self) -> None:
        payload = {
            "entity": "issue",
            "action": "create",
            "target": "<new>",
            "endpoint": "https://example.test/rest/api/3/issue",
            "method": "POST",
            "mode": "dry-run",
            "headers": {"Accept": "application/json"},
        }
        enriched = tool_contract.attach_agentic_contract("jira", payload)
        self.assertEqual(enriched["agentic"]["decision"], "review_then_proceed")
        self.assertEqual(enriched["agentic"]["outcome"], tool_contract.PARTIAL)

    def test_jira_multiple_remote_links_becomes_double_check(self) -> None:
        payload = {
            "entity": "remotelink",
            "action": "list",
            "target": "EXAMPLE-4",
            "endpoint": "https://example.test/rest/api/2/issue/EXAMPLE-4/remotelink",
            "method": "GET",
            "mode": "live",
            "status": 200,
            "response": [{"id": 1}, {"id": 2}],
            "headers": {"Accept": "application/json"},
        }
        enriched = tool_contract.attach_agentic_contract("jira", payload)
        self.assertEqual(enriched["agentic"]["decision"], "double_check")
        self.assertTrue(enriched["agentic"]["anomalies"])

    def test_confluence_publish_without_backlinks_recommends_follow_up(self) -> None:
        payload = {
            "command": "publish",
            "mode": "live",
            "space": {"key": "EXAMPLE"},
            "page": {"id": "786460", "title": "Demo", "representation": "atlas_doc_format"},
            "jira_remote_links": [],
        }
        enriched = tool_contract.attach_agentic_contract("confluence", payload)
        self.assertIn("link", enriched["agentic"]["next_actions"][0].lower())

    def test_jira_search_empty_becomes_double_check(self) -> None:
        payload = {
            "entity": "search",
            "action": "list",
            "target": "jql",
            "endpoint": "https://example.test/rest/api/3/search/jql",
            "method": "GET",
            "mode": "live",
            "status": 200,
            "response": {"issues": []},
            "headers": {"Accept": "application/json"},
        }
        enriched = tool_contract.attach_agentic_contract("jira", payload)
        self.assertEqual(enriched["agentic"]["decision"], "double_check")
        self.assertTrue(enriched["agentic"]["anomalies"])

    def test_jira_comment_create_summary_mentions_comment_id(self) -> None:
        payload = {
            "entity": "comment",
            "action": "create",
            "target": "EXAMPLE-1",
            "endpoint": "https://example.test/rest/api/3/issue/EXAMPLE-1/comment",
            "method": "POST",
            "mode": "live",
            "status": 201,
            "response": {"id": "10001"},
            "headers": {"Accept": "application/json"},
        }
        enriched = tool_contract.attach_agentic_contract("jira", payload)
        self.assertIn("10001", enriched["agentic"]["summary"])

    def test_jira_metadata_issue_types_is_not_flagged_empty(self) -> None:
        payload = {
            "entity": "metadata",
            "action": "list",
            "target": "EXAMPLE",
            "endpoint": "https://example.test/rest/api/3/issue/createmeta/EXAMPLE/issuetypes",
            "method": "GET",
            "mode": "live",
            "status": 200,
            "response": {"issueTypes": [{"id": "10000", "name": "Epic"}]},
            "headers": {"Accept": "application/json"},
        }
        enriched = tool_contract.attach_agentic_contract("jira", payload)
        self.assertEqual(enriched["agentic"]["decision"], "proceed")
        self.assertFalse(enriched["agentic"]["anomalies"])


if __name__ == "__main__":
    unittest.main()
