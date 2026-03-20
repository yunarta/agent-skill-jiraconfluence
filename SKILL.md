---
name: agentic-skill-jiraconfluence
description: Use when you need Jira execution and Confluence reporting from Codex, including Jira project, issue, sprint, metadata, field, and remote-link operations plus Confluence page and space publishing with caller-facing agentic output.
---

# Skill: agentic-skill-jiraconfluence

Use this skill when the task needs:
- Jira operational work
- Confluence reporting work
- Jira to Confluence or Confluence to Jira artifact linking

## What this skill covers

- Jira `project`, `issue`, `sprint`, `field`, `metadata`, and `remotelink` operations
- Confluence report validation, render preview, publish/update, and space provisioning
- caller-facing `agentic` output:
  - `summary`
  - `outcome`
  - `decision`
  - `confidence`
  - `anomalies`
  - `next_actions`

## What this skill does not claim

- native Jira project-level Confluence UI linking through a verified public API
- arbitrary Confluence macro coverage beyond the validated Jira-linked reporting path
- full Jira administration across classic-only schemes, workflows, or screens

## Required environment

### Jira

- `JIRA_BASE_URL`
- `ATL_USER`
- `ATL_TOKEN`

Optional (admin-gated operations only):
- `ATL_ADMIN_USER`
- `ATL_ADMIN_TOKEN`

### Confluence

- `CONFLUENCE_BASE_URL` or fallback `JIRA_BASE_URL/wiki`
- `CONFLUENCE_USER` or fallback `ATL_USER`
- `CONFLUENCE_TOKEN` or fallback `ATL_TOKEN`
- `CONFLUENCE_SPACE_KEY` or explicit `--space-key`

## Workflow

1. Choose the lane
- use `jira_cli.py` for Jira work
- use `confluence_cli.py` for Confluence work

2. Prefer safe inspection first
- use Jira reads or `--dry-run` before writes
- use `validate` or `render-preview` before publish when the report shape is new
- destructive Jira actions require explicit confirmation; issue deletion can be blocked by Jira permissions (HTTP 403)

3. Execute from the repo root
- `python3 jira_cli.py ...`
- `python3 confluence_cli.py ...`

4. Read the `agentic` output before continuing
- respect `outcome`
- respect `decision`
- stop on `double_check` unless the caller explicitly wants manual review

## References

- Entry README: `README.md`
- Docs index: `docs/README.md`
- Report contract: `references/report-document-v1.md`
