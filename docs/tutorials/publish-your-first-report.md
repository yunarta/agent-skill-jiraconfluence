# Publish Your First Report

This tutorial walks through the smallest complete path:
- validate a local report
- preview it
- publish it to Confluence
- add Jira issue backlinks

By the end, you will have one Confluence page and one or more Jira issues linked back to it.

## Before you start

You need:
- Python 3
- dependencies installed from `agentic-skill-jiraconfluence/requirements.txt`
- Jira credentials:
  - `JIRA_BASE_URL`
  - `ATL_USER`
  - `ATL_TOKEN`
- Confluence credentials:
  - `CONFLUENCE_BASE_URL`
  - `CONFLUENCE_USER`
  - `CONFLUENCE_TOKEN`
- a target Confluence space key such as `EXAMPLE`

You can start from [`.env.example`](../../.env.example).

## Step 1: Validate the report input

Use the sample report first.

```bash
python3 agentic-skill-jiraconfluence/confluence_cli.py validate \
  agentic-skill-jiraconfluence/samples/execution-sync-05.report.yaml
```

Expected result:
- the command returns a structured JSON response
- the `agentic` section should indicate a usable outcome

## Step 2: Preview the rendered report

Render a preview before publishing.

```bash
python3 agentic-skill-jiraconfluence/confluence_cli.py render-preview \
  agentic-skill-jiraconfluence/samples/execution-sync-05.report.yaml \
  --format atlas_doc_format
```

Use this step to confirm that:
- the title is correct
- the report body looks reasonable
- Jira keys are detected where expected

## Step 3: Dry-run the publish

Do a publish dry-run before creating or updating a real page.

```bash
python3 agentic-skill-jiraconfluence/confluence_cli.py publish \
  agentic-skill-jiraconfluence/samples/execution-sync-05.report.yaml \
  --space-key EXAMPLE \
  --title "Example Sprint Report" \
  --link-jira EXAMPLE-3 \
  --link-jira EXAMPLE-4 \
  --dry-run
```

Expected result:
- `agentic.outcome` should be `PARTIAL`
- `agentic.decision` should tell you to review before proceeding

## Step 4: Publish the page

When the dry-run looks right, publish the page.

```bash
python3 agentic-skill-jiraconfluence/confluence_cli.py publish \
  agentic-skill-jiraconfluence/samples/execution-sync-05.report.yaml \
  --space-key EXAMPLE \
  --title "Example Sprint Report" \
  --link-jira EXAMPLE-3 \
  --link-jira EXAMPLE-4
```

Expected result:
- a page is created or updated in Confluence
- the response includes page identifiers and a caller-facing summary

## Step 5: Verify Jira backlinks

List remote links on one of the Jira issues.

```bash
python3 agentic-skill-jiraconfluence/jira_cli.py remotelink list --resource EXAMPLE-3
```

Expected result:
- the issue has a remote link pointing to the published Confluence page

## What you learned

You now have the basic reporting lane:
- local report input
- preview and validation
- Confluence publish
- Jira issue link-back

For task-oriented variants, use the guides under `docs/how-to/`.
