#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DAYS_BACK=3
EXCLUDE_POLICY="strict"
MANIFEST_DIR="${REPO_ROOT}/artifacts/cloud-sync"
REPO_URL="https://github.com/Victordtesla24/Codex.git"
BRANCH="main"
LAYOUT_ROOT=""
COMMIT_PREFIX="chore(cloud-sync): sync legal dashboard + skills"

usage() {
  cat <<'USAGE'
Usage: run_all.sh [options]

Options:
  --days-back <int>         Include files modified in the last N days (default: 3)
  --exclude-policy <value>  Exclusion policy: strict|none (default: strict)
  --manifest-dir <path>     Output dir for manifests and reports
  --repo-url <url>          Destination repository URL
  --branch <name>           Destination branch
  --layout-root <path>      Optional destination root prefix
  --commit-prefix <text>    Commit message prefix
  -h, --help                Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --days-back)
      DAYS_BACK="${2:-}"
      shift 2
      ;;
    --exclude-policy)
      EXCLUDE_POLICY="${2:-}"
      shift 2
      ;;
    --manifest-dir)
      MANIFEST_DIR="${2:-}"
      shift 2
      ;;
    --repo-url)
      REPO_URL="${2:-}"
      shift 2
      ;;
    --branch)
      BRANCH="${2:-}"
      shift 2
      ;;
    --layout-root)
      LAYOUT_ROOT="${2:-}"
      shift 2
      ;;
    --commit-prefix)
      COMMIT_PREFIX="${2:-}"
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

run_step() {
  local code="$1"
  local label="$2"
  shift 2
  echo "[run_all] ${label}"
  if ! "$@"; then
    echo "[run_all] FAILED (${label})" >&2
    exit "${code}"
  fi
}

run_step 10 "collect manifests" \
  "${SCRIPT_DIR}/collect_manifest.sh" \
    --days-back "${DAYS_BACK}" \
    --output-dir "${MANIFEST_DIR}" \
    --exclude-policy "${EXCLUDE_POLICY}"

run_step 20 "install global Codex skills" \
  "${SCRIPT_DIR}/install_global_codex_skills.sh"

run_step 30 "build ChatGPT pack" \
  "${REPO_ROOT}/scripts/chatgpt/build_chatgpt_pack.sh"

run_step 40 "push to Victordtesla24/Codex" \
  "${SCRIPT_DIR}/push_to_victordtesla24_codex.sh" \
    --repo-url "${REPO_URL}" \
    --branch "${BRANCH}" \
    --layout-root "${LAYOUT_ROOT}" \
    --manifest-dir "${MANIFEST_DIR}" \
    --commit-prefix "${COMMIT_PREFIX}"

sync_report="${MANIFEST_DIR}/sync_report.json"
if [[ -f "${sync_report}" ]]; then
  python3 - <<PY
import json
from pathlib import Path
path = Path("${sync_report}")
data = json.loads(path.read_text(encoding="utf-8"))
print("[run_all] push_status=", data.get("push_status"))
print("[run_all] commit_sha=", data.get("commit_sha"))
print("[run_all] files_copied=", data.get("files_copied"))
PY
fi

echo "[run_all] COMPLETE"
