# Input Schema

Use this schema for normalized payload JSON consumed by connector and fallback scripts.

## Required Fields
- `title` (string): document title shown on cover and header.
- `executive_summary` (array of strings): concise outcome-oriented summary points.
- `strategic_priorities` (array of strings): ordered action priorities.
- `risk_matrix` (array of objects): each row must include `risk`, `impact`, `mitigation`, `owner`.
- `citations` (array of objects): each citation must include `id`, `source`, `note`.

## Optional Fields
- `annexes` (array of objects): each annex may include `title`, `summary`, `items`.
- `metadata` (object): run metadata; auto-populated by assembler if missing.

## Canonical JSON Shape
```json
{
  "title": "Executive Legal Strategy Brief",
  "executive_summary": [
    "Summary point 1",
    "Summary point 2"
  ],
  "strategic_priorities": [
    "Priority 1",
    "Priority 2"
  ],
  "risk_matrix": [
    {
      "risk": "Risk statement",
      "impact": "Business/legal impact",
      "mitigation": "Mitigation action",
      "owner": "Owner role"
    }
  ],
  "citations": [
    {
      "id": "SR-1",
      "source": "Source label",
      "note": "Why this source matters"
    }
  ],
  "annexes": [
    {
      "title": "Annex A",
      "summary": "Support material summary",
      "items": ["Item 1", "Item 2"]
    }
  ],
  "metadata": {
    "profile": "strict-legal",
    "generated_at_utc": "2026-02-12T00:00:00Z"
  }
}
```

## Validation Rules
1. Reject payloads missing any required top-level field.
2. Reject empty arrays for required list fields.
3. Coerce single strings to one-item arrays where reasonable.
4. Preserve optional `annexes` if present; default to empty array otherwise.
