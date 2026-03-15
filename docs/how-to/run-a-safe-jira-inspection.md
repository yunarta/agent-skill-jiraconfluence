# Run A Safe Jira Inspection

Use this guide when you want to inspect Jira state without changing anything.

## Inspect a project

```bash
python3 agentic-skill-jiraconfluence/jira_cli.py project get --resource EXAMPLE
```

Use this to confirm:
- the project exists
- the key is correct
- the tool can authenticate successfully

## Inspect issue creation metadata

```bash
python3 agentic-skill-jiraconfluence/jira_cli.py metadata list --project EXAMPLE
```

Use this to see:
- available issue types
- which issue types are valid in the project

## Inspect fields for a specific issue type

```bash
python3 agentic-skill-jiraconfluence/jira_cli.py metadata get \
  --project EXAMPLE \
  --issue-type Story
```

Use this before issue creation when:
- the project has field requirements you do not fully trust
- you need to confirm which fields are writable

## Inspect remote links on an issue

```bash
python3 agentic-skill-jiraconfluence/jira_cli.py remotelink list --resource EXAMPLE-3
```

Use this to verify whether:
- the issue already links to Confluence
- duplicate backlink creation should be avoided

## Read the caller-facing contract

Every command emits an `agentic` envelope. Pay attention to:
- `outcome`
- `decision`
- `anomalies`
- `next_actions`

Treat this as the operational answer, not just the raw payload.
