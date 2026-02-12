# Template Enforcement

## Canonical source
- Directory: `/Users/vics-macbook-pro/.codex/skills/.system/skill-creator/canva-templates`
- File: `C-SUITE-EXEC-PDF-TEMPLATE.pdf`
- Manifest: `assets/template_manifest.json`

## Enforcement policy
1. Verify file exists and is readable.
2. Verify extension is `.pdf`.
3. Verify hash matches manifest.
4. Fail fast if any check fails.

## No-scratch rule
- Rendering flow must stop when template validation fails.
- Do not produce a final deliverable PDF if the template gate is not PASS.
