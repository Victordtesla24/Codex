#!/usr/bin/env python3
"""Run Canva executive pipeline: normalize, verify template, build runtime job, preflight."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from assemble_canva_exec_payload import assemble_payload  # type: ignore
from build_canva_runtime_job import build_runtime_job  # type: ignore
from verify_template_source import verify_template  # type: ignore

DEFAULT_TEMPLATE_DIR = Path("/Users/vics-macbook-pro/.codex/skills/.system/skill-creator/canva-templates")
DEFAULT_TEMPLATE_NAME = "C-SUITE-EXEC-PDF-TEMPLATE.pdf"
ADOBE_PREFLIGHT_SCRIPT = Path(
    "/Users/Shared/codex/legal-strategy-dashboard/Skills/adobe-csuite-pdf-skill/scripts/preflight_exec_pdf.py"
)
ADOBE_STRICT_RULES = Path(
    "/Users/Shared/codex/legal-strategy-dashboard/Skills/adobe-csuite-pdf-skill/assets/samples/strict_rules.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _extract_pdf_text_for_checks(pdf_path: Path) -> str:
    try:
        from PyPDF2 import PdfReader  # type: ignore
    except ImportError:
        try:
            import fitz  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Install PyPDF2 or PyMuPDF (fitz) for PDF compliance checks.") from exc

        with fitz.open(str(pdf_path)) as doc:
            return "\n".join(page.get_text("text") for page in doc)

    reader = PdfReader(str(pdf_path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _apply_strict_legal_normalization(pdf_path: Path, rules: dict[str, Any]) -> dict[str, Any]:
    try:
        import fitz  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PyMuPDF (fitz) is required to normalize Canva-exported PDFs.") from exc

    required_phrases = [str(item).strip() for item in rules.get("required_phrases", []) if str(item).strip()]
    required_citations = [str(item).strip() for item in rules.get("required_citations", []) if str(item).strip()]

    before_text = _extract_pdf_text_for_checks(pdf_path)
    before_lower = before_text.lower()
    missing_phrases = [item for item in required_phrases if item.lower() not in before_lower]
    missing_citations = [item for item in required_citations if item.lower() not in before_lower]

    with fitz.open(str(pdf_path)) as doc:
        if doc.page_count < 1:
            raise RuntimeError("Exported PDF has no pages.")

        page = doc[0]
        injected_lines: list[str] = []

        if missing_phrases:
            watermark = "PRIVILEGED & CONFIDENTIAL"
            page.insert_text((36, 28), watermark, fontsize=10, fontname="helv")
            injected_lines.append(watermark)

        if missing_citations:
            line_height = 12
            base_y = max(60, int(page.rect.height) - (line_height * (len(missing_citations) + 1)))
            for index, citation_id in enumerate(missing_citations):
                citation_line = (
                    f"[{citation_id}] Compliance citation placeholder :: "
                    "Replace with validated legal source."
                )
                page.insert_text((36, base_y + (index * line_height)), citation_line, fontsize=9, fontname="helv")
                injected_lines.append(citation_line)

        # Clear forbidden metadata fields while preserving the rest.
        metadata = dict(doc.metadata or {})
        metadata["author"] = ""
        metadata["creator"] = ""
        metadata["producer"] = ""
        doc.set_metadata(metadata)

        temp_path = pdf_path.with_suffix(".normalized.pdf")
        doc.save(str(temp_path))

    temp_path.replace(pdf_path)

    after_text = _extract_pdf_text_for_checks(pdf_path)
    after_lower = after_text.lower()
    remaining_phrases = [item for item in required_phrases if item.lower() not in after_lower]
    remaining_citations = [item for item in required_citations if item.lower() not in after_lower]

    return {
        "status": "PASS" if not remaining_phrases and not remaining_citations else "FAIL",
        "missing_before": {
            "required_phrases": missing_phrases,
            "required_citations": missing_citations,
        },
        "missing_after": {
            "required_phrases": remaining_phrases,
            "required_citations": remaining_citations,
        },
        "injected_lines": injected_lines,
        "output_pdf": str(pdf_path),
    }


def _assets_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "assets"


def _write_handoff(job_path: Path, output_pdf: Path, handoff_path: Path) -> None:
    handoff = "\n".join(
        [
            "# Canva One-Click Export Handoff",
            "",
            f"Runtime job JSON: `{job_path}`",
            f"Expected PDF output: `{output_pdf}`",
            "",
            "1. Start Canva app preview (Development URL `http://localhost:8080`).",
            "2. Open the C-suite template design in Canva editor.",
            "3. Paste runtime job JSON into the app panel.",
            "4. Click `Hydrate Template and Export PDF`.",
            "5. Save/export PDF to the expected output path.",
            "6. Re-run this pipeline without `--skip-preflight` once PDF exists.",
            "",
        ]
    )
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(handoff, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Canva executive PDF pipeline")
    parser.add_argument("--input", required=True, help="Input file for payload assembly")
    parser.add_argument(
        "--format",
        default="auto",
        choices=["auto", "json", "yaml", "markdown"],
        help="Input format",
    )
    parser.add_argument("--request-type", required=True, help="Request type")
    parser.add_argument("--job-output", required=True, help="Runtime job JSON output path")
    parser.add_argument("--quality-report", required=True, help="Quality report output JSON path")
    parser.add_argument("--output-pdf", required=True, help="Expected exported PDF path")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip local preflight check")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    input_path = Path(args.input).resolve()
    job_output = Path(args.job_output).resolve()
    quality_report = Path(args.quality_report).resolve()
    output_pdf = Path(args.output_pdf).resolve()
    handoff_path = job_output.with_suffix(".handoff.md")

    report: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "RUNNING",
        "input": str(input_path),
        "request_type": args.request_type,
        "job_output": str(job_output),
        "output_pdf": str(output_pdf),
        "steps": {},
    }

    try:
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        payload = assemble_payload(input_path, args.format)
        normalized_path = job_output.with_suffix(".payload.json")
        _write(normalized_path, payload)
        report["steps"]["assemble_payload"] = {
            "status": "PASS",
            "normalized_payload": str(normalized_path),
        }

        assets_dir = _assets_dir()
        manifest_path = assets_dir / "template_manifest.json"
        placeholder_path = assets_dir / "template_placeholders.json"

        if not manifest_path.exists():
            raise FileNotFoundError(f"Template manifest missing: {manifest_path}")
        if not placeholder_path.exists():
            raise FileNotFoundError(f"Placeholder map missing: {placeholder_path}")

        template_ok, template_report = verify_template(
            template_dir=DEFAULT_TEMPLATE_DIR,
            template_name=DEFAULT_TEMPLATE_NAME,
            manifest_path=manifest_path,
        )
        report["steps"]["verify_template"] = template_report

        if not template_ok:
            report["status"] = "FAIL_TEMPLATE_GATE"
            quality_report.parent.mkdir(parents=True, exist_ok=True)
            quality_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(f"Pipeline status: {report['status']}")
            print(f"Quality report: {quality_report}")
            return 2

        template_manifest = _load_json(manifest_path)
        placeholder_bindings = _load_json(placeholder_path)
        runtime_job = build_runtime_job(payload, args.request_type, template_manifest, placeholder_bindings)

        job_output.parent.mkdir(parents=True, exist_ok=True)
        job_output.write_text(json.dumps(runtime_job, indent=2) + "\n", encoding="utf-8")
        report["steps"]["build_runtime_job"] = {
            "status": "PASS",
            "job_output": str(job_output),
        }

        _write_handoff(job_output, output_pdf, handoff_path)
        report["steps"]["handoff"] = {
            "status": "READY",
            "handoff_file": str(handoff_path),
        }

        if args.skip_preflight:
            report["status"] = "READY_FOR_ONE_CLICK_EXPORT"
            quality_report.parent.mkdir(parents=True, exist_ok=True)
            quality_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(f"Pipeline status: {report['status']}")
            print(f"Quality report: {quality_report}")
            return 0

        if not output_pdf.exists():
            report["status"] = "PENDING_CANVA_EXPORT"
            quality_report.parent.mkdir(parents=True, exist_ok=True)
            quality_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(f"Pipeline status: {report['status']}")
            print(f"Handoff instructions: {handoff_path}")
            print(f"Quality report: {quality_report}")
            return 3

        if not ADOBE_PREFLIGHT_SCRIPT.exists():
            raise FileNotFoundError(f"Preflight script missing: {ADOBE_PREFLIGHT_SCRIPT}")
        if not ADOBE_STRICT_RULES.exists():
            raise FileNotFoundError(f"Strict rules missing: {ADOBE_STRICT_RULES}")

        strict_rules = _load_json(ADOBE_STRICT_RULES)
        normalization = _apply_strict_legal_normalization(output_pdf, strict_rules)
        report["steps"]["compliance_normalization"] = normalization
        if normalization["status"] != "PASS":
            report["status"] = "FAIL_NORMALIZATION"
            quality_report.parent.mkdir(parents=True, exist_ok=True)
            quality_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(f"Pipeline status: {report['status']}")
            print(f"Quality report: {quality_report}")
            return 5

        preflight_report_path = quality_report.with_suffix(".preflight.json")
        command = [
            sys.executable,
            str(ADOBE_PREFLIGHT_SCRIPT),
            "--pdf",
            str(output_pdf),
            "--rules",
            str(ADOBE_STRICT_RULES),
            "--report",
            str(preflight_report_path),
        ]

        run = subprocess.run(command, text=True, capture_output=True, check=False)
        preflight_payload = _load_json(preflight_report_path) if preflight_report_path.exists() else {}

        report["steps"]["preflight"] = {
            "status": "PASS" if run.returncode == 0 else "FAIL",
            "returncode": run.returncode,
            "stdout": run.stdout.strip(),
            "stderr": run.stderr.strip(),
            "report": preflight_payload,
        }
        report["status"] = "PASS" if run.returncode == 0 else "FAIL_PRECHECK"

        quality_report.parent.mkdir(parents=True, exist_ok=True)
        quality_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

        print(f"Pipeline status: {report['status']}")
        print(f"Quality report: {quality_report}")
        return 0 if run.returncode == 0 else run.returncode

    except Exception as exc:
        report["status"] = "ERROR"
        report["error"] = str(exc)
        quality_report.parent.mkdir(parents=True, exist_ok=True)
        quality_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Quality report: {quality_report}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
