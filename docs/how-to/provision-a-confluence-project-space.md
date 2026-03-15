# Provision A Confluence Project Space

Use this guide when you need a Confluence space for a Jira project and want an inspectable metadata link between them.

## Create or reuse a space

```bash
python3 agentic-skill-jiraconfluence/confluence_cli.py space-create \
  --space-key EXAMPLE \
  --space-name "Example Project Space" \
  --project-key EXAMPLE \
  --homepage-title "Example Project Space Home"
```

This path can:
- create a new global space
- reuse an existing space with the same key
- attach `openclaw.project_link` metadata
- create a landing page in that space

## Inspect the space

```bash
python3 agentic-skill-jiraconfluence/confluence_cli.py space-get --space-key EXAMPLE
```

Use this to verify:
- the space exists
- the key matches the project intent
- the response contains the expected identifiers

## Understand the current limit

This is not the same thing as the native Jira web UI "Connect to Confluence" relationship.

What is proven:
- Confluence space provisioning
- stable metadata linking
- reliable page publishing into the space

What is still manual:
- native Jira project-level Confluence UI linking
