#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

REPO_URL="https://github.com/Victordtesla24/Codex.git"
BRANCH="main"
LAYOUT_ROOT=""
MANIFEST_DIR="${REPO_ROOT}/artifacts/cloud-sync"
COMMIT_PREFIX="chore(cloud-sync): sync legal dashboard + skills"

CANVA_SKILL_ROOT="${CODEX_HOME:-$HOME/.codex}/skills/canva-csuite-pdf-skill"
CHATGPT_SOURCE_ROOT="${REPO_ROOT}/chatgpt"

usage() {
  cat <<'USAGE'
Usage: push_to_victordtesla24_codex.sh [options]

Options:
  --repo-url <url>        Destination repository URL
  --branch <name>         Destination branch (default: main)
  --layout-root <path>    Optional prefix path in destination repo root
  --manifest-dir <path>   Directory containing manifest_*.txt files
  --commit-prefix <text>  Commit message prefix
  -h, --help              Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
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
    --manifest-dir)
      MANIFEST_DIR="${2:-}"
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

PROJECT_MANIFEST="${MANIFEST_DIR}/manifest_project.txt"
ADOBE_MANIFEST="${MANIFEST_DIR}/manifest_adobe_skill.txt"
CANVA_MANIFEST="${MANIFEST_DIR}/manifest_canva_skill.txt"
SYNC_REPORT="${MANIFEST_DIR}/sync_report.json"

for required in "${PROJECT_MANIFEST}" "${ADOBE_MANIFEST}" "${CANVA_MANIFEST}"; do
  if [[ ! -f "${required}" ]]; then
    echo "Missing manifest file: ${required}" >&2
    exit 1
  fi
done

tmpdir="$(mktemp -d /tmp/victordtesla24-codex-sync-XXXXXX)"
cleanup() {
  rm -rf "${tmpdir}"
}
trap cleanup EXIT

git clone --branch "${BRANCH}" --single-branch "${REPO_URL}" "${tmpdir}/repo" >/dev/null 2>&1
dest_repo="${tmpdir}/repo"

if [[ -n "${LAYOUT_ROOT}" ]]; then
  base_dest="${dest_repo}/${LAYOUT_ROOT#/}"
else
  base_dest="${dest_repo}"
fi

dest_project="${base_dest}/legal-strategy-dashboard/project"
dest_adobe="${base_dest}/skills/adobe-csuite-pdf-skill"
dest_canva="${base_dest}/skills/canva-csuite-pdf-skill"
dest_chatgpt="${base_dest}/chatgpt"

rm -rf "${dest_project}" "${dest_adobe}" "${dest_canva}" "${dest_chatgpt}"
mkdir -p "${dest_project}" "${dest_adobe}" "${dest_canva}" "${dest_chatgpt}"

if [[ -s "${PROJECT_MANIFEST}" ]]; then
  rsync -a --files-from="${PROJECT_MANIFEST}" "${REPO_ROOT}/" "${dest_project}/"
fi
if [[ -s "${ADOBE_MANIFEST}" ]]; then
  rsync -a --files-from="${ADOBE_MANIFEST}" "${REPO_ROOT}/Skills/adobe-csuite-pdf-skill/" "${dest_adobe}/"
fi
if [[ -s "${CANVA_MANIFEST}" ]]; then
  rsync -a --files-from="${CANVA_MANIFEST}" "${CANVA_SKILL_ROOT}/" "${dest_canva}/"
fi
if [[ -d "${CHATGPT_SOURCE_ROOT}" ]]; then
  rsync -a \
    --exclude '.DS_Store' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    "${CHATGPT_SOURCE_ROOT}/" "${dest_chatgpt}/"
fi

pushd "${dest_repo}" >/dev/null

git add -A

changed_file_list="$(git diff --cached --name-only | sed '/^\s*$/d')"
changed_files="$(printf '%s\n' "${changed_file_list}" | sed '/^\s*$/d' | wc -l | tr -d ' ')"
project_count="$(grep -c . "${PROJECT_MANIFEST}" 2>/dev/null || true)"
adobe_count="$(grep -c . "${ADOBE_MANIFEST}" 2>/dev/null || true)"
canva_count="$(grep -c . "${CANVA_MANIFEST}" 2>/dev/null || true)"
chatgpt_count="$(find "${CHATGPT_SOURCE_ROOT}" -type f \
  ! -name '.DS_Store' ! -name '*.pyc' ! -path '*/__pycache__/*' 2>/dev/null | wc -l | tr -d ' ')"
selected_total="$((project_count + adobe_count + canva_count + chatgpt_count))"

commit_sha="$(git rev-parse HEAD)"
push_status="NO_CHANGES"
commit_message=""
push_error=""

if [[ "${changed_files}" -gt 0 ]]; then
  git config user.name "${GIT_AUTHOR_NAME:-Codex Cloud Sync Bot}"
  git config user.email "${GIT_AUTHOR_EMAIL:-codex-sync-bot@users.noreply.github.com}"
  commit_message="${COMMIT_PREFIX} $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  git commit -m "${commit_message}" >/dev/null
  commit_sha="$(git rev-parse HEAD)"
  if GIT_TERMINAL_PROMPT=0 git push origin "${BRANCH}" >/dev/null 2>&1; then
    push_status="PUSHED"
  else
    push_status="PUSH_FAILED"
    push_error="git push failed. Check credential helper / repo permissions."
  fi
fi

popd >/dev/null

python3 - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path
changed = [line.strip() for line in """${changed_file_list}""".splitlines() if line.strip()]
selected_total = int("${selected_total}")
changed_files = int("${changed_files}")
report = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "repo_url": "${REPO_URL}",
    "branch": "${BRANCH}",
    "layout_root": "${LAYOUT_ROOT}",
    "manifests": {
        "project": "${PROJECT_MANIFEST}",
        "adobe_skill": "${ADOBE_MANIFEST}",
        "canva_skill": "${CANVA_MANIFEST}",
    },
    "files_selected": selected_total,
    "files_copied": changed_files,
    "files_skipped": max(selected_total - changed_files, 0),
    "commit_sha": "${commit_sha}",
    "commit_message": "${commit_message}",
    "push_status": "${push_status}",
    "push_error": "${push_error}",
    "changed_files": changed,
}
Path("${SYNC_REPORT}").parent.mkdir(parents=True, exist_ok=True)
Path("${SYNC_REPORT}").write_text(json.dumps(report, indent=2) + "\\n", encoding="utf-8")
PY

echo "Sync report: ${SYNC_REPORT}"
echo "Push status: ${push_status}"
if [[ "${push_status}" == "PUSH_FAILED" ]]; then
  exit 1
fi
