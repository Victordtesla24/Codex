---
name: adobe-csuite-pdf-skill
description: Create C-suite executive legal PDFs with strict legal-quality controls using Canva-first rendering, then Adobe connector/API fallback. Use when Codex must produce privileged legal briefs, board-ready reports, or executive defense packets in PDF; route through $canva-csuite-pdf-skill first, fall back to ChatGPT Adobe connector or Adobe PDF Services API when needed, and always run strict local legal preflight before delivery.
---

# Adobe C-Suite PDF Skill

## Overview
Generate executive legal PDFs through a routed workflow: normalize input, attempt Canva-first rendering, apply Adobe fallback as needed, and block delivery until strict legal preflight passes.

## Workflow Decision Tree
1. Normalize source content with `scripts/assemble_exec_payload.py`.
2. Route renderer with `scripts/route_exec_renderer.py`.
3. Renderer `auto` executes:
   - Canva-first pipeline via `$canva-csuite-pdf-skill`.
   - Adobe API fallback via `scripts/adobe_api_render.py` when Canva path fails/pends.
4. If explicit connector path is required, use `scripts/build_connector_prompt.py` and `references/chatgpt_connector_playbook.md`.
5. Run `scripts/preflight_exec_pdf.py` with strict rules before delivery.
6. Deliver only when every gate passes.

## Credential Resolution Order
The Adobe fallback scripts resolve credentials in this order:
1. `--credentials-json`
2. `ADOBE_PDF_CREDENTIALS_JSON`
3. `/Users/vics-macbook-pro/.codex/skills/.system/skill-creator/PDFServicesSDK/pdfservices-api-credentials.json`
4. Environment fallback:
   - `PDF_SERVICES_CLIENT_ID` + `PDF_SERVICES_CLIENT_SECRET`
   - `ADOBE_PDF_SERVICES_CLIENT_ID` + `ADOBE_PDF_SERVICES_CLIENT_SECRET`

## Quick Start
1. Assemble payload:
```bash
python3 scripts/assemble_exec_payload.py \
  --input assets/samples/sample_payload.json \
  --format json \
  --output /tmp/executive_payload.json
```
2. Route renderer (Canva-first, Adobe fallback):
```bash
python3 scripts/route_exec_renderer.py \
  --payload /tmp/executive_payload.json \
  --output /tmp/executive_brief.pdf \
  --renderer auto \
  --request-log /tmp/executive_route_log.json
```
3. Optional direct Adobe API render (mock):
```bash
python3 scripts/adobe_api_render.py \
  --payload /tmp/executive_payload.json \
  --operation create-pdf \
  --mock \
  --output /tmp/executive_brief.pdf
```
4. Strict preflight:
```bash
python3 scripts/preflight_exec_pdf.py \
  --pdf /tmp/executive_brief.pdf \
  --rules assets/samples/strict_rules.json \
  --report /tmp/executive_preflight.json
```

## Adobe REST Flow
Live mode uses the official Acrobat Services contract:
1. `POST /token` using `client_id` and `client_secret`.
2. `POST /assets` with `Authorization: Bearer` and `x-api-key`.
3. Upload source asset with `PUT uploadUri`.
4. `POST /operation/createpdf`.
5. Poll job `location` until `done` or `failed`.
6. Download output from `asset.downloadUri`.

## Strict Legal Gates
Apply these gates for every run:
1. Require privilege signals (`PRIVILEGED`, `CONFIDENTIAL`) in output text.
2. Verify required citations listed in rules.
3. Reject unresolved redaction markers and prohibited tokens.
4. Reject forbidden metadata keys and forbidden metadata value patterns.
5. Enforce minimum page count and explicit pass/fail report output.

## References
Load only the file needed for the current step:
- `references/input_schema.md`: input contract and examples.
- `references/chatgpt_connector_playbook.md`: connector execution plus Canva routing contract.
- `references/adobe_api_fallback.md`: API fallback execution and router behavior.
- `references/executive_layout_spec.md`: C-suite visual/layout requirements.
- `references/strict_legal_quality_gates.md`: rule semantics and gate policy.

## Assets
Reuse templates and samples instead of rewriting structure:
- `assets/templates/master_brief_template.md`
- `assets/templates/annex_template.md`
- `assets/samples/sample_payload.json`
- `assets/samples/strict_rules.json`
