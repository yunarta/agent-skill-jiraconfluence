# ReportDocument v1

Canonical semantic contract for report publication into Confluence.

## Purpose

- Keep local reporting flexible while preserving a stable semantic contract.
- Separate meaning from presentation.
- Support both structured YAML files and legacy markdown reports already present in this repo.

## Accepted local source shapes

- `.yaml` / `.yml`
  - First YAML document must be the canonical report mapping.
  - Optional second YAML document may hold extra narrative content.
- `.md`
  - Existing local markdown reports are accepted as source input.
  - The CLI normalizes them into `report.v1` before rendering or publishing.

## Required fields

```yaml
schema_version: report.v1
report_id: ARC-001-SPR-003-RPT-001
title: Sprint 3 execution sync
report_type: execution_sync
status: draft
summary:
  executive: Short report summary.
  outcome: Short outcome statement.
traceability:
  source_path: .agile/practice/arcs/ARC-001-jira-crud-skill/reports/example.md
  source_type: local-markdown-report
  upstream_jira_keys: []
  confluence_page_id: null
  confluence_page_url: null
  labels: []
```

## Recommended fields

```yaml
arc_id: ARC-001-jira-crud-skill
sprint_id: SPR-003
stage: Execution
context:
  defaults_chosen: []
  blockers: []
decisions: []
open_questions: []
risks: []
next_actions: []
artifacts: []
sections: []
publisher:
  render_target: confluence
  renderer_version: 0.1.0
  publish_mode: draft
```

## Traceability contract

- `report_id` must be stable for the same logical report.
- `traceability.source_path` points to the local source artifact.
- `traceability.confluence_page_id` stores the published page identity when known.
- `traceability.upstream_jira_keys` stores related Jira execution artifacts.
- `traceability.labels` stores publication-friendly tags.

## Design rule

- Agents should emit semantics, not target-specific page markup.
- Renderers own Confluence formatting.
- Publishers own delivery and update behavior.
