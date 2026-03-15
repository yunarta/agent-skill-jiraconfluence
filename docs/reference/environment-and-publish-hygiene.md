# Environment And Publish Hygiene

## Required Environment

### Jira

- `JIRA_BASE_URL`
- `ATL_USER`
- `ATL_TOKEN`

### Confluence

- `CONFLUENCE_BASE_URL`
  fallback: `JIRA_BASE_URL/wiki`
- `CONFLUENCE_USER`
  fallback: `ATL_USER`
- `CONFLUENCE_TOKEN`
  fallback: `ATL_TOKEN`
- `CONFLUENCE_SPACE_KEY`
  or pass `--space-key`

Start from [`.env.example`](../../.env.example).

## Publish Hygiene Rules

- Do not commit a real `.env`
- Do not commit exported responses that include secrets or tokens
- Replace tenant-specific project keys, hostnames, page titles, and identifiers in examples before publishing
- Keep generated Python caches out of git

This folder already includes a local [`.gitignore`](../../.gitignore).

## Sanitized Example Policy

Public examples in this bundle should use placeholders such as:
- `EXAMPLE`
- `EXAMPLE-3`
- `https://example.atlassian.net`

Avoid leaving:
- real workspace hostnames
- local absolute filesystem paths
- personal names unless intentionally public

## Safe Review Checklist

Before publishing the folder, check:
- `.env` is not staged
- examples use placeholders
- sample reports do not expose internal repo paths
- tests do not depend on a real tenant name
- README examples are generic
