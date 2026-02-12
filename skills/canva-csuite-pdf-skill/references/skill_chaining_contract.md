# Skill Chaining Contract

## Routing priority
1. `canva-csuite-pdf-skill` first for PDF/executive requests.
2. Existing Adobe flows as fallback where Canva export is unavailable.
3. Strict legal preflight is required before final delivery.

## Integration points
- Global PDF skill router script:
  - `/Users/vics-macbook-pro/.codex/skills/pdf/scripts/route_pdf_to_canva.py`
- Adobe C-suite router script:
  - `/Users/Shared/codex/legal-strategy-dashboard/Skills/adobe-csuite-pdf-skill/scripts/route_exec_renderer.py`

## Output expectations
- Runtime job JSON is always produced for Canva flow.
- If one-click export is pending, return pending status plus handoff instructions.
- For finalized PDFs, require preflight PASS.
