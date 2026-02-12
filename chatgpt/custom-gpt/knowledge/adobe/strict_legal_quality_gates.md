# Strict Legal Quality Gates

Use this gate policy for `preflight_exec_pdf.py`.

## Gate Set
1. **Privilege watermark gate**
- Require all phrases from `required_phrases`.
- Typical values: `PRIVILEGED`, `CONFIDENTIAL`.

2. **Citation integrity gate**
- Require every citation ID listed in `required_citations`.
- Treat missing IDs as hard failure.

3. **Redaction verification gate**
- Reject any unresolved marker in `redaction.pending_patterns`.
- Reject any leak token in `redaction.sensitive_terms`.

4. **Metadata hygiene gate**
- Reject forbidden metadata keys in `forbidden_metadata_keys`.
- Reject metadata values matching `forbidden_metadata_patterns`.

5. **Document minimum gate**
- Enforce `min_pages` threshold.

## Rules File Contract
Use JSON with this shape:
```json
{
  "required_phrases": ["PRIVILEGED", "CONFIDENTIAL"],
  "required_citations": ["SR-1", "SR-2"],
  "prohibited_patterns": ["[REDACTED_PENDING]", "<REDACT_ME>"],
  "forbidden_metadata_keys": ["author", "creator", "producer"],
  "forbidden_metadata_patterns": ["@", "client name", "draft only"],
  "min_pages": 1,
  "redaction": {
    "pending_patterns": ["[REDACTED_PENDING]", "<REDACT_ME>"],
    "sensitive_terms": []
  }
}
```

## Pass/Fail Policy
1. Mark report as `PASS` only if every gate passes.
2. Mark report as `FAIL` when any gate fails.
3. Include per-gate evidence in output JSON.
