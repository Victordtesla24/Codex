#!/usr/bin/env python3
"""Official Acrobat Services REST auth and create-pdf flow helpers."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adobe_credentials import AdobeCredentials


@dataclass
class HttpResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes


class AdobeApiError(RuntimeError):
    """Raised when Acrobat Services API calls fail."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
        body_excerpt: str | None = None,
        url: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id
        self.body_excerpt = body_excerpt
        self.url = url
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": str(self),
            "status_code": self.status_code,
            "request_id": self.request_id,
            "body_excerpt": self.body_excerpt,
            "url": self.url,
            "details": self.details,
        }


def _header_map(headers: Any) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in dict(headers).items()}


def _sanitize_body_excerpt(body: bytes, max_chars: int = 400) -> str:
    text = body.decode("utf-8", errors="ignore").replace("\n", " ").strip()
    if len(text) > max_chars:
        return text[:max_chars] + "..."
    return text


def _http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout_seconds: int = 60,
) -> HttpResponse:
    request = urllib.request.Request(
        url=url,
        method=method,
        headers=headers or {},
        data=data,
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return HttpResponse(
                status_code=int(response.status),
                headers=_header_map(response.headers),
                body=response.read(),
            )
    except urllib.error.HTTPError as exc:
        body = exc.read() if hasattr(exc, "read") else b""
        hdrs = _header_map(exc.headers or {})
        raise AdobeApiError(
            f"HTTP {exc.code} from {url}",
            status_code=int(exc.code),
            request_id=hdrs.get("x-request-id"),
            body_excerpt=_sanitize_body_excerpt(body),
            url=url,
        ) from exc
    except urllib.error.URLError as exc:
        raise AdobeApiError(
            f"Network error calling {url}: {exc.reason}",
            url=url,
        ) from exc


def request_access_token(
    credentials: AdobeCredentials,
    *,
    token_url: str,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    payload = urllib.parse.urlencode(
        {
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
        }
    ).encode("utf-8")

    response = _http_request(
        "POST",
        token_url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=payload,
        timeout_seconds=timeout_seconds,
    )

    try:
        body = json.loads(response.body.decode("utf-8"))
    except Exception as exc:
        raise AdobeApiError(
            "Token endpoint returned non-JSON response",
            status_code=response.status_code,
            request_id=response.headers.get("x-request-id"),
            body_excerpt=_sanitize_body_excerpt(response.body),
            url=token_url,
        ) from exc

    access_token = str(body.get("access_token", "")).strip()
    token_type = str(body.get("token_type", "Bearer")).strip() or "Bearer"

    expires_raw = body.get("expires_in", 0)
    try:
        expires_in = int(expires_raw)
    except Exception as exc:
        raise AdobeApiError(
            f"Invalid expires_in from token endpoint: {expires_raw}",
            status_code=response.status_code,
            request_id=response.headers.get("x-request-id"),
            url=token_url,
        ) from exc

    if not access_token:
        raise AdobeApiError(
            "Token response missing access_token",
            status_code=response.status_code,
            request_id=response.headers.get("x-request-id"),
            body_excerpt=_sanitize_body_excerpt(response.body),
            url=token_url,
        )

    return {
        "access_token": access_token,
        "token_type": token_type,
        "expires_in": expires_in,
        "obtained_at_epoch": int(time.time()),
        "request_id": response.headers.get("x-request-id"),
    }


def _api_headers(access_token: str, client_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "x-api-key": client_id,
    }


def create_upload_asset(
    *,
    api_base_url: str,
    access_token: str,
    client_id: str,
    media_type: str,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    endpoint = api_base_url.rstrip("/") + "/assets"
    payload = json.dumps({"mediaType": media_type}).encode("utf-8")

    response = _http_request(
        "POST",
        endpoint,
        headers={
            **_api_headers(access_token, client_id),
            "Content-Type": "application/json",
        },
        data=payload,
        timeout_seconds=timeout_seconds,
    )

    try:
        body = json.loads(response.body.decode("utf-8"))
    except Exception as exc:
        raise AdobeApiError(
            "Asset upload-URI endpoint returned non-JSON response",
            status_code=response.status_code,
            request_id=response.headers.get("x-request-id"),
            body_excerpt=_sanitize_body_excerpt(response.body),
            url=endpoint,
        ) from exc

    asset_id = str(body.get("assetID", "")).strip()
    upload_uri = str(body.get("uploadUri", "")).strip()
    if not asset_id or not upload_uri:
        raise AdobeApiError(
            "Asset upload-URI response missing assetID or uploadUri",
            status_code=response.status_code,
            request_id=response.headers.get("x-request-id"),
            url=endpoint,
            details={"response": body},
        )

    return {
        "asset_id": asset_id,
        "upload_uri": upload_uri,
        "request_id": response.headers.get("x-request-id"),
    }


def upload_asset_bytes(
    *,
    upload_uri: str,
    input_path: Path,
    media_type: str,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    data = input_path.read_bytes()

    response = _http_request(
        "PUT",
        upload_uri,
        headers={"Content-Type": media_type},
        data=data,
        timeout_seconds=timeout_seconds,
    )

    return {
        "status_code": response.status_code,
        "request_id": response.headers.get("x-request-id"),
        "bytes_uploaded": len(data),
    }


def submit_create_pdf_job(
    *,
    api_base_url: str,
    access_token: str,
    client_id: str,
    asset_id: str,
    document_language: str | None,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    endpoint = api_base_url.rstrip("/") + "/operation/createpdf"

    payload: dict[str, Any] = {"assetID": asset_id}
    if document_language:
        payload["documentLanguage"] = document_language

    response = _http_request(
        "POST",
        endpoint,
        headers={
            **_api_headers(access_token, client_id),
            "Content-Type": "application/json",
        },
        data=json.dumps(payload).encode("utf-8"),
        timeout_seconds=timeout_seconds,
    )

    location = response.headers.get("location", "").strip()
    if not location:
        raise AdobeApiError(
            "Create PDF response missing location header",
            status_code=response.status_code,
            request_id=response.headers.get("x-request-id"),
            body_excerpt=_sanitize_body_excerpt(response.body),
            url=endpoint,
        )

    if location.startswith("/"):
        location = api_base_url.rstrip("/") + location

    return {
        "location": location,
        "status_code": response.status_code,
        "request_id": response.headers.get("x-request-id"),
    }


def poll_create_pdf_job(
    *,
    location_url: str,
    access_token: str,
    client_id: str,
    poll_timeout_seconds: int,
    poll_interval_seconds: float,
    request_timeout_seconds: int = 60,
) -> dict[str, Any]:
    start = time.monotonic()
    attempts = 0
    last_status: dict[str, Any] | None = None

    while True:
        if time.monotonic() - start > poll_timeout_seconds:
            raise AdobeApiError(
                f"Polling timed out after {poll_timeout_seconds}s",
                url=location_url,
                details={"attempts": attempts, "last_status": last_status},
            )

        response = _http_request(
            "GET",
            location_url,
            headers=_api_headers(access_token, client_id),
            timeout_seconds=request_timeout_seconds,
        )

        try:
            body = json.loads(response.body.decode("utf-8"))
        except Exception as exc:
            raise AdobeApiError(
                "Job status endpoint returned non-JSON response",
                status_code=response.status_code,
                request_id=response.headers.get("x-request-id"),
                body_excerpt=_sanitize_body_excerpt(response.body),
                url=location_url,
            ) from exc

        attempts += 1
        last_status = body
        status = str(body.get("status", "")).strip().lower()

        if status == "done":
            asset = body.get("asset") or {}
            if not isinstance(asset, dict):
                raise AdobeApiError(
                    "Done status missing asset payload",
                    request_id=response.headers.get("x-request-id"),
                    url=location_url,
                    details={"response": body},
                )
            download_uri = str(asset.get("downloadUri", "")).strip()
            if not download_uri:
                raise AdobeApiError(
                    "Done status missing asset.downloadUri",
                    request_id=response.headers.get("x-request-id"),
                    url=location_url,
                    details={"response": body},
                )
            return {
                "status": "done",
                "asset": asset,
                "attempts": attempts,
                "request_id": response.headers.get("x-request-id"),
                "response": body,
            }

        if status == "failed":
            error_payload = body.get("error") if isinstance(body.get("error"), dict) else {}
            error_message = str(error_payload.get("message", "Adobe job failed")).strip() or "Adobe job failed"
            raise AdobeApiError(
                f"Adobe createpdf job failed: {error_message}",
                status_code=error_payload.get("status") if isinstance(error_payload.get("status"), int) else None,
                request_id=response.headers.get("x-request-id"),
                url=location_url,
                details={"job": body},
            )

        if status == "in progress":
            time.sleep(max(poll_interval_seconds, 0.1))
            continue

        raise AdobeApiError(
            f"Unexpected job status '{status or '<empty>'}'",
            request_id=response.headers.get("x-request-id"),
            url=location_url,
            details={"response": body},
        )


def download_asset(
    *,
    download_uri: str,
    output_path: Path,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    response = _http_request(
        "GET",
        download_uri,
        timeout_seconds=timeout_seconds,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.body)

    return {
        "bytes_written": len(response.body),
        "content_type": response.headers.get("content-type", ""),
        "request_id": response.headers.get("x-request-id"),
    }
