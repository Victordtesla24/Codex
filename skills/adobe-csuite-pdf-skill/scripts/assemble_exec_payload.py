#!/usr/bin/env python3
"""Normalize executive legal inputs into canonical payload JSON."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = [
    "title",
    "executive_summary",
    "strategic_priorities",
    "risk_matrix",
    "citations",
]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def _coerce_string_list(value: Any, field_name: str) -> list[str]:
    if isinstance(value, str):
        items = [value.strip()] if value.strip() else []
    elif isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
    else:
        raise ValueError(f"Field '{field_name}' must be a string or list of strings")
    return items


def _normalize_risk_matrix(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError("Field 'risk_matrix' must be a list")

    normalized: list[dict[str, str]] = []
    for index, row in enumerate(value, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"risk_matrix[{index}] must be an object")
        normalized.append(
            {
                "risk": str(row.get("risk", "")).strip(),
                "impact": str(row.get("impact", "")).strip(),
                "mitigation": str(row.get("mitigation", "")).strip(),
                "owner": str(row.get("owner", "")).strip(),
            }
        )

    return [row for row in normalized if any(row.values())]


def _normalize_citations(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError("Field 'citations' must be a list")

    normalized: list[dict[str, str]] = []
    counter = 1
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if not text:
                continue
            match = re.match(r"^\[?([A-Za-z]+-?\d+)\]?\s*[:\-]\s*(.+)$", text)
            if match:
                citation_id, source = match.groups()
                normalized.append({"id": citation_id.strip(), "source": source.strip(), "note": ""})
            else:
                normalized.append({"id": f"CIT-{counter}", "source": text, "note": ""})
                counter += 1
            continue

        if isinstance(item, dict):
            citation_id = str(item.get("id", "")).strip() or f"CIT-{counter}"
            source = str(item.get("source", "")).strip()
            note = str(item.get("note", "")).strip()
            if source:
                normalized.append({"id": citation_id, "source": source, "note": note})
                counter += 1
            continue

        raise ValueError("Each citation must be a string or object")

    return normalized


def _normalize_annexes(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Field 'annexes' must be a list when provided")

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"annexes[{index}] must be an object")
        items = item.get("items", [])
        if isinstance(items, str):
            items = [items]
        if not isinstance(items, list):
            raise ValueError(f"annexes[{index}].items must be a list or string")

        normalized.append(
            {
                "title": str(item.get("title", "")).strip(),
                "summary": str(item.get("summary", "")).strip(),
                "items": [str(entry).strip() for entry in items if str(entry).strip()],
            }
        )

    return normalized


def _pick_section(sections: dict[str, list[str]], names: list[str]) -> list[str]:
    for name in names:
        key = name.lower()
        if key in sections and any(line.strip() for line in sections[key]):
            return sections[key]
    return []


def _parse_markdown_table(lines: list[str]) -> list[dict[str, str]]:
    table_lines = [line.strip() for line in lines if "|" in line]
    if len(table_lines) < 2:
        return []

    header = [cell.strip().lower() for cell in table_lines[0].strip("|").split("|")]
    separator = table_lines[1]
    if "---" not in separator:
        return []

    key_map = {
        "risk": "risk",
        "impact": "impact",
        "mitigation": "mitigation",
        "owner": "owner",
    }

    normalized_rows: list[dict[str, str]] = []
    for raw_line in table_lines[2:]:
        cells = [cell.strip() for cell in raw_line.strip("|").split("|")]
        if not any(cells):
            continue
        row = {"risk": "", "impact": "", "mitigation": "", "owner": ""}
        for idx, head in enumerate(header):
            if idx >= len(cells):
                break
            mapped_key = key_map.get(head)
            if mapped_key:
                row[mapped_key] = cells[idx]
        if any(row.values()):
            normalized_rows.append(row)

    return normalized_rows


def _parse_markdown_bullets(lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        match = re.match(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)(.+)$", line)
        if match:
            value = match.group(1).strip()
            if value:
                items.append(value)
    return items


def _parse_markdown_payload(text: str) -> dict[str, Any]:
    sections: dict[str, list[str]] = {}
    headings: list[str] = []
    current = "__preamble__"
    sections[current] = []

    for raw_line in text.splitlines():
        heading_match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", raw_line)
        if heading_match:
            heading = heading_match.group(1).strip()
            normalized = heading.lower()
            headings.append(heading)
            current = normalized
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(raw_line.rstrip())

    title = ""
    if headings:
        title = headings[0].strip()
    if not title:
        for line in sections.get("__preamble__", []):
            if line.strip():
                title = line.strip().lstrip("#").strip()
                break

    summary_lines = _pick_section(sections, ["executive summary", "summary", "brief summary"])
    priorities_lines = _pick_section(sections, ["strategic priorities", "priorities", "action priorities"])
    risk_lines = _pick_section(sections, ["risk matrix", "risks"])
    citation_lines = _pick_section(sections, ["citations", "references", "sources"])
    annex_lines = _pick_section(sections, ["annexes", "appendices"])

    risk_matrix = _parse_markdown_table(risk_lines)
    if not risk_matrix:
        for entry in _parse_markdown_bullets(risk_lines):
            parts = [part.strip() for part in entry.split("|")]
            risk_matrix.append(
                {
                    "risk": parts[0] if len(parts) > 0 else entry,
                    "impact": parts[1] if len(parts) > 1 else "",
                    "mitigation": parts[2] if len(parts) > 2 else "",
                    "owner": parts[3] if len(parts) > 3 else "",
                }
            )

    citation_candidates = _parse_markdown_bullets(citation_lines)
    annexes = []
    for bullet in _parse_markdown_bullets(annex_lines):
        title_part, _, summary_part = bullet.partition(":")
        annexes.append(
            {
                "title": title_part.strip(),
                "summary": summary_part.strip(),
                "items": [],
            }
        )

    return {
        "title": title,
        "executive_summary": _parse_markdown_bullets(summary_lines) or [line.strip() for line in summary_lines if line.strip()],
        "strategic_priorities": _parse_markdown_bullets(priorities_lines)
        or [line.strip() for line in priorities_lines if line.strip()],
        "risk_matrix": risk_matrix,
        "citations": citation_candidates,
        "annexes": annexes,
    }


def _load_input(path: Path, fmt: str) -> dict[str, Any]:
    text = _read_text(path)

    effective_format = fmt
    if fmt == "auto":
        suffix = path.suffix.lower()
        if suffix == ".json":
            effective_format = "json"
        elif suffix in {".yaml", ".yml"}:
            effective_format = "yaml"
        else:
            effective_format = "markdown"

    if effective_format == "json":
        return json.loads(text)

    if effective_format == "yaml":
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ValueError("PyYAML is required for --format yaml") from exc
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError("YAML input must parse to an object")
        return data

    if effective_format == "markdown":
        return _parse_markdown_payload(text)

    raise ValueError(f"Unsupported format: {effective_format}")


def _normalize_payload(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Input must parse to a JSON object")

    title = str(raw.get("title", "")).strip()
    executive_summary = _coerce_string_list(raw.get("executive_summary", []), "executive_summary")
    strategic_priorities = _coerce_string_list(raw.get("strategic_priorities", []), "strategic_priorities")
    risk_matrix = _normalize_risk_matrix(raw.get("risk_matrix", []))
    citations = _normalize_citations(raw.get("citations", []))
    annexes = _normalize_annexes(raw.get("annexes"))

    normalized = {
        "title": title,
        "executive_summary": executive_summary,
        "strategic_priorities": strategic_priorities,
        "risk_matrix": risk_matrix,
        "citations": citations,
        "annexes": annexes,
        "metadata": {
            "profile": "strict-legal",
            "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    }

    missing = [
        field
        for field in REQUIRED_FIELDS
        if not normalized.get(field) or (isinstance(normalized[field], list) and len(normalized[field]) == 0)
    ]
    if missing:
        raise ValueError(
            "Missing required sections after normalization: " + ", ".join(missing)
        )

    return normalized


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize executive legal input into payload JSON")
    parser.add_argument("--input", required=True, help="Path to input file")
    parser.add_argument(
        "--format",
        default="auto",
        choices=["auto", "json", "yaml", "markdown"],
        help="Input format",
    )
    parser.add_argument("--output", required=True, help="Path to output JSON payload")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    if not input_path.exists():
        print(f"ERROR: Input not found: {input_path}", file=sys.stderr)
        return 1

    try:
        raw = _load_input(input_path, args.format)
        payload = _normalize_payload(raw)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote normalized payload: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
