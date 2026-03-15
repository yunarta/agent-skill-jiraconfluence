# agentic-skill-jiraconfluence

`agentic-skill-jiraconfluence` is a Python bundle for Jira execution work and Confluence reporting work.

It covers:
- Jira `project`, `issue`, `sprint`, `field`, `metadata`, and `remotelink` operations
- Confluence report validation, preview, publish, and space provisioning
- Jira-aware report publishing with link-back behavior
- caller-facing `agentic` summaries, decisions, anomalies, and next actions

## Status

Current release status:
- validated for Jira operational CRUD on the supported surface
- validated for Confluence report publish/update
- validated for Jira issue backlinking to Confluence pages
- not claiming native Jira project-level Confluence UI linking
- not claiming arbitrary Confluence macro coverage

## Feature Matrix

| Area | Capability | Status |
| --- | --- | --- |
| Jira | Project operations | Supported |
| Jira | Issue operations | Supported |
| Jira | Sprint operations | Supported |
| Jira | Field and metadata inspection | Supported |
| Jira | Issue remote links | Supported |
| Confluence | Report validate | Supported |
| Confluence | Render preview | Supported |
| Confluence | Page publish/update | Supported |
| Confluence | Space create/get/list | Supported |
| Cross-linking | Jira issue -> Confluence page backlink | Supported |
| Cross-linking | Confluence page -> Jira-linked report content | Supported on validated path |
| Native UI integration | Jira project -> Confluence UI link | Manual / not claimed |

## Documentation

This bundle now follows a Diataxis-style documentation split.

- Tutorials:
  - [Publish your first report](docs/tutorials/publish-your-first-report.md)
- How-to guides:
  - [Run a safe Jira inspection](docs/how-to/run-a-safe-jira-inspection.md)
  - [Publish a report with Jira backlinks](docs/how-to/publish-a-report-with-jira-backlinks.md)
  - [Provision a Confluence project space](docs/how-to/provision-a-confluence-project-space.md)
- Explanation:
  - [Architecture and operating model](docs/explanation/architecture-and-operating-model.md)
- Reference:
  - [CLI reference](docs/reference/cli-reference.md)
  - [Environment and publish hygiene](docs/reference/environment-and-publish-hygiene.md)
  - [Release notes](docs/reference/release-notes.md)
  - [Report document contract](references/report-document-v1.md)

## Quick Start

1. Copy [`.env.example`](.env.example) into your local environment setup.
2. Install dependencies.
3. Validate or inspect before you write.
4. Publish or execute only after the dry-run path looks correct.

```bash
pip install -r agentic-skill-jiraconfluence/requirements.txt
python3 agentic-skill-jiraconfluence/jira_cli.py project get --resource EXAMPLE
python3 agentic-skill-jiraconfluence/confluence_cli.py validate \
  agentic-skill-jiraconfluence/samples/execution-sync-05.report.yaml
```

## Core Files

- `jira_cli.py`: Jira execution CLI
- `confluence_cli.py`: Confluence publishing CLI
- `tool_contract.py`: shared caller-facing response envelope
- `references/report-document-v1.md`: canonical report contract
- `samples/execution-sync-05.report.yaml`: sample report input

## Design Boundary

This bundle is optimized for a proven operational path:
- Jira for execution artifacts
- Confluence for reporting artifacts
- caller-facing decisions for orchestrating agents

It is not trying to be a complete Atlassian admin SDK.

## Verification

```bash
python3 -m py_compile \
  agentic-skill-jiraconfluence/tool_contract.py \
  agentic-skill-jiraconfluence/confluence_cli.py \
  agentic-skill-jiraconfluence/jira_cli.py
```

```bash
python3 -m unittest discover -s agentic-skill-jiraconfluence/tests -p 'test_*.py' -v
```
