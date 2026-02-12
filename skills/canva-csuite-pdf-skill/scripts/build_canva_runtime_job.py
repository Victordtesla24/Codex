#!/usr/bin/env python3
"""Build Canva runtime job JSON from normalized executive payload."""

from __future__ import annotations

import argparse
import json
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


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON object required: {path}")
    return data


def _default_assets_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "assets"


def build_runtime_job(
    payload: dict[str, Any],
    request_type: str,
    template_manifest: dict[str, Any],
    placeholder_bindings: dict[str, Any],
) -> dict[str, Any]:
    missing = [field for field in REQUIRED_FIELDS if not payload.get(field)]
    if missing:
        raise ValueError("Payload missing required fields: " + ", ".join(missing))

    missing_bindings = [field for field in REQUIRED_FIELDS if field not in placeholder_bindings]
    if missing_bindings:
        raise ValueError("Placeholder mapping missing required bindings: " + ", ".join(missing_bindings))

    section_map = {
        "title": {"required": True, "content_type": "text"},
        "executive_summary": {"required": True, "content_type": "bullet_list"},
        "strategic_priorities": {"required": True, "content_type": "numbered_list"},
        "risk_matrix": {"required": True, "content_type": "structured_rows"},
        "citations": {"required": True, "content_type": "citation_list"},
        "annexes": {"required": False, "content_type": "optional_annex"},
    }

    return {
        "version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "request_type": request_type,
        "profile": "strict-legal",
        "template": {
            "template_name": template_manifest.get("template_name", "C-SUITE-EXEC-PDF-TEMPLATE.pdf"),
            "template_path": template_manifest.get("template_path", ""),
            "policy": template_manifest.get("policy", "local-folder-only"),
            "required_keyword": "C-SUITE-EXEC",
        },
        "section_map": section_map,
        "placeholder_bindings": placeholder_bindings,
        "payload": payload,
        "rendering_instructions": {
            "mode": "prep-and-one-click-export",
            "accepted_file_types": ["pdf_standard"],
            "must_include_phrase": "PRIVILEGED & CONFIDENTIAL",
            "must_preserve_citations": True,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Canva runtime job JSON")
    parser.add_argument("--payload", required=True, help="Normalized payload JSON")
    parser.add_argument("--request-type", required=True, help="Request type (for routing/audit)")
    parser.add_argument("--output", required=True, help="Runtime job output JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload_path = Path(args.payload).resolve()
    output_path = Path(args.output).resolve()

    if not payload_path.exists():
        print(f"ERROR: Payload not found: {payload_path}", file=sys.stderr)
        return 1

    assets_dir = _default_assets_dir()
    template_manifest_path = assets_dir / "template_manifest.json"
    placeholder_map_path = assets_dir / "template_placeholders.json"

    if not template_manifest_path.exists():
        print(f"ERROR: Template manifest not found: {template_manifest_path}", file=sys.stderr)
        return 1
    if not placeholder_map_path.exists():
        print(f"ERROR: Placeholder mapping not found: {placeholder_map_path}", file=sys.stderr)
        return 1

    try:
        payload = _load_json(payload_path)
        template_manifest = _load_json(template_manifest_path)
        placeholder_bindings = _load_json(placeholder_map_path)
        job = build_runtime_job(payload, args.request_type, template_manifest, placeholder_bindings)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote runtime job: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
