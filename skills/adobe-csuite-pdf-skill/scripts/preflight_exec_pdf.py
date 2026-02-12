#!/usr/bin/env python3
"""Run strict legal preflight checks against an executive PDF."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _extract_with_pypdf(pdf_path: Path) -> tuple[str, dict[str, str], int]:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pypdf is required for rich preflight. Install with: python3 -m pip install pypdf") from exc

    reader = PdfReader(str(pdf_path))
    page_text = []
    for page in reader.pages:
        page_text.append(page.extract_text() or "")

    metadata_raw = reader.metadata or {}
    metadata: dict[str, str] = {}
    for key, value in metadata_raw.items():
        if value is None:
            continue
        clean_key = str(key).lstrip("/").lower()
        metadata[clean_key] = str(value).strip()

    return "\n".join(page_text), metadata, len(reader.pages)


def _extract_with_pypdf2(pdf_path: Path) -> tuple[str, dict[str, str], int]:
    try:
        from PyPDF2 import PdfReader  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PyPDF2 is not available") from exc

    reader = PdfReader(str(pdf_path))
    page_text = []
    for page in reader.pages:
        page_text.append(page.extract_text() or "")

    metadata_raw = reader.metadata or {}
    metadata: dict[str, str] = {}
    for key, value in metadata_raw.items():
        if value is None:
            continue
        clean_key = str(key).lstrip("/").lower()
        metadata[clean_key] = str(value).strip()

    return "\n".join(page_text), metadata, len(reader.pages)


def _extract_fallback(pdf_path: Path) -> tuple[str, dict[str, str], int]:
    content = pdf_path.read_bytes().decode("latin-1", errors="ignore")
    text_fragments = re.findall(r"\((.*?)\)\s*Tj", content)
    text = "\n".join(text_fragments) if text_fragments else content
    page_count = max(1, content.count("/Type /Page"))

    metadata: dict[str, str] = {}
    for key in ("Author", "Creator", "Producer", "Title", "Subject", "Keywords"):
        match = re.search(rf"/{key}\s*\((.*?)\)", content, flags=re.IGNORECASE | re.DOTALL)
        if match:
            metadata[key.lower()] = match.group(1).strip()

    return text, metadata, page_count


def _load_pdf(pdf_path: Path) -> tuple[str, dict[str, str], int]:
    try:
        return _extract_with_pypdf(pdf_path)
    except Exception:
        try:
            return _extract_with_pypdf2(pdf_path)
        except Exception:
            return _extract_fallback(pdf_path)


def _load_rules(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Rules file must be a JSON object")
    return data


def _check_required_phrases(text: str, rules: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    required = [str(item) for item in rules.get("required_phrases", [])]
    lower = text.lower()
    missing = [phrase for phrase in required if phrase.lower() not in lower]
    return len(missing) == 0, {"required": required, "missing": missing}


def _check_required_citations(text: str, rules: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    required = [str(item) for item in rules.get("required_citations", [])]
    lower = text.lower()
    missing = [citation for citation in required if citation.lower() not in lower]
    return len(missing) == 0, {"required": required, "missing": missing}


def _check_prohibited_patterns(text: str, rules: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    prohibited = [str(item) for item in rules.get("prohibited_patterns", [])]
    lower = text.lower()
    hits = [pattern for pattern in prohibited if pattern.lower() in lower]
    return len(hits) == 0, {"prohibited": prohibited, "hits": hits}


def _check_redaction(text: str, rules: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    redaction = rules.get("redaction", {})
    if not isinstance(redaction, dict):
        redaction = {}

    pending_patterns = [str(item) for item in redaction.get("pending_patterns", [])]
    sensitive_terms = [str(item) for item in redaction.get("sensitive_terms", [])]
    lower = text.lower()

    pending_hits = [item for item in pending_patterns if item.lower() in lower]
    leak_hits = [item for item in sensitive_terms if item.lower() in lower]

    passed = not pending_hits and not leak_hits
    details = {
        "pending_patterns": pending_patterns,
        "pending_hits": pending_hits,
        "sensitive_terms": sensitive_terms,
        "sensitive_term_hits": leak_hits,
    }
    return passed, details


def _check_metadata(metadata: dict[str, str], rules: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    forbidden_keys = [str(item).lower() for item in rules.get("forbidden_metadata_keys", [])]
    forbidden_patterns = [str(item).lower() for item in rules.get("forbidden_metadata_patterns", [])]

    def _effective_value(value: str) -> str:
        clean = value.strip()
        if clean.lower() in {"nullobject", "null", "none"}:
            return ""
        return clean

    present_forbidden_keys = [key for key in forbidden_keys if _effective_value(metadata.get(key, ""))]

    pattern_hits: list[dict[str, str]] = []
    for key, value in metadata.items():
        clean_value = _effective_value(value)
        if not clean_value:
            continue
        lower_value = clean_value.lower()
        for pattern in forbidden_patterns:
            if pattern and pattern in lower_value:
                pattern_hits.append({"key": key, "pattern": pattern, "value": clean_value})

    passed = not present_forbidden_keys and not pattern_hits
    details = {
        "metadata": metadata,
        "forbidden_keys": forbidden_keys,
        "present_forbidden_keys": present_forbidden_keys,
        "forbidden_patterns": forbidden_patterns,
        "pattern_hits": pattern_hits,
    }
    return passed, details


def _check_min_pages(page_count: int, rules: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    min_pages = int(rules.get("min_pages", 1))
    return page_count >= min_pages, {"min_pages": min_pages, "actual_pages": page_count}


def _record(name: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "passed": passed, "details": details}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run strict legal preflight checks for executive PDFs")
    parser.add_argument("--pdf", required=True, help="Path to PDF file")
    parser.add_argument("--rules", required=True, help="Path to strict rules JSON")
    parser.add_argument("--report", required=True, help="Path to output report JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pdf_path = Path(args.pdf).resolve()
    rules_path = Path(args.rules).resolve()
    report_path = Path(args.report).resolve()

    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        return 1
    if not rules_path.exists():
        print(f"ERROR: Rules not found: {rules_path}", file=sys.stderr)
        return 1

    try:
        rules = _load_rules(rules_path)
        text, metadata, page_count = _load_pdf(pdf_path)

        checks = [
            _record("privilege_watermark", *_check_required_phrases(text, rules)),
            _record("citation_integrity", *_check_required_citations(text, rules)),
            _record("placeholder_rejection", *_check_prohibited_patterns(text, rules)),
            _record("redaction_verification", *_check_redaction(text, rules)),
            _record("metadata_hygiene", *_check_metadata(metadata, rules)),
            _record("min_page_count", *_check_min_pages(page_count, rules)),
        ]

        passed = all(check["passed"] for check in checks)

        report = {
            "status": "PASS" if passed else "FAIL",
            "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "pdf": str(pdf_path),
            "rules": str(rules_path),
            "page_count": page_count,
            "checks": checks,
        }
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Preflight status: {report['status']}")
    print(f"Report written: {report_path}")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
