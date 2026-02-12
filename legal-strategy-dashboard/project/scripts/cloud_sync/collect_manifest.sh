#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DAYS_BACK=3
OUTPUT_DIR="${REPO_ROOT}/artifacts/cloud-sync"
EXCLUDE_POLICY="strict"
CANVA_SKILL_ROOT="${CODEX_HOME:-$HOME/.codex}/skills/canva-csuite-pdf-skill"

usage() {
  cat <<'USAGE'
Usage: collect_manifest.sh [options]

Options:
  --days-back <int>         Include files modified in the last N days (default: 3)
  --output-dir <path>       Output directory for manifests
  --exclude-policy <value>  Exclusion policy: strict|none (default: strict)
  -h, --help                Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --days-back)
      DAYS_BACK="${2:-}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --exclude-policy)
      EXCLUDE_POLICY="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! [[ "${DAYS_BACK}" =~ ^[0-9]+$ ]]; then
  echo "--days-back must be a non-negative integer" >&2
  exit 1
fi

case "${EXCLUDE_POLICY}" in
  strict|none) ;;
  *)
    echo "--exclude-policy must be 'strict' or 'none'" >&2
    exit 1
    ;;
esac

mkdir -p "${OUTPUT_DIR}"

PROJECT_MANIFEST="${OUTPUT_DIR}/manifest_project.txt"
ADOBE_MANIFEST="${OUTPUT_DIR}/manifest_adobe_skill.txt"
CANVA_MANIFEST="${OUTPUT_DIR}/manifest_canva_skill.txt"
SUMMARY_JSON="${OUTPUT_DIR}/manifest_summary.json"

should_skip_common() {
  local rel="$1"
  case "${rel}" in
    .DS_Store|*/.DS_Store|*.pyc|*.pyo|*.pyd) return 0 ;;
    */__pycache__/*) return 0 ;;
  esac
  return 1
}

should_skip_project_strict() {
  local rel="$1"
  case "${rel}" in
    .git/*|Skills/*|artifacts/cloud-sync/*|chatgpt/*) return 0 ;;
    test-results/*|learning/raw/*|learning/normalized/*|learning/analysis/*) return 0 ;;
    .netlify/state.json) return 0 ;;
    learning/state/*)
      if [[ "${rel}" != learning/state/run_manifest_*.json ]]; then
        return 0
      fi
      ;;
  esac
  return 1
}

collect_manifest() {
  local source_root="$1"
  local manifest_path="$2"
  local mode="$3"
  : > "${manifest_path}"

  if [[ ! -d "${source_root}" ]]; then
    echo "WARN: source root does not exist, writing empty manifest: ${source_root}" >&2
    return 0
  fi

  local mtime_pred=("-mtime" "-${DAYS_BACK}")
  if [[ "${DAYS_BACK}" -eq 0 ]]; then
    # "0 days back" is interpreted as "all files" to avoid an empty set edge case.
    mtime_pred=()
  fi

  while IFS= read -r -d '' abs_path; do
    local rel="${abs_path#${source_root}/}"

    if should_skip_common "${rel}"; then
      continue
    fi

    if [[ "${EXCLUDE_POLICY}" == "strict" && "${mode}" == "project" ]]; then
      if should_skip_project_strict "${rel}"; then
        continue
      fi
    fi

    printf '%s\n' "${rel}"
  done < <(find "${source_root}" -type f "${mtime_pred[@]}" -print0) | LC_ALL=C sort -u > "${manifest_path}"
}

collect_manifest "${REPO_ROOT}" "${PROJECT_MANIFEST}" "project"
collect_manifest "${REPO_ROOT}/Skills/adobe-csuite-pdf-skill" "${ADOBE_MANIFEST}" "skill"
collect_manifest "${CANVA_SKILL_ROOT}" "${CANVA_MANIFEST}" "skill"

python3 - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path
summary = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "days_back": int("${DAYS_BACK}"),
    "exclude_policy": "${EXCLUDE_POLICY}",
    "manifests": {
        "project": {
            "path": "${PROJECT_MANIFEST}",
            "count": sum(1 for _ in Path("${PROJECT_MANIFEST}").open("r", encoding="utf-8"))
        },
        "adobe_skill": {
            "path": "${ADOBE_MANIFEST}",
            "count": sum(1 for _ in Path("${ADOBE_MANIFEST}").open("r", encoding="utf-8"))
        },
        "canva_skill": {
            "path": "${CANVA_MANIFEST}",
            "count": sum(1 for _ in Path("${CANVA_MANIFEST}").open("r", encoding="utf-8"))
        },
    },
}
Path("${SUMMARY_JSON}").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
PY

echo "Wrote manifests:"
echo "  ${PROJECT_MANIFEST}"
echo "  ${ADOBE_MANIFEST}"
echo "  ${CANVA_MANIFEST}"
echo "Summary: ${SUMMARY_JSON}"
