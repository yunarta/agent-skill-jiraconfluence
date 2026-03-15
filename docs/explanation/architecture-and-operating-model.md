# Architecture And Operating Model

`agentic-skill-jiraconfluence` exists to separate two lanes that often get mixed together:
- Jira as the execution system
- Confluence as the reporting system

## Why this bundle exists

The bundle provides a thin operational layer over Atlassian APIs, but it does not stop at transport. It also emits caller-facing decisions so an orchestrating agent can decide whether to proceed, review, or double-check.

This matters because raw API success is not enough for an agentic workflow.

## Two-lane model

### Jira lane

The Jira lane is for operational artifacts:
- projects
- issues
- sprints
- fields
- metadata
- remote links

This lane is handled by `jira_cli.py`.

### Confluence lane

The Confluence lane is for reporting artifacts:
- report validation
- render preview
- page publish/update
- space provisioning

This lane is handled by `confluence_cli.py`.

## Why the tool emits an agentic envelope

The bundle is designed for callers that need judgment signals, not just response bodies.

Each command can emit:
- `summary`
- `outcome`
- `decision`
- `confidence`
- `anomalies`
- `next_actions`

This helps the caller distinguish:
- safe success
- partial preview
- blocked execution
- suspicious or ambiguous results

## Why Jira backlinks use remote links

The validated link-back path is Jira remote links, not issue description mutation.

That choice is deliberate:
- it is reversible
- it keeps report URLs out of user-facing issue prose
- it aligns better with artifact traceability

## Why Confluence report pages prefer ADF for Jira-linked content

Jira-linked report content should not be treated as escaped text.

The validated report path uses `atlas_doc_format` for Jira-linked content so the page stores structured link objects rather than plain HTML approximations.

## What this bundle does not claim

This bundle does not claim:
- native Jira project-level Confluence UI linking through a verified public API
- arbitrary Confluence macro coverage
- full Jira administration beyond the validated surface

Those limits are intentional. The bundle is optimized for the working path that has already been proven.
