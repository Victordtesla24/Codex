#!/usr/bin/env python3
"""Route executive render requests: Canva-first, then Adobe fallback."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CANVA_PIPELINE = Path("/Users/vics-macbook-pro/.codex/skills/canva-csuite-pdf-skill/scripts/run_canva_exec_pipeline.py")
ADOBE_RENDER = Path(__file__).resolve().parent / "adobe_api_render.py"
CONNECTOR_PROMPT = Path(__file__).resolve().parent / "build_connector_prompt.py"


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def _attempt_canva(payload_path: Path, output_pdf: Path, request_log: Path) -> dict[str, Any]:
    job_output = request_log.with_suffix(".canva_job.json")
    quality_output = request_log.with_suffix(".canva_quality.json")

    cmd = [
        sys.executable,
        str(CANVA_PIPELINE),
        "--input",
        str(payload_path),
        "--format",
        "json",
        "--request-type",
        "executive_report",
        "--job-output",
        str(job_output),
        "--quality-report",
        str(quality_output),
        "--output-pdf",
        str(output_pdf),
    ]

    if os.getenv("CANVA_SKIP_PREFLIGHT", "").strip() in {"1", "true", "TRUE"}:
        cmd.append("--skip-preflight")

    run = _run(cmd)
    return {
        "name": "canva_pipeline",
        "returncode": run.returncode,
        "stdout": run.stdout.strip(),
        "stderr": run.stderr.strip(),
        "job_output": str(job_output),
        "quality_output": str(quality_output),
    }


def _attempt_adobe_api(payload_path: Path, output_pdf: Path) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(ADOBE_RENDER),
        "--payload",
        str(payload_path),
        "--operation",
        "create-pdf",
        "--output",
        str(output_pdf),
    ]

    if os.getenv("ADOBE_RENDER_MOCK", "").strip() in {"1", "true", "TRUE"}:
        cmd.append("--mock")

    run = _run(cmd)
    return {
        "name": "adobe_api",
        "returncode": run.returncode,
        "stdout": run.stdout.strip(),
        "stderr": run.stderr.strip(),
    }


def _attempt_adobe_connector(payload_path: Path, request_log: Path) -> dict[str, Any]:
    prompt_path = request_log.with_suffix(".connector_prompt.txt")

    cmd = [
        sys.executable,
        str(CONNECTOR_PROMPT),
        "--payload",
        str(payload_path),
        "--profile",
        "strict-legal",
        "--output",
        str(prompt_path),
    ]

    run = _run(cmd)
    return {
        "name": "adobe_connector",
        "returncode": run.returncode,
        "stdout": run.stdout.strip(),
        "stderr": run.stderr.strip(),
        "prompt_path": str(prompt_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Route executive renderer path")
    parser.add_argument("--payload", required=True, help="Normalized payload JSON")
    parser.add_argument("--output", required=True, help="Output PDF path")
    parser.add_argument(
        "--renderer",
        required=True,
        choices=["auto", "canva", "adobe-connector", "adobe-api"],
        help="Renderer mode",
    )
    parser.add_argument("--request-log", required=True, help="Request log JSON output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    payload_path = Path(args.payload).resolve()
    output_pdf = Path(args.output).resolve()
    request_log = Path(args.request_log).resolve()

    report: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload": str(payload_path),
        "output": str(output_pdf),
        "renderer": args.renderer,
        "attempts": [],
        "status": "RUNNING",
    }

    if not payload_path.exists():
        report["status"] = "ERROR"
        report["error"] = f"Payload not found: {payload_path}"
        request_log.parent.mkdir(parents=True, exist_ok=True)
        request_log.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"ERROR: {report['error']}", file=sys.stderr)
        return 1

    if args.renderer == "canva":
        canva = _attempt_canva(payload_path, output_pdf, request_log)
        report["attempts"].append(canva)
        report["status"] = "SUCCESS_CANVA" if canva["returncode"] == 0 else "FAILED_CANVA"
        rc = 0 if canva["returncode"] == 0 else canva["returncode"] or 1

    elif args.renderer == "adobe-api":
        adobe = _attempt_adobe_api(payload_path, output_pdf)
        report["attempts"].append(adobe)
        report["status"] = "SUCCESS_ADOBE_API" if adobe["returncode"] == 0 else "FAILED_ADOBE_API"
        rc = 0 if adobe["returncode"] == 0 else adobe["returncode"] or 1

    elif args.renderer == "adobe-connector":
        connector = _attempt_adobe_connector(payload_path, request_log)
        report["attempts"].append(connector)
        if connector["returncode"] == 0:
            report["status"] = "PENDING_MANUAL_CONNECTOR_RUN"
            rc = 4
        else:
            report["status"] = "FAILED_ADOBE_CONNECTOR_PROMPT"
            rc = connector["returncode"] or 1

    else:  # auto
        canva = _attempt_canva(payload_path, output_pdf, request_log)
        report["attempts"].append(canva)
        if canva["returncode"] == 0:
            report["status"] = "SUCCESS_CANVA"
            rc = 0
        else:
            adobe = _attempt_adobe_api(payload_path, output_pdf)
            report["attempts"].append(adobe)
            if adobe["returncode"] == 0:
                report["status"] = "SUCCESS_ADOBE_FALLBACK"
                rc = 0
            else:
                report["status"] = "FAILED_ALL_RENDERERS"
                rc = adobe["returncode"] or 1

    request_log.parent.mkdir(parents=True, exist_ok=True)
    request_log.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Renderer status: {report['status']}")
    print(f"Request log: {request_log}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
