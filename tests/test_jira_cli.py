from __future__ import annotations

import unittest

from _loader import load_module


jira_cli = load_module("jira_cli_module", "jira_cli.py")


class JiraCliTest(unittest.TestCase):
    def test_build_url_requires_required_query_keys(self) -> None:
        route = jira_cli.ROUTES["metadata"]["get"]
        with self.assertRaises(SystemExit):
            jira_cli.build_url("https://example.test", route, "EXAMPLE", {})

    def test_build_url_encodes_resource_and_query(self) -> None:
        route = jira_cli.ROUTES["remotelink"]["delete"]
        url = jira_cli.build_url(
            "https://example.test",
            route,
            "EXAMPLE-4",
            {"linkId": "10006", "expand": "details"},
        )
        self.assertEqual(
            url,
            "https://example.test/rest/api/2/issue/EXAMPLE-4/remotelink/10006?expand=details",
        )


if __name__ == "__main__":
    unittest.main()
