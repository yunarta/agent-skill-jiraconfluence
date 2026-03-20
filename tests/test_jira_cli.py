from __future__ import annotations

import unittest
from unittest import mock

from _loader import load_module


jira_cli = load_module("jira_cli_module", "jira_cli.py")


class JiraCliTest(unittest.TestCase):
    def test_sprint_custom_actions_exclude_ambiguous_stop_and_end(self) -> None:
        self.assertNotIn("stop", jira_cli.SPRINT_CUSTOM_ACTIONS)
        self.assertNotIn("end", jira_cli.SPRINT_CUSTOM_ACTIONS)
        self.assertIn("finish", jira_cli.SPRINT_CUSTOM_ACTIONS)

    def test_parse_issue_keys_supports_repeat_and_csv(self) -> None:
        keys = jira_cli.parse_issue_keys(["EXAMPLE-1, EXAMPLE-2", "EXAMPLE-2", "EXAMPLE-3"])
        self.assertEqual(keys, ["EXAMPLE-1", "EXAMPLE-2", "EXAMPLE-3"])

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

    def test_build_sprint_membership_payload_supports_ranking(self) -> None:
        args = jira_cli.argparse.Namespace(
            issue=["EXAMPLE-1", "EXAMPLE-2"],
            rank_before_issue="EXAMPLE-9",
            rank_after_issue=None,
            rank_custom_field_id=17,
        )
        payload = jira_cli.build_sprint_membership_payload(args)
        self.assertEqual(
            payload,
            {
                "issues": ["EXAMPLE-1", "EXAMPLE-2"],
                "rankBeforeIssue": "EXAMPLE-9",
                "rankCustomFieldId": 17,
            },
        )

    def test_build_sprint_transition_payload_starts_future_sprint(self) -> None:
        payload = jira_cli.build_sprint_transition_payload(
            "start",
            {"state": "future", "name": "Example Sprint"},
            start_date="2026-03-16T00:00:00.000Z",
            end_date="2026-03-30T00:00:00.000Z",
            goal="Sprint goal",
        )
        self.assertEqual(
            payload,
            {
                "name": "Example Sprint",
                "state": "active",
                "startDate": "2026-03-16T00:00:00.000Z",
                "endDate": "2026-03-30T00:00:00.000Z",
                "goal": "Sprint goal",
            },
        )

    def test_build_sprint_transition_payload_blocks_invalid_complete_state(self) -> None:
        with self.assertRaises(SystemExit):
            jira_cli.build_sprint_transition_payload(
                "complete",
                {"state": "future"},
                start_date=None,
                end_date=None,
                goal=None,
            )

    def test_ensure_issues_belong_to_sprint_blocks_foreign_issue(self) -> None:
        with mock.patch.object(jira_cli, "fetch_sprint_issue_keys", return_value={"EXAMPLE-1"}):
            with self.assertRaises(SystemExit) as exc:
                jira_cli.ensure_issues_belong_to_sprint(
                    "https://example.test",
                    {"Accept": "application/json"},
                    "42",
                    ["EXAMPLE-1", "EXAMPLE-2"],
                )
        self.assertIn("EXAMPLE-2", str(exc.exception))

    def test_build_transition_execute_payload_supports_name_lookup(self) -> None:
        args = jira_cli.argparse.Namespace(
            payload=None,
            payload_file=None,
            transition_id=None,
            transition_name="In Progress",
        )
        payload = jira_cli.build_transition_execute_payload(
            args,
            [
                {"id": "11", "name": "To Do"},
                {"id": "21", "name": "In Progress"},
            ],
        )
        self.assertEqual(payload, {"transition": {"id": "21"}})

    def test_build_transition_execute_payload_rejects_ambiguous_names(self) -> None:
        args = jira_cli.argparse.Namespace(
            payload=None,
            payload_file=None,
            transition_id=None,
            transition_name="Done",
        )
        with self.assertRaises(SystemExit):
            jira_cli.build_transition_execute_payload(
                args,
                [
                    {"id": "31", "name": "Done"},
                    {"id": "32", "name": "Done"},
                ],
            )

    def test_build_assignee_payload_supports_set_and_clear(self) -> None:
        set_args = jira_cli.argparse.Namespace(action="set", account_id="abc123")
        clear_args = jira_cli.argparse.Namespace(action="clear", account_id=None)
        self.assertEqual(jira_cli.build_assignee_payload(set_args), {"accountId": "abc123"})
        self.assertEqual(jira_cli.build_assignee_payload(clear_args), {"accountId": None})

    def test_build_issue_link_payload_requires_link_shape(self) -> None:
        args = jira_cli.argparse.Namespace(
            payload=None,
            payload_file=None,
            link_type="Relates",
            inward_issue="EXAMPLE-1",
            outward_issue="EXAMPLE-2",
        )
        payload = jira_cli.build_issue_link_payload(args)
        self.assertEqual(
            payload,
            {
                "type": {"name": "Relates"},
                "inwardIssue": {"key": "EXAMPLE-1"},
                "outwardIssue": {"key": "EXAMPLE-2"},
            },
        )

    def test_with_default_paging_applies_defaults(self) -> None:
        args = jira_cli.argparse.Namespace(start_at=None, max_results=None)
        self.assertEqual(
            jira_cli.with_default_paging({}, args),
            {"startAt": "0", "maxResults": "50"},
        )
        args = jira_cli.argparse.Namespace(start_at=10, max_results=5)
        self.assertEqual(
            jira_cli.with_default_paging({"projectKeyOrId": "EXAMPLE"}, args),
            {"projectKeyOrId": "EXAMPLE", "startAt": "10", "maxResults": "5"},
        )

    def test_parse_csv_values_supports_repeat_and_csv(self) -> None:
        values = jira_cli.parse_csv_values(["summary,status", "status", "assignee"])
        self.assertEqual(values, ["summary", "status", "assignee"])

    def test_build_comment_payload_wraps_plain_text_as_adf(self) -> None:
        args = jira_cli.argparse.Namespace(
            payload=None,
            payload_file=None,
            comment_body="Line one\n\nLine two",
        )
        payload = jira_cli.build_comment_payload(args)
        self.assertEqual(payload["body"]["type"], "doc")
        self.assertEqual(payload["body"]["version"], 1)
        self.assertEqual(len(payload["body"]["content"]), 3)

    def test_normalize_issue_rich_text_fields_wraps_plain_description(self) -> None:
        payload = {"fields": {"summary": "Example", "description": "Plain text description"}}
        normalized = jira_cli.normalize_issue_rich_text_fields(payload)
        self.assertEqual(normalized["fields"]["description"]["type"], "doc")
        self.assertEqual(normalized["fields"]["description"]["content"][0]["content"][0]["text"], "Plain text description")

    def test_normalize_issue_rich_text_fields_keeps_existing_adf(self) -> None:
        payload = {
            "fields": {
                "summary": "Example",
                "description": {"type": "doc", "version": 1, "content": []},
            }
        }
        normalized = jira_cli.normalize_issue_rich_text_fields(payload)
        self.assertEqual(normalized, payload)

    def test_build_search_query_applies_jql_fields_and_defaults(self) -> None:
        args = jira_cli.argparse.Namespace(
            jql="project = EXAMPLE ORDER BY created DESC",
            field=["summary,status", "assignee"],
            expand=["names"],
            max_results=None,
            next_page_token=None,
        )
        query = jira_cli.build_search_query(args, {})
        self.assertEqual(
            query,
            {
                "jql": "project = EXAMPLE ORDER BY created DESC",
                "fields": "summary,status,assignee",
                "expand": "names",
                "maxResults": "25",
            },
        )

    def test_build_search_query_requires_jql(self) -> None:
        args = jira_cli.argparse.Namespace(
            jql=None,
            field=[],
            expand=[],
            max_results=None,
            next_page_token=None,
        )
        with self.assertRaises(SystemExit):
            jira_cli.build_search_query(args, {})

    def test_build_epic_issue_payload_requires_bounded_issue_list(self) -> None:
        args = jira_cli.argparse.Namespace(
            payload=None,
            payload_file=None,
            issue=["EXAMPLE-1,EXAMPLE-2"],
        )
        self.assertEqual(jira_cli.build_epic_issue_payload(args), {"issues": ["EXAMPLE-1", "EXAMPLE-2"]})

    def test_build_epic_search_query_uses_parent_epic_fallback(self) -> None:
        args = jira_cli.argparse.Namespace(field=[], expand=[], max_results=None, next_page_token=None)
        query = jira_cli.build_epic_search_query("EXAMPLE-9", {}, args)
        self.assertEqual(query["jql"], "parentEpic = EXAMPLE-9")
        self.assertIn("parent", query["fields"])
        self.assertIn("customfield_10014", query["fields"])

    def test_filter_epic_search_issues_keeps_only_children(self) -> None:
        response = {
            "issues": [
                {"key": "EXAMPLE-9", "fields": {"issuetype": {"name": "Epic"}}},
                {"key": "EXAMPLE-1", "fields": {"parent": {"key": "EXAMPLE-9"}}},
                {"key": "EXAMPLE-2", "fields": {"customfield_10014": "EXAMPLE-9"}},
                {"key": "EXAMPLE-3", "fields": {"parent": {"key": "OTHER-1"}}},
            ]
        }
        filtered = jira_cli.filter_epic_search_issues("EXAMPLE-9", response)
        self.assertEqual([issue["key"] for issue in filtered], ["EXAMPLE-1", "EXAMPLE-2"])

    def test_build_rank_payload_requires_single_anchor_direction(self) -> None:
        args = jira_cli.argparse.Namespace(
            payload=None,
            payload_file=None,
            issue=["EXAMPLE-1"],
            rank_before_issue="EXAMPLE-9",
            rank_after_issue="EXAMPLE-10",
            rank_custom_field_id=None,
        )
        with self.assertRaises(SystemExit):
            jira_cli.build_rank_payload(args)

    def test_build_rank_payload_supports_after_anchor(self) -> None:
        args = jira_cli.argparse.Namespace(
            payload=None,
            payload_file=None,
            issue=["EXAMPLE-1", "EXAMPLE-2"],
            rank_before_issue=None,
            rank_after_issue="EXAMPLE-9",
            rank_custom_field_id=17,
        )
        self.assertEqual(
            jira_cli.build_rank_payload(args),
            {
                "issues": ["EXAMPLE-1", "EXAMPLE-2"],
                "rankAfterIssue": "EXAMPLE-9",
                "rankCustomFieldId": 17,
            },
        )

    def test_enforce_guardrails_requires_confirm_for_delete(self) -> None:
        args = jira_cli.argparse.Namespace(entity="issue", action="delete", confirm=False, admin_mode=False, admin_approve=False)
        with self.assertRaises(SystemExit):
            jira_cli.enforce_guardrails(args)

    def test_enforce_guardrails_requires_admin_approve_for_admin_mode(self) -> None:
        args = jira_cli.argparse.Namespace(entity="issue", action="get", confirm=True, admin_mode=True, admin_approve=False)
        with self.assertRaises(SystemExit):
            jira_cli.enforce_guardrails(args)

    def test_enforce_guardrails_requires_admin_mode_for_projectrole_mutation(self) -> None:
        args = jira_cli.argparse.Namespace(entity="projectrole", action="add-user", confirm=True, admin_mode=False, admin_approve=True)
        with self.assertRaises(SystemExit):
            jira_cli.enforce_guardrails(args)

    def test_prepare_custom_route_request_builds_projectrole_add_user_payload(self) -> None:
        args = jira_cli.argparse.Namespace(
            entity="projectrole",
            action="add-user",
            resource="EXAMPLE",
            role_id="10002",
            account_id="557058:example",
        )
        route = jira_cli.resolve_route("projectrole", "add-user")
        effective_route, endpoint, target, query, payload, response_context = jira_cli.prepare_custom_route_request(
            args,
            base_url="https://example.atlassian.net",
            read_headers={"Accept": "application/json"},
            route=route,
            query={},
        )
        self.assertEqual(effective_route.method, "POST")
        self.assertEqual(endpoint, "https://example.atlassian.net/rest/api/3/project/EXAMPLE/role/10002")
        self.assertEqual(target, "EXAMPLE/role/10002")
        self.assertEqual(query, {"roleId": "10002"})
        self.assertEqual(payload, {"user": ["557058:example"]})
        self.assertEqual(response_context, {"actorAccountId": "557058:example"})


if __name__ == "__main__":
    unittest.main()
