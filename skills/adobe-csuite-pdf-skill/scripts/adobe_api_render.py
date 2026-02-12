#!/usr/bin/env python3
"""Render executive PDFs using Acrobat Services REST flow, with mock support."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from adobe_credentials import (  # type: ignore
    CredentialResolutionError,
    credentials_summary,
    resolve_credentials,
)
from adobe_rest_auth import (  # type: ignore
    AdobeApiError,
    create_upload_asset,
    download_asset,
    poll_create_pdf_job,
    request_access_token,
    submit_create_pdf_job,
    upload_asset_bytes,
)

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
    missing = [key for key in REQUIRED_FIELDS if not payload.get(key)]
    if missing:
        raise ValueError("Missing required payload fields: " + ", ".join(missing))


def _render_lines(payload: dict[str, Any]) -> list[str]:
    lines = [
        "PRIVILEGED & CONFIDENTIAL",
        payload["title"],
        "",
        "Executive Summary",
    ]

    for item in payload["executive_summary"]:
        lines.append(f"- {item}")

    lines.extend(["", "Strategic Priorities"])
    for idx, item in enumerate(payload["strategic_priorities"], start=1):
        lines.append(f"{idx}. {item}")

    lines.extend(["", "Risk Matrix"])
    for row in payload["risk_matrix"]:
        lines.append(
            "Risk: {risk}; Impact: {impact}; Mitigation: {mitigation}; Owner: {owner}".format(
                risk=row.get("risk", ""),
                impact=row.get("impact", ""),
                mitigation=row.get("mitigation", ""),
                owner=row.get("owner", ""),
            )
        )

    lines.extend(["", "Citations"])
    for citation in payload["citations"]:
        lines.append(
            f"[{citation.get('id', '')}] {citation.get('source', '')} - {citation.get('note', '')}"
        )

    annexes = payload.get("annexes", [])
    if annexes:
        lines.extend(["", "Annexes"])
        for annex in annexes:
            lines.append(f"- {annex.get('title', '')}: {annex.get('summary', '')}")
            for item in annex.get("items", []):
                lines.append(f"  * {item}")

    return lines


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _make_info_object(metadata: dict[str, str]) -> bytes:
    tokens = ["<<"]
    for key, value in metadata.items():
        if not value:
            continue
        key_token = key[:1].upper() + key[1:]
        tokens.append(f"/{key_token} ({_pdf_escape(value)})")
    tokens.append(">>")
    return " ".join(tokens).encode("latin-1", errors="ignore")


def _write_basic_pdf(output_path: Path, lines: list[str], metadata: dict[str, str] | None = None) -> None:
    commands = ["BT", "/F1 11 Tf", "50 790 Td"]
    for index, line in enumerate(lines):
        if index > 0:
            commands.append("0 -14 Td")
        commands.append(f"({_pdf_escape(line)}) Tj")
    commands.append("ET")

    stream_content = "\n".join(commands).encode("latin-1", errors="ignore")

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream_content)).encode("ascii") + b" >>\nstream\n" + stream_content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    info_index: int | None = None
    if metadata:
        objects.append(_make_info_object(metadata))
        info_index = len(objects)

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{i} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    startxref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    trailer = f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R".encode("ascii")
    if info_index is not None:
        trailer += f" /Info {info_index} 0 R".encode("ascii")
    trailer += b" >>\n"

    pdf.extend(trailer)
    pdf.extend(f"startxref\n{startxref}\n%%EOF\n".encode("ascii"))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(bytes(pdf))


def _read_metadata(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Metadata JSON must be an object")
    return {str(key): str(value) for key, value in raw.items()}


def _operation_supported_in_live_mode(operation: str) -> bool:
    return operation == "create-pdf"


def _determine_api_base_url(api_base_url: str, endpoint_alias: str | None) -> str:
    if endpoint_alias and not api_base_url:
        return endpoint_alias.rstrip("/")

    if endpoint_alias:
        alias = endpoint_alias.rstrip("/")
        if "/operation/" in alias:
            return alias.split("/operation/")[0]
        if alias.endswith("/assets"):
            return alias[: -len("/assets")]
        if alias.endswith("/token"):
            return alias[: -len("/token")]
        return alias

    return api_base_url.rstrip("/")


def _render_live(
    *,
    payload: dict[str, Any],
    output_path: Path,
    operation: str,
    credentials_json: str | None,
    token_url: str,
    api_base_url: str,
    endpoint_alias: str | None,
    poll_timeout_seconds: int,
    poll_interval_seconds: float,
    request_timeout_seconds: int,
) -> dict[str, Any]:
    if not _operation_supported_in_live_mode(operation):
        raise RuntimeError(
            f"Operation '{operation}' is not yet implemented for official REST mode. "
            "Use --operation create-pdf or use --mock for local simulation."
        )

    credentials = resolve_credentials(credentials_json)
    lines = _render_lines(payload)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".txt",
        delete=False,
        prefix="adobe_createpdf_",
    ) as handle:
        source_file = Path(handle.name)
        handle.write("\n".join(lines) + "\n")

    try:
        token = request_access_token(
            credentials,
            token_url=token_url,
            timeout_seconds=request_timeout_seconds,
        )

        base_url = _determine_api_base_url(api_base_url, endpoint_alias)

        upload_info = create_upload_asset(
            api_base_url=base_url,
            access_token=token["access_token"],
            client_id=credentials.client_id,
            media_type="text/plain",
            timeout_seconds=request_timeout_seconds,
        )

        upload_result = upload_asset_bytes(
            upload_uri=upload_info["upload_uri"],
            input_path=source_file,
            media_type="text/plain",
            timeout_seconds=max(request_timeout_seconds, 120),
        )

        create_job = submit_create_pdf_job(
            api_base_url=base_url,
            access_token=token["access_token"],
            client_id=credentials.client_id,
            asset_id=upload_info["asset_id"],
            document_language="en-US",
            timeout_seconds=request_timeout_seconds,
        )

        job_result = poll_create_pdf_job(
            location_url=create_job["location"],
            access_token=token["access_token"],
            client_id=credentials.client_id,
            poll_timeout_seconds=poll_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            request_timeout_seconds=request_timeout_seconds,
        )

        download_uri = str(job_result["asset"].get("downloadUri", "")).strip()
        if not download_uri:
            raise RuntimeError("Create PDF job completed without downloadUri")

        download_result = download_asset(
            download_uri=download_uri,
            output_path=output_path,
            timeout_seconds=max(request_timeout_seconds, 120),
        )

        return {
            "mode": "live",
            "operation": operation,
            "credentials": credentials_summary(credentials),
            "token": {
                "token_type": token["token_type"],
                "expires_in": token["expires_in"],
                "request_id": token.get("request_id"),
            },
            "api_base_url": base_url,
            "token_url": token_url,
            "source_file": str(source_file),
            "steps": {
                "asset": upload_info,
                "upload": upload_result,
                "create_job": create_job,
                "job_result": {
                    "status": job_result["status"],
                    "attempts": job_result["attempts"],
                    "request_id": job_result.get("request_id"),
                },
                "download": download_result,
            },
            "output": str(output_path),
        }
    finally:
        if source_file.exists():
            source_file.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render executive PDF using Adobe API fallback")
    parser.add_argument("--payload", required=True, help="Path to normalized payload JSON")
    parser.add_argument(
        "--operation",
        required=True,
        choices=["create-pdf", "watermark", "protect", "redact"],
        help="Fallback operation",
    )
    parser.add_argument("--output", required=True, help="Output PDF path")
    parser.add_argument("--endpoint", help="Deprecated alias for API base URL override")
    parser.add_argument("--mock", action="store_true", help="Generate mock PDF without network call")
    parser.add_argument("--metadata-json", help="Optional JSON metadata for generated PDF info dictionary")
    parser.add_argument("--request-log", help="Optional path for request log JSON")

    parser.add_argument("--credentials-json", help="Credentials JSON path override")
    parser.add_argument(
        "--token-url",
        default="https://pdf-services.adobe.io/token",
        help="Adobe token endpoint URL",
    )
    parser.add_argument(
        "--api-base-url",
        default="https://pdf-services.adobe.io",
        help="Adobe API base URL",
    )
    parser.add_argument(
        "--poll-timeout-seconds",
        type=int,
        default=300,
        help="Max seconds to wait for job completion",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=2.0,
        help="Seconds between polling attempts",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=int,
        default=60,
        help="Per-request network timeout seconds",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload_path = Path(args.payload).resolve()
    output_path = Path(args.output).resolve()
    metadata_path = Path(args.metadata_json).resolve() if args.metadata_json else None

    if not payload_path.exists():
        print(f"ERROR: Payload not found: {payload_path}", file=sys.stderr)
        return 1

    try:
        payload = _load_payload(payload_path)
        _validate_payload(payload)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    request_log = Path(args.request_log).resolve() if args.request_log else output_path.with_suffix(".request.json")
    request_log.parent.mkdir(parents=True, exist_ok=True)

    try:
        metadata = _read_metadata(metadata_path)

        if args.mock:
            _write_basic_pdf(output_path, _render_lines(payload), metadata)
            log_payload = {
                "mode": "mock",
                "operation": args.operation,
                "output": str(output_path),
                "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            request_log.write_text(json.dumps(log_payload, indent=2) + "\n", encoding="utf-8")
            print(f"Mock PDF generated: {output_path}")
            print(f"Request log written: {request_log}")
            return 0

        live_log = _render_live(
            payload=payload,
            output_path=output_path,
            operation=args.operation,
            credentials_json=args.credentials_json,
            token_url=args.token_url,
            api_base_url=args.api_base_url,
            endpoint_alias=args.endpoint,
            poll_timeout_seconds=args.poll_timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
            request_timeout_seconds=args.request_timeout_seconds,
        )
        live_log["timestamp_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        request_log.write_text(json.dumps(live_log, indent=2) + "\n", encoding="utf-8")

        print(f"Live PDF generated: {output_path}")
        print(f"Request log written: {request_log}")
        return 0
    except CredentialResolutionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except AdobeApiError as exc:
        error_payload = {
            "mode": "live",
            "error": exc.to_dict(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        request_log.write_text(json.dumps(error_payload, indent=2) + "\n", encoding="utf-8")
        print(f"ERROR: {exc}", file=sys.stderr)
        if exc.request_id:
            print(f"ERROR: x-request-id={exc.request_id}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
