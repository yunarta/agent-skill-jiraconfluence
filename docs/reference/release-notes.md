# Release Notes

This page gives a short external-facing summary of what the bundle currently proves.

## Current Shape

`agentic-skill-jiraconfluence` is a publishable Python bundle for:
- Jira execution workflows
- Confluence reporting workflows
- Jira and Confluence artifact cross-linking on the validated path

## What Is Proven

- Jira project, issue, sprint, field, metadata, and remote-link operations
- Confluence report validation, preview, page publish, and space provisioning
- Jira issue backlinks to published Confluence pages
- caller-facing `agentic` output for orchestrators and smaller models

## What Is Explicitly Out Of Scope

- native Jira project-level Confluence UI linking through a verified public API
- arbitrary Confluence macro rendering beyond the validated Jira-linked path
- full Jira administration across all Atlassian scheme/workflow variants

## Notes For Publishers

Before publishing this folder externally:
- review placeholder examples
- confirm branding/naming you want to expose
- keep `.env` and tenant-specific exports out of git
