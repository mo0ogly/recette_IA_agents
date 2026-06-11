# GRC Migration -- {{direction}}

Source   : `{{source_id}}` ({{source_name}})
Target   : `{{target_id_or_placeholder}}`
Client   : `{{client_id}}`
Date     : {{YYYY-MM-DD}}
Session  : `grc-migrate-{{session_id}}`
Status   : IN_PROGRESS

## Source Inventory

| Entity | Count | Notes |
|--------|-------|-------|
| {{auto-populated from P1 queries}} | | |

## Target Schema

Tables that will receive INSERT/UPDATE:

- {{auto-populated}}

## Migration Gap Tracker

Legend: `[ ]` pending, `[x]` resolved, suffix `✓ <ISO timestamp>` on completion, `-- ERROR: <reason>` on failure, `-- DROPPED` when no equivalent.

### Identity + scope

- [ ] G01 -- Study name -> Assessment name
      Source field(s) : `ebios_rm_studies.name`
      Target field(s) : `smsi_risk_assessments.name`
      Strategy        : DIRECT
      Status          : PENDING

### {{section per gap cluster}}

- [ ] Gxx -- ...

## Decision Log

{{REPLAN entries + per-gap errors here}}

## Footer

Checked : {{N}}/{{total}}
Status  : IN_PROGRESS | PARTIAL ({{N}}/{{total}}) | MIGRATION FULL ✓
