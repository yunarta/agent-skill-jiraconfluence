# Publish A Report With Jira Backlinks

Use this guide when the report should show Jira-derived content and the related Jira issues must link back to the published Confluence page.

## Validate first

```bash
python3 agentic-skill-jiraconfluence/confluence_cli.py validate \
  agentic-skill-jiraconfluence/samples/execution-sync-05.report.yaml
```

## Preview the Jira-aware output

```bash
python3 agentic-skill-jiraconfluence/confluence_cli.py render-preview \
  agentic-skill-jiraconfluence/samples/execution-sync-05.report.yaml \
  --format atlas_doc_format
```

Use `atlas_doc_format` for Jira-linked report pages. This is the validated path for smart-link style output.

## Publish with explicit Jira links

```bash
python3 agentic-skill-jiraconfluence/confluence_cli.py publish \
  agentic-skill-jiraconfluence/samples/execution-sync-05.report.yaml \
  --space-key EXAMPLE \
  --title "Example Jira-Linked Report" \
  --link-jira EXAMPLE-3 \
  --link-jira EXAMPLE-4
```

This does two things:
- creates or updates the Confluence page
- creates or refreshes Jira remote links back to that page

## Confirm the backlink

```bash
python3 agentic-skill-jiraconfluence/jira_cli.py remotelink list --resource EXAMPLE-4
```

## If you only want to test

Use `--dry-run` on `publish`.

```bash
python3 agentic-skill-jiraconfluence/confluence_cli.py publish \
  agentic-skill-jiraconfluence/samples/execution-sync-05.report.yaml \
  --space-key EXAMPLE \
  --link-jira EXAMPLE-3 \
  --dry-run
```

You should expect a `PARTIAL` outcome. That is correct for a preview-only path.
