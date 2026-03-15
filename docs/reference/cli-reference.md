# CLI Reference

This page is a concise reference for the executable surface in `agentic-skill-jiraconfluence/`.

## Jira CLI

Entry point:

```bash
python3 agentic-skill-jiraconfluence/jira_cli.py ...
```

Supported entity groups:
- `project`
- `issue`
- `sprint`
- `field`
- `metadata`
- `remotelink`
- `transition`
- `assignee`
- `issuelink`
- `board`
- `comment`
- `search`
- `epic`
- `rank`

Typical examples:

```bash
python3 agentic-skill-jiraconfluence/jira_cli.py project get --resource EXAMPLE
python3 agentic-skill-jiraconfluence/jira_cli.py issue get --resource EXAMPLE-3
python3 agentic-skill-jiraconfluence/jira_cli.py sprint add-items --resource 42 --issue EXAMPLE-3 --issue EXAMPLE-4
python3 agentic-skill-jiraconfluence/jira_cli.py sprint remove-items --resource 42 --issue EXAMPLE-3
python3 agentic-skill-jiraconfluence/jira_cli.py sprint start --resource 42 --start-date 2026-03-16T00:00:00.000Z --end-date 2026-03-30T00:00:00.000Z
python3 agentic-skill-jiraconfluence/jira_cli.py sprint complete --resource 42
python3 agentic-skill-jiraconfluence/jira_cli.py transition list --resource EXAMPLE-3
python3 agentic-skill-jiraconfluence/jira_cli.py transition execute --resource EXAMPLE-3 --transition-name "In Progress"
python3 agentic-skill-jiraconfluence/jira_cli.py assignee set --resource EXAMPLE-3 --account-id 557058:example
python3 agentic-skill-jiraconfluence/jira_cli.py assignee clear --resource EXAMPLE-3
python3 agentic-skill-jiraconfluence/jira_cli.py issuelink create --link-type Relates --inward-issue EXAMPLE-3 --outward-issue EXAMPLE-4
python3 agentic-skill-jiraconfluence/jira_cli.py issuelink list --resource EXAMPLE-3
python3 agentic-skill-jiraconfluence/jira_cli.py comment create --resource EXAMPLE-3 --comment-body "Validation note"
python3 agentic-skill-jiraconfluence/jira_cli.py comment list --resource EXAMPLE-3
python3 agentic-skill-jiraconfluence/jira_cli.py search list --jql "project = EXAMPLE ORDER BY created DESC" --field summary --field status
python3 agentic-skill-jiraconfluence/jira_cli.py epic issues --resource EXAMPLE-1
python3 agentic-skill-jiraconfluence/jira_cli.py epic set --resource EXAMPLE-1 --issue EXAMPLE-3 --issue EXAMPLE-4
python3 agentic-skill-jiraconfluence/jira_cli.py rank execute --issue EXAMPLE-3 --rank-before-issue EXAMPLE-4
python3 agentic-skill-jiraconfluence/jira_cli.py board list --query projectKeyOrId=EXAMPLE
python3 agentic-skill-jiraconfluence/jira_cli.py board backlog --resource 7 --query projectKeyOrId=EXAMPLE
python3 agentic-skill-jiraconfluence/jira_cli.py issue update --resource EXAMPLE-3 --payload '{"fields":{"description":"Plain text description"}}'
python3 agentic-skill-jiraconfluence/jira_cli.py metadata list --resource EXAMPLE
python3 agentic-skill-jiraconfluence/jira_cli.py remotelink list --resource EXAMPLE-3
```

Sprint-specific high-intent actions:
- `sprint add-items`
- `sprint remove-items`
- `sprint start`
- `sprint complete`
- alias for completion: `sprint finish`

Workflow execution helpers:
- `transition list`
- `transition execute`
- `assignee get`
- `assignee set`
- `assignee clear`
- `issuelink types`
- `issuelink list`
- `issuelink create`
- `issuelink delete`
- `board list`
- `board issues`
- `board backlog`

Search and coordination helpers:
- `search list`
- `comment list`
- `comment create`
- `comment delete`
- `epic get`
- `epic issues`
- `epic set`
- `epic clear`
- `rank execute`

Rich-text and hierarchy notes:
- `issue create` and `issue update` normalize plain string `fields.description` into Jira ADF before write
- `epic issues` uses a search-backed fallback on the validated team-managed path and may return `PARTIAL` with `double_check` guidance when Jira hierarchy inspection remains bounded

## Confluence CLI

Entry point:

```bash
python3 agentic-skill-jiraconfluence/confluence_cli.py ...
```

Supported operation groups:
- `validate`
- `render-preview`
- `publish`
- `publish-sprint-review`
- `space-list`
- `space-get`
- `space-create`
- `space-link-project`

Typical examples:

```bash
python3 agentic-skill-jiraconfluence/confluence_cli.py validate \
  agentic-skill-jiraconfluence/samples/execution-sync-05.report.yaml

python3 agentic-skill-jiraconfluence/confluence_cli.py publish \
  agentic-skill-jiraconfluence/samples/execution-sync-05.report.yaml \
  --space-key EXAMPLE \
  --title "Example Report"

python3 agentic-skill-jiraconfluence/confluence_cli.py publish-sprint-review \
  --project-key EXAMPLE \
  --board-id 7 \
  --sprint-id 42 \
  --space-key OCPI4 \
  --title "Example Sprint Review"
```

## Response Contract

Commands emit JSON output with two layers:
- transport payload
- `agentic` caller-facing envelope

The `agentic` envelope includes:
- `summary`
- `outcome`
- `decision`
- `confidence`
- `anomalies`
- `next_actions`

## Outcome Semantics

- `SUCCESS`: valid and complete for the requested path
- `PARTIAL`: useful but follow-up is still required
- `BLOCKED`: cannot proceed safely

## Decision Semantics

Common decisions include:
- `proceed`
- `review_then_proceed`
- `double_check`
- `stop`
