#!/usr/bin/env python3
"""Build a connector-ready prompt for ChatGPT Adobe app workflows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = [
    "title",
    "executive_summary",
    "strategic_priorities",
    "risk_matrix",
    "citations",
]


def _load_payload(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Payload must be a JSON object")
    return data


def _validate_payload(payload: dict[str, Any]) -> None:
    missing = []
    for field in REQUIRED_FIELDS:
        value = payload.get(field)
        if not value:
            missing.append(field)
    if missing:
        raise ValueError("Missing required payload fields: " + ", ".join(missing))


def _render_risk_rows(rows: list[dict[str, Any]]) -> str:
    lines = []
    for idx, row in enumerate(rows, start=1):
        lines.append(
            f"{idx}. Risk: {row.get('risk', '')}; Impact: {row.get('impact', '')}; "
            f"Mitigation: {row.get('mitigation', '')}; Owner: {row.get('owner', '')}."
        )
    return "\n".join(lines)


def _render_citations(citations: list[dict[str, Any]]) -> str:
    lines = []
    for item in citations:
        lines.append(f"- [{item.get('id', '')}] {item.get('source', '')} :: {item.get('note', '')}")
    return "\n".join(lines)


def _render_annexes(annexes: list[dict[str, Any]]) -> str:
    if not annexes:
        return "- No annexes requested."

    lines = []
    for idx, annex in enumerate(annexes, start=1):
        items = annex.get("items", [])
        item_text = "; ".join(str(item) for item in items) if items else "No items listed"
        lines.append(
            f"{idx}. {annex.get('title', '')}: {annex.get('summary', '')}. Items: {item_text}."
        )
    return "\n".join(lines)


def _build_prompt(payload: dict[str, Any], profile: str) -> str:
    summary_text = "\n".join(f"- {item}" for item in payload["executive_summary"])
    priorities_text = "\n".join(
        f"{idx}. {item}" for idx, item in enumerate(payload["strategic_priorities"], start=1)
    )
    risk_rows = _render_risk_rows(payload["risk_matrix"])
    citations = _render_citations(payload["citations"])
    annexes = _render_annexes(payload.get("annexes", []))

    profile_instructions = {
        "strict-legal": "Enforce all strict legal gates: privilege signals, citation integrity, redaction verification, metadata hygiene.",
        "adobe-standard": "Enforce Adobe production quality and accessibility defaults.",
        "fast": "Prioritize speed while preserving required structure and citation IDs.",
    }[profile]

    return f"""You are generating a C-suite legal PDF using the Adobe Acrobat app connector in ChatGPT.

PROFILE: {profile}
RULE: {profile_instructions}

Generate one polished A4 PDF with professional legal tone and clear hierarchy.

Required sections and content:
1) Title: {payload['title']}
2) Executive Summary:
{summary_text}
3) Strategic Priorities:
{priorities_text}
4) Risk Matrix:
{risk_rows}
5) Citation Register (must preserve IDs exactly):
{citations}
6) Annexes:
{annexes}

Mandatory quality controls:
- Print visible phrase: PRIVILEGED & CONFIDENTIAL on cover/header.
- Keep all citation IDs verbatim (for example SR-1, SR-2).
- Do not include unresolved placeholders like [REDACTED_PENDING], <REDACT_ME>, TODO_REDACT.
- Keep metadata minimal and avoid personal or draft metadata values.
- Preserve concise executive readability and courtroom-safe language.

Output requirements:
- Return exactly one final PDF artifact.
- Return a short QA checklist confirming privilege marker, citation completeness, and redaction gate status.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build connector prompt from normalized payload")
    parser.add_argument("--payload", required=True, help="Path to normalized payload JSON")
    parser.add_argument(
        "--profile",
        default="strict-legal",
        choices=["strict-legal", "adobe-standard", "fast"],
        help="Prompt profile",
    )
    parser.add_argument("--output", required=True, help="Path to output prompt text file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload_path = Path(args.payload).resolve()
    output_path = Path(args.output).resolve()

    if not payload_path.exists():
        print(f"ERROR: Payload not found: {payload_path}", file=sys.stderr)
        return 1

    try:
        payload = _load_payload(payload_path)
        _validate_payload(payload)
        prompt = _build_prompt(payload, args.profile)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(prompt, encoding="utf-8")
    print(f"Wrote connector prompt: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
