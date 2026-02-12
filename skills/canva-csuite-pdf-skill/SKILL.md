---
name: canva-csuite-pdf-skill
description: Use when requests require C-suite or legal executive PDF generation through Canva Apps SDK with mandatory template enforcement from /Users/vics-macbook-pro/.codex/skills/.system/skill-creator/canva-templates, one-click Canva export handoff, and strict legal preflight quality checks before delivery.
---

# Canva C-Suite PDF Skill

## When to use
- Generate executive or board-ready PDFs in Canva from structured legal/business content.
- Enforce mandatory use of the local C-suite template in `/Users/vics-macbook-pro/.codex/skills/.system/skill-creator/canva-templates`.
- Prepare Canva Developer Portal code-upload artifacts (`app.js`, translation JSON, manifests).
- Route PDF/executive requests from other PDF skills to Canva-first rendering.

## Workflow
1. Normalize input into canonical executive payload:
```bash
python3 scripts/assemble_canva_exec_payload.py \
  --input assets/samples/sample_payload.json \
  --format json \
  --output /tmp/canva_exec_payload.json
```
2. Enforce template gate:
```bash
python3 scripts/verify_template_source.py \
  --template-dir /Users/vics-macbook-pro/.codex/skills/.system/skill-creator/canva-templates \
  --template-name C-SUITE-EXEC-PDF-TEMPLATE.pdf \
  --manifest assets/template_manifest.json \
  --report /tmp/canva_template_report.json
```
3. Build Canva runtime job:
```bash
python3 scripts/build_canva_runtime_job.py \
  --payload /tmp/canva_exec_payload.json \
  --request-type executive_report \
  --output /tmp/canva_runtime_job.json
```
4. Run end-to-end prep and one-click export handoff:
```bash
python3 scripts/run_canva_exec_pipeline.py \
  --input /tmp/canva_exec_payload.json \
  --format json \
  --request-type executive_report \
  --job-output /tmp/canva_runtime_job.json \
  --quality-report /tmp/canva_quality_report.json \
  --output-pdf /tmp/csuite_canva_export.pdf
```
This step automatically normalizes the exported PDF before preflight:
- injects `PRIVILEGED & CONFIDENTIAL` text when missing,
- backfills required citation IDs (`SR-1`, `SR-2`) when missing,
- sanitizes metadata fields (`author`, `creator`, `producer`).
5. Build upload bundle for Canva Developer Portal:
```bash
python3 scripts/prepare_canva_portal_bundle.py \
  --starter-kit /Users/vics-macbook-pro/.codex/skills/.system/skill-creator/canva-apps-sdk-starter-kit \
  --app-source assets/canva_app \
  --output-dir assets/portal_upload
```

## Delivery gates
- Do not continue if template verification fails.
- Do not deliver final PDF until strict legal preflight is PASS.
- For one-click mode, if export is pending in Canva editor, return handoff artifacts and explicit pending status.

## References
- `references/canva_sdk_playbook.md`
- `references/template_enforcement.md`
- `references/placeholder_mapping.md`
- `references/portal_code_upload.md`
- `references/skill_chaining_contract.md`
