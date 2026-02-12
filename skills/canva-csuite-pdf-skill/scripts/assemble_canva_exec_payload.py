#!/usr/bin/env python3
"""Normalize executive input into a canonical Canva runtime payload."""

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
REQUIRED_CITATION_IDS = ["SR-1", "SR-2"]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def _coerce_string_list(value: Any, field_name: str) -> list[str]:
    if isinstance(value, str):
        candidate = value.strip()
        return [candidate] if candidate else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError(f"Field '{field_name}' must be a string or list of strings")


def _normalize_risk_matrix(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError("Field 'risk_matrix' must be a list")

    rows: list[dict[str, str]] = []
    for index, row in enumerate(value, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"risk_matrix[{index}] must be an object")

        normalized = {
            "risk": str(row.get("risk", "")).strip(),
            "impact": str(row.get("impact", "")).strip(),
            "mitigation": str(row.get("mitigation", "")).strip(),
            "owner": str(row.get("owner", "")).strip(),
        }
        if any(normalized.values()):
            rows.append(normalized)

    return rows


def _normalize_citations(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError("Field 'citations' must be a list")

    citations: list[dict[str, str]] = []
    seq = 1

    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if not text:
                continue
            match = re.match(r"^\[?([A-Za-z]+-?\d+)\]?\s*[:\-]\s*(.+)$", text)
            if match:
                citation_id, source = match.groups()
                citations.append({"id": citation_id.strip(), "source": source.strip(), "note": ""})
            else:
                citations.append({"id": f"SRC-{seq}", "source": text, "note": ""})
                seq += 1
            continue

        if isinstance(item, dict):
            citation_id = str(item.get("id", "")).strip() or f"SRC-{seq}"
            source = str(item.get("source", "")).strip()
            note = str(item.get("note", "")).strip()
            if source:
                citations.append({"id": citation_id, "source": source, "note": note})
                seq += 1
            continue

        raise ValueError("Each citation must be a string or object")

    return citations


def _ensure_required_citations(citations: list[dict[str, str]]) -> list[dict[str, str]]:
    by_id = {str(item.get("id", "")).strip().upper(): item for item in citations if item.get("id")}
    normalized = list(citations)

    for citation_id in REQUIRED_CITATION_IDS:
        key = citation_id.upper()
        if key in by_id:
            continue

        normalized.append(
            {
                "id": citation_id,
                "source": "Compliance citation placeholder",
                "note": "AUTO-BACKFILL: replace with validated legal source before external circulation.",
            }
        )

    return normalized


def _normalize_annexes(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Field 'annexes' must be a list when provided")

    annexes: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"annexes[{index}] must be an object")
        items = item.get("items", [])
        if isinstance(items, str):
            items = [items]
        if not isinstance(items, list):
            raise ValueError(f"annexes[{index}].items must be a list or string")
        annexes.append(
            {
                "title": str(item.get("title", "")).strip(),
                "summary": str(item.get("summary", "")).strip(),
                "items": [str(entry).strip() for entry in items if str(entry).strip()],
            }
        )

    return annexes


def _parse_markdown_bullets(lines: list[str]) -> list[str]:
    values: list[str] = []
    for line in lines:
        match = re.match(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)(.+)$", line)
        if match:
            value = match.group(1).strip()
            if value:
                values.append(value)
    return values


def _parse_markdown_table(lines: list[str]) -> list[dict[str, str]]:
    table_lines = [line.strip() for line in lines if "|" in line]
    if len(table_lines) < 2 or "---" not in table_lines[1]:
        return []

    header = [cell.strip().lower() for cell in table_lines[0].strip("|").split("|")]
    key_map = {
        "risk": "risk",
        "impact": "impact",
        "mitigation": "mitigation",
        "owner": "owner",
    }

    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not any(cells):
            continue

        row = {"risk": "", "impact": "", "mitigation": "", "owner": ""}
        for idx, cell in enumerate(cells):
            if idx >= len(header):
                break
            mapped = key_map.get(header[idx])
            if mapped:
                row[mapped] = cell

        if any(row.values()):
            rows.append(row)

    return rows


def _section_lines(markdown: str) -> tuple[str, dict[str, list[str]]]:
    sections: dict[str, list[str]] = {"__preamble__": []}
    title = ""
    current = "__preamble__"

    for raw_line in markdown.splitlines():
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", raw_line)
        if heading:
            heading_text = heading.group(1).strip()
            if not title:
                title = heading_text
            current = heading_text.lower()
            sections.setdefault(current, [])
            continue

        sections.setdefault(current, []).append(raw_line.rstrip())

    if not title:
        for line in sections["__preamble__"]:
            line = line.strip().lstrip("#").strip()
            if line:
                title = line
                break

    return title, sections


def _pick_section(sections: dict[str, list[str]], aliases: list[str]) -> list[str]:
    for alias in aliases:
        key = alias.lower()
        if key in sections and any(line.strip() for line in sections[key]):
            return sections[key]
    return []


def _parse_markdown(markdown: str) -> dict[str, Any]:
    title, sections = _section_lines(markdown)

    summary_lines = _pick_section(sections, ["executive summary", "summary"])
    priorities_lines = _pick_section(sections, ["strategic priorities", "priorities"])
    risk_lines = _pick_section(sections, ["risk matrix", "risks"])
    citation_lines = _pick_section(sections, ["citations", "sources", "references"])
    annex_lines = _pick_section(sections, ["annexes", "appendices"])

    risk_rows = _parse_markdown_table(risk_lines)
    if not risk_rows:
        for entry in _parse_markdown_bullets(risk_lines):
            pieces = [part.strip() for part in entry.split("|")]
            risk_rows.append(
                {
                    "risk": pieces[0] if len(pieces) > 0 else entry,
                    "impact": pieces[1] if len(pieces) > 1 else "",
                    "mitigation": pieces[2] if len(pieces) > 2 else "",
                    "owner": pieces[3] if len(pieces) > 3 else "",
                }
            )

    annexes: list[dict[str, Any]] = []
    for entry in _parse_markdown_bullets(annex_lines):
        title_part, _, summary_part = entry.partition(":")
        annexes.append({"title": title_part.strip(), "summary": summary_part.strip(), "items": []})

    return {
        "title": title,
        "executive_summary": _parse_markdown_bullets(summary_lines)
        or [line.strip() for line in summary_lines if line.strip()],
        "strategic_priorities": _parse_markdown_bullets(priorities_lines)
        or [line.strip() for line in priorities_lines if line.strip()],
        "risk_matrix": risk_rows,
        "citations": _parse_markdown_bullets(citation_lines),
        "annexes": annexes,
    }


def _load_input(path: Path, fmt: str) -> tuple[dict[str, Any], str]:
    text = _read_text(path)

    effective = fmt
    if fmt == "auto":
        suffix = path.suffix.lower()
        if suffix == ".json":
            effective = "json"
        elif suffix in {".yaml", ".yml"}:
            effective = "yaml"
        else:
            effective = "markdown"

    if effective == "json":
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("JSON input must be an object")
        return parsed, effective

    if effective == "yaml":
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError("PyYAML is required for YAML input. Install with: python3 -m pip install pyyaml") from exc

        parsed = yaml.safe_load(text)
        if not isinstance(parsed, dict):
            raise ValueError("YAML input must be an object")
        return parsed, effective

    return _parse_markdown(text), effective


def assemble_payload(input_path: Path, fmt: str) -> dict[str, Any]:
    data, source_format = _load_input(input_path, fmt)

    payload: dict[str, Any] = {
        "title": str(data.get("title", "")).strip(),
        "audience": str(data.get("audience", "")).strip(),
        "tone": str(data.get("tone", "")).strip(),
        "content": str(data.get("content", "")).strip(),
        "executive_summary": _coerce_string_list(data.get("executive_summary", []), "executive_summary"),
        "strategic_priorities": _coerce_string_list(data.get("strategic_priorities", []), "strategic_priorities"),
        "risk_matrix": _normalize_risk_matrix(data.get("risk_matrix", [])),
        "citations": _ensure_required_citations(_normalize_citations(data.get("citations", []))),
        "annexes": _normalize_annexes(data.get("annexes")),
        "metadata": {
            "source_file": str(input_path),
            "source_format": source_format,
            "assembled_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    }

    missing = [key for key in REQUIRED_FIELDS if not payload.get(key)]
    if missing:
        raise ValueError("Missing required fields after normalization: " + ", ".join(missing))

    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize executive input into Canva payload JSON")
    parser.add_argument("--input", required=True, help="Source input file")
    parser.add_argument(
        "--format",
        default="auto",
        choices=["auto", "json", "yaml", "markdown"],
        help="Input format",
    )
    parser.add_argument("--output", required=True, help="Output payload JSON path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        return 1

    try:
        payload = assemble_payload(input_path, args.format)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote payload: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
