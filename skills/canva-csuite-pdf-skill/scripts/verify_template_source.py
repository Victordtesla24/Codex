#!/usr/bin/env python3
"""Verify mandatory local template source and hash against manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_TEMPLATE_DIR = Path("/Users/vics-macbook-pro/.codex/skills/.system/skill-creator/canva-templates")
DEFAULT_TEMPLATE_NAME = "C-SUITE-EXEC-PDF-TEMPLATE.pdf"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Manifest JSON must be an object")
    return data


def _check(name: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "passed": passed, "details": details}


def verify_template(
    template_dir: Path,
    template_name: str,
    manifest_path: Path,
) -> tuple[bool, dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    manifest = _load_manifest(manifest_path)
    declared_path_raw = str(manifest.get("template_path", "")).strip()
    declared_hash = str(manifest.get("sha256", "")).strip().lower()

    template_path = (template_dir / template_name).resolve()
    declared_path = Path(declared_path_raw).resolve() if declared_path_raw else None

    path_match = declared_path is None or declared_path == template_path
    checks.append(
        _check(
            "manifest_path_match",
            path_match,
            {
                "manifest_template_path": str(declared_path) if declared_path else "",
                "resolved_template_path": str(template_path),
            },
        )
    )

    exists = template_path.exists() and template_path.is_file()
    checks.append(_check("template_exists", exists, {"path": str(template_path)}))

    readable = exists and os.access(template_path, os.R_OK)
    checks.append(_check("template_readable", readable, {"path": str(template_path)}))

    extension_ok = template_path.suffix.lower() == ".pdf"
    checks.append(_check("template_extension", extension_ok, {"suffix": template_path.suffix.lower()}))

    actual_hash = _sha256(template_path) if exists and readable else ""
    hash_match = bool(declared_hash) and actual_hash.lower() == declared_hash
    checks.append(
        _check(
            "template_sha256",
            hash_match,
            {
                "expected_sha256": declared_hash,
                "actual_sha256": actual_hash,
            },
        )
    )

    passed = all(item["passed"] for item in checks)
    report = {
        "status": "PASS" if passed else "FAIL",
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "template_dir": str(template_dir),
        "template_name": template_name,
        "manifest": str(manifest_path),
        "checks": checks,
    }
    return passed, report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify required local Canva template source")
    parser.add_argument("--template-dir", default=str(DEFAULT_TEMPLATE_DIR), help="Template directory")
    parser.add_argument("--template-name", default=DEFAULT_TEMPLATE_NAME, help="Template file name")
    parser.add_argument("--manifest", required=True, help="Template manifest JSON")
    parser.add_argument("--report", required=True, help="Output verification report JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    template_dir = Path(args.template_dir).resolve()
    manifest_path = Path(args.manifest).resolve()
    report_path = Path(args.report).resolve()

    if not manifest_path.exists():
        print(f"ERROR: Manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    try:
        passed, report = verify_template(template_dir, args.template_name, manifest_path)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Template verification: {report['status']}")
    print(f"Report written: {report_path}")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
