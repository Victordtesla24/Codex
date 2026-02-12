#!/usr/bin/env python3
"""Build Canva app bundle and collect upload artifacts for Developer Portal."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED_ENV_KEYS = [
    "CANVA_FRONTEND_PORT",
    "CANVA_BACKEND_PORT",
    "CANVA_BACKEND_HOST",
    "CANVA_APP_ID",
    "CANVA_APP_ORIGIN",
    "CANVA_HMR_ENABLED",
]


def _run(cmd: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), env=env, text=True, capture_output=True, check=False)


def _preferred_node_bin() -> str | None:
    override = os.getenv("CANVA_NODE_BIN", "").strip()
    if override:
        candidate = Path(override)
        if candidate.exists() and (candidate / "node").exists() and (candidate / "npm").exists():
            return str(candidate)

    default_candidate = Path("/opt/homebrew/opt/node@20/bin")
    if default_candidate.exists() and (default_candidate / "node").exists() and (default_candidate / "npm").exists():
        return str(default_candidate)

    return None


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    preferred_bin = _preferred_node_bin()
    if preferred_bin:
        env["PATH"] = f"{preferred_bin}:{env.get('PATH', '')}"
    return env


def _overlay_source(app_source: Path, starter_kit: Path, backup_dir: Path) -> list[tuple[Path, bool]]:
    changes: list[tuple[Path, bool]] = []

    for source_file in sorted(app_source.rglob("*")):
        if not source_file.is_file():
            continue

        relative = source_file.relative_to(app_source)
        destination = starter_kit / relative
        existed = destination.exists()

        if existed:
            backup_target = backup_dir / relative
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, backup_target)

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination)
        changes.append((relative, existed))

    return changes


def _restore_source(starter_kit: Path, backup_dir: Path, changes: list[tuple[Path, bool]]) -> None:
    for relative, existed in reversed(changes):
        destination = starter_kit / relative

        if existed:
            backup_target = backup_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_target, destination)
            continue

        if destination.exists():
            destination.unlink()


def _read_version(output: str) -> str:
    return output.strip().splitlines()[0].strip() if output.strip() else ""


def _load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if " #" in value and not value.startswith('"') and not value.startswith("'"):
            value = value.split(" #", 1)[0].strip()

        if (
            len(value) >= 2
            and ((value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")))
        ):
            value = value[1:-1]

        values[key] = value

    return values


def _validate_dotenv(env_file: Path) -> dict[str, Any]:
    if not env_file.exists():
        return {
            "status": "error",
            "env_file": str(env_file),
            "missing_keys": REQUIRED_ENV_KEYS,
            "warnings": [],
            "errors": [f"Missing .env file at {env_file}"],
            "values": {},
        }

    values = _load_dotenv(env_file)
    missing = [key for key in REQUIRED_ENV_KEYS if not values.get(key, "").strip()]
    warnings: list[str] = []
    errors: list[str] = []

    if missing:
        errors.append("Missing required env keys: " + ", ".join(missing))

    frontend_port = values.get("CANVA_FRONTEND_PORT", "").strip()
    if frontend_port and frontend_port != "8080":
        warnings.append(
            f"CANVA_FRONTEND_PORT is {frontend_port}. Code Upload preview in the portal screenshot uses http://localhost:8080."
        )

    backend_host = values.get("CANVA_BACKEND_HOST", "").strip().lower()
    if backend_host.endswith(":8080") or backend_host.endswith(":8080/"):
        warnings.append("CANVA_BACKEND_HOST points to frontend port 8080. Use backend host http://localhost:3001 for local dev.")

    hmr_enabled = values.get("CANVA_HMR_ENABLED", "").strip().lower()
    app_origin = values.get("CANVA_APP_ORIGIN", "").strip()
    if hmr_enabled == "true" and not app_origin:
        warnings.append("CANVA_HMR_ENABLED is TRUE but CANVA_APP_ORIGIN is empty.")

    app_id = values.get("CANVA_APP_ID", "").strip()
    if app_id and app_origin and app_id.lower() not in app_origin.lower():
        warnings.append("CANVA_APP_ORIGIN does not appear to include CANVA_APP_ID; verify origin in Developer Portal credentials.")

    status = "ok"
    if errors:
        status = "error"
    elif warnings:
        status = "warning"

    return {
        "status": status,
        "env_file": str(env_file),
        "missing_keys": missing,
        "warnings": warnings,
        "errors": errors,
        "values": {
            "CANVA_FRONTEND_PORT": values.get("CANVA_FRONTEND_PORT", ""),
            "CANVA_BACKEND_PORT": values.get("CANVA_BACKEND_PORT", ""),
            "CANVA_BACKEND_HOST": values.get("CANVA_BACKEND_HOST", ""),
            "CANVA_APP_ID": values.get("CANVA_APP_ID", ""),
            "CANVA_APP_ORIGIN": values.get("CANVA_APP_ORIGIN", ""),
            "CANVA_HMR_ENABLED": values.get("CANVA_HMR_ENABLED", ""),
        },
    }


def _write_recommended_env(output_dir: Path, env_values: dict[str, str]) -> Path:
    lines = [
        "CANVA_FRONTEND_PORT=8080",
        "CANVA_BACKEND_PORT=3001",
        "CANVA_BACKEND_HOST=http://localhost:3001",
        f"CANVA_APP_ID={env_values.get('CANVA_APP_ID', '').strip() or 'REPLACE_WITH_APP_ID'}",
        f"CANVA_APP_ORIGIN={env_values.get('CANVA_APP_ORIGIN', '').strip() or 'REPLACE_WITH_APP_ORIGIN'}",
        f"CANVA_HMR_ENABLED={env_values.get('CANVA_HMR_ENABLED', '').strip() or 'TRUE'}",
    ]
    out = output_dir / "starter_kit_env_recommended.env"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Canva bundle and collect portal upload assets")
    parser.add_argument("--starter-kit", required=True, help="Path to canva-apps-sdk-starter-kit")
    parser.add_argument("--app-source", required=True, help="Path to app source overlay")
    parser.add_argument("--output-dir", required=True, help="Output directory for portal artifacts")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    starter_kit = Path(args.starter_kit).resolve()
    app_source = Path(args.app_source).resolve()
    output_dir = Path(args.output_dir).resolve()

    report: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "starter_kit": str(starter_kit),
        "app_source": str(app_source),
        "output_dir": str(output_dir),
        "steps": {},
    }

    if not starter_kit.exists():
        print(f"ERROR: Starter kit not found: {starter_kit}", file=sys.stderr)
        return 1
    if not (starter_kit / "package.json").exists():
        print(f"ERROR: Starter kit missing package.json: {starter_kit}", file=sys.stderr)
        return 1

    if not app_source.exists():
        print(f"ERROR: App source not found: {app_source}", file=sys.stderr)
        return 1
    if not (app_source / "src" / "index.tsx").exists():
        print(f"ERROR: App source missing src/index.tsx: {app_source}", file=sys.stderr)
        return 1
    if not (app_source / "canva-app.json").exists():
        print(f"ERROR: App source missing canva-app.json: {app_source}", file=sys.stderr)
        return 1
    if not (app_source / "config.json").exists():
        print(f"ERROR: App source missing config.json: {app_source}", file=sys.stderr)
        return 1

    env = _build_env()

    node_ver = _run(["node", "-v"], starter_kit, env)
    npm_ver = _run(["npm", "-v"], starter_kit, env)
    if node_ver.returncode != 0 or npm_ver.returncode != 0:
        print("ERROR: Unable to execute node/npm with current environment", file=sys.stderr)
        return 1

    node_version = _read_version(node_ver.stdout)
    npm_version = _read_version(npm_ver.stdout)
    report["runtime"] = {
        "node": node_version,
        "npm": npm_version,
    }

    if not node_version.startswith("v18") and not node_version.startswith("v20"):
        print(
            f"ERROR: Unsupported node runtime {node_version}. Use Node 18 or 20 for Canva starter kit.",
            file=sys.stderr,
        )
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    env_validation = _validate_dotenv(starter_kit / ".env")
    report["steps"]["env_validation"] = env_validation
    if env_validation["status"] == "error":
        report_path = output_dir / "build_report.json"
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("ERROR: .env validation failed. See build_report.json", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="canva_portal_bundle_backup_") as temp_dir:
        backup_dir = Path(temp_dir)
        changes: list[tuple[Path, bool]] = []

        try:
            changes = _overlay_source(app_source, starter_kit, backup_dir)
            report["steps"]["overlay"] = {
                "status": "ok",
                "files_overlaid": len(changes),
            }

            if not (starter_kit / "node_modules").exists():
                install = _run(["npm", "install"], starter_kit, env)
                report["steps"]["npm_install"] = {
                    "status": "ok" if install.returncode == 0 else "error",
                    "returncode": install.returncode,
                    "stdout": install.stdout[-2000:],
                    "stderr": install.stderr[-2000:],
                }
                if install.returncode != 0:
                    raise RuntimeError("npm install failed in starter kit")
            else:
                report["steps"]["npm_install"] = {"status": "skipped", "reason": "node_modules present"}

            build = _run(["npm", "run", "build"], starter_kit, env)
            report["steps"]["npm_build"] = {
                "status": "ok" if build.returncode == 0 else "error",
                "returncode": build.returncode,
                "stdout": build.stdout[-4000:],
                "stderr": build.stderr[-4000:],
            }
            if build.returncode != 0:
                raise RuntimeError("npm run build failed")

            artifact_map = {
                "app.js": starter_kit / "dist" / "app.js",
                "messages_en.json": starter_kit / "dist" / "messages_en.json",
                "canva-app.json": starter_kit / "canva-app.json",
                "config.json": starter_kit / "config.json",
            }

            copied: list[str] = []
            for name, source in artifact_map.items():
                if not source.exists():
                    raise RuntimeError(f"Required artifact missing after build: {source}")
                destination = output_dir / name
                shutil.copy2(source, destination)
                copied.append(str(destination))

            report["steps"]["collect_artifacts"] = {
                "status": "ok",
                "artifacts": copied,
            }

            recommended_env = _write_recommended_env(output_dir, env_validation.get("values", {}))
            report["steps"]["recommended_env"] = {
                "status": "ok",
                "path": str(recommended_env),
            }

            checklist = output_dir / "portal_upload_checklist.md"
            checklist.write_text(
                "\n".join(
                    [
                        "# Portal Upload Checklist",
                        "",
                        "1. In Canva Developer Portal, open app code upload page.",
                        "2. For local preview, set Development URL to http://localhost:8080.",
                        "3. For bundle upload, upload app.js.",
                        "4. Upload messages_en.json in Translations.",
                        "5. Confirm starter-kit .env uses frontend 8080 and backend host http://localhost:3001.",
                        "6. Confirm CANVA_APP_ID/CANVA_APP_ORIGIN match the Developer Portal credentials for this app.",
                        "7. For final JavaScript bundle submission, rebuild with CANVA_BACKEND_HOST set to a deployed HTTPS backend URL.",
                        "8. Confirm scopes match canva-app.json.",
                        "9. Verify bundle size and publish readiness.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            report_path = output_dir / "build_report.json"
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(f"Prepared portal bundle: {output_dir}")
            return 0

        except Exception as exc:
            report["error"] = str(exc)
            report_path = output_dir / "build_report.json"
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        finally:
            _restore_source(starter_kit, backup_dir, changes)


if __name__ == "__main__":
    raise SystemExit(main())
