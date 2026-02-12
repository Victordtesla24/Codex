#!/usr/bin/env python3
"""Credential resolution helpers for Adobe PDF Services scripts."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CREDENTIALS_JSON = Path(
    "/Users/vics-macbook-pro/.codex/skills/.system/skill-creator/PDFServicesSDK/pdfservices-api-credentials.json"
)


class CredentialResolutionError(RuntimeError):
    """Raised when credentials cannot be resolved from supported sources."""


@dataclass(frozen=True)
class AdobeCredentials:
    client_id: str
    client_secret: str
    organization_id: str | None
    source: str


def mask_secret(value: str, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}...{value[-keep:]}"


def _load_json_credentials(path: Path) -> AdobeCredentials:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CredentialResolutionError(f"Unable to read credentials JSON at {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise CredentialResolutionError(f"Credentials JSON at {path} must be an object")

    client_credentials = raw.get("client_credentials")
    if not isinstance(client_credentials, dict):
        raise CredentialResolutionError(
            f"Credentials JSON at {path} must contain object 'client_credentials'"
        )

    missing: list[str] = []
    client_id = str(client_credentials.get("client_id", "")).strip()
    client_secret = str(client_credentials.get("client_secret", "")).strip()
    if not client_id:
        missing.append("client_credentials.client_id")
    if not client_secret:
        missing.append("client_credentials.client_secret")
    if missing:
        raise CredentialResolutionError(
            f"Credentials JSON at {path} missing required keys: {', '.join(missing)}"
        )

    organization_id: str | None = None
    sp = raw.get("service_principal_credentials")
    if isinstance(sp, dict):
        org_id_raw = str(sp.get("organization_id", "")).strip()
        organization_id = org_id_raw or None

    return AdobeCredentials(
        client_id=client_id,
        client_secret=client_secret,
        organization_id=organization_id,
        source=f"json:{path}",
    )


def _load_env_credentials() -> AdobeCredentials:
    primary_id = os.getenv("PDF_SERVICES_CLIENT_ID", "").strip()
    primary_secret = os.getenv("PDF_SERVICES_CLIENT_SECRET", "").strip()
    legacy_id = os.getenv("ADOBE_PDF_SERVICES_CLIENT_ID", "").strip()
    legacy_secret = os.getenv("ADOBE_PDF_SERVICES_CLIENT_SECRET", "").strip()

    if primary_id and primary_secret:
        return AdobeCredentials(
            client_id=primary_id,
            client_secret=primary_secret,
            organization_id=None,
            source="env:PDF_SERVICES_CLIENT_ID/PDF_SERVICES_CLIENT_SECRET",
        )

    if legacy_id and legacy_secret:
        return AdobeCredentials(
            client_id=legacy_id,
            client_secret=legacy_secret,
            organization_id=None,
            source="env:ADOBE_PDF_SERVICES_CLIENT_ID/ADOBE_PDF_SERVICES_CLIENT_SECRET",
        )

    partial_messages: list[str] = []
    if primary_id and not primary_secret:
        partial_messages.append(
            "PDF_SERVICES_CLIENT_ID is set but PDF_SERVICES_CLIENT_SECRET is missing"
        )
    if primary_secret and not primary_id:
        partial_messages.append(
            "PDF_SERVICES_CLIENT_SECRET is set but PDF_SERVICES_CLIENT_ID is missing"
        )
    if legacy_id and not legacy_secret:
        partial_messages.append(
            "ADOBE_PDF_SERVICES_CLIENT_ID is set but ADOBE_PDF_SERVICES_CLIENT_SECRET is missing"
        )
    if legacy_secret and not legacy_id:
        partial_messages.append(
            "ADOBE_PDF_SERVICES_CLIENT_SECRET is set but ADOBE_PDF_SERVICES_CLIENT_ID is missing"
        )

    if partial_messages:
        raise CredentialResolutionError("; ".join(partial_messages))

    raise CredentialResolutionError(
        "No usable environment credentials found. Expected either "
        "PDF_SERVICES_CLIENT_ID/PDF_SERVICES_CLIENT_SECRET or "
        "ADOBE_PDF_SERVICES_CLIENT_ID/ADOBE_PDF_SERVICES_CLIENT_SECRET."
    )


def resolve_credentials(credentials_json_arg: str | None = None) -> AdobeCredentials:
    candidates: list[tuple[str, Path]] = []

    if credentials_json_arg:
        candidates.append(("--credentials-json", Path(credentials_json_arg).expanduser()))

    env_json = os.getenv("ADOBE_PDF_CREDENTIALS_JSON", "").strip()
    if env_json:
        env_path = Path(env_json).expanduser()
        if not any(path == env_path for _, path in candidates):
            candidates.append(("ADOBE_PDF_CREDENTIALS_JSON", env_path))

    if not any(path == DEFAULT_CREDENTIALS_JSON for _, path in candidates):
        candidates.append(("default", DEFAULT_CREDENTIALS_JSON))

    json_attempt_messages: list[str] = []
    for label, candidate_path in candidates:
        resolved = candidate_path.resolve(strict=False)
        if not resolved.exists():
            json_attempt_messages.append(f"{label}: credentials file not found at {resolved}")
            continue

        try:
            return _load_json_credentials(resolved)
        except CredentialResolutionError as exc:
            json_attempt_messages.append(f"{label}: {exc}")
            continue

    try:
        return _load_env_credentials()
    except CredentialResolutionError as env_exc:
        details = "\n".join(f"- {msg}" for msg in json_attempt_messages)
        raise CredentialResolutionError(
            "Could not resolve Adobe credentials from JSON or environment.\n"
            f"JSON attempts:\n{details}\n"
            f"Environment fallback: {env_exc}"
        ) from env_exc


def credentials_summary(credentials: AdobeCredentials) -> dict[str, Any]:
    return {
        "source": credentials.source,
        "client_id_masked": mask_secret(credentials.client_id),
        "organization_id": credentials.organization_id,
    }
