# ChatGPT Adobe Connector Playbook

Use this as a manual connector execution path when renderer mode is `adobe-connector` or when explicit connector fallback is requested.

## Pre-Run
1. Generate normalized payload JSON.
2. Generate connector prompt text from payload.
3. Confirm strict rules file path for final preflight.

## Routing context
- Default renderer order is Canva-first through `$canva-csuite-pdf-skill`.
- Use connector workflow only when Canva path is unavailable or user explicitly requests connector mode.

## Execute in ChatGPT UI
1. Open ChatGPT with Adobe Acrobat app connector enabled.
2. Paste prompt from `build_connector_prompt.py` output.
3. Provide payload JSON as structured input if requested.
4. Request one PDF output artifact only.
5. Save PDF locally for gate checks.

## Mandatory Output Requirements
1. Include privilege markers in visible text.
2. Include all required citation IDs exactly as provided.
3. Preserve section order: title, summary, priorities, risk matrix, citations, annexes.
4. Keep executive readability with clear hierarchy and page chrome.

## After Connector Run
1. Run `preflight_exec_pdf.py` with strict rules.
2. If any gate fails, revise prompt/payload and rerun connector.
3. Deliver only after preflight status is `PASS`.
