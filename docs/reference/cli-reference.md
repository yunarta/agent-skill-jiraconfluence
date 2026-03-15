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

Typical examples:

```bash
python3 agentic-skill-jiraconfluence/jira_cli.py project get --resource EXAMPLE
python3 agentic-skill-jiraconfluence/jira_cli.py issue get --resource EXAMPLE-3
python3 agentic-skill-jiraconfluence/jira_cli.py metadata list --project EXAMPLE
python3 agentic-skill-jiraconfluence/jira_cli.py remotelink list --resource EXAMPLE-3
```

## Confluence CLI

Entry point:

```bash
python3 agentic-skill-jiraconfluence/confluence_cli.py ...
```

Supported operation groups:
- `validate`
- `render-preview`
- `publish`
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
