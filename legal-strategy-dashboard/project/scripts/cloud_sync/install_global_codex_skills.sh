#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

SOURCE_ADOBE_SKILL="${REPO_ROOT}/Skills/adobe-csuite-pdf-skill"
GLOBAL_SKILLS_ROOT="${CODEX_HOME:-$HOME/.codex}/skills"
CANVA_SKILL_NAME="canva-csuite-pdf-skill"
ADOBE_SKILL_NAME="adobe-csuite-pdf-skill"
REPORT_PATH="${REPO_ROOT}/artifacts/cloud-sync/global_skill_install_report.json"

usage() {
  cat <<'USAGE'
Usage: install_global_codex_skills.sh [options]

Options:
  --source-adobe-skill <path>  Source path for adobe-csuite-pdf-skill
  --global-skills-root <path>  Global Codex skills root path
  --report-path <path>         JSON report output path
  -h, --help                   Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-adobe-skill)
      SOURCE_ADOBE_SKILL="${2:-}"
      shift 2
      ;;
    --global-skills-root)
      GLOBAL_SKILLS_ROOT="${2:-}"
      shift 2
      ;;
    --report-path)
      REPORT_PATH="${2:-}"
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

if [[ ! -d "${SOURCE_ADOBE_SKILL}" ]]; then
  echo "Source Adobe skill does not exist: ${SOURCE_ADOBE_SKILL}" >&2
  exit 1
fi

mkdir -p "${GLOBAL_SKILLS_ROOT}"
dest_adobe="${GLOBAL_SKILLS_ROOT}/${ADOBE_SKILL_NAME}"
mkdir -p "${dest_adobe}"

# Non-destructive merge: update/add files without deleting unknown destination files.
rsync -a \
  --exclude '.DS_Store' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "${SOURCE_ADOBE_SKILL}/" "${dest_adobe}/"

adobe_skill_md="${dest_adobe}/SKILL.md"
canva_skill_md="${GLOBAL_SKILLS_ROOT}/${CANVA_SKILL_NAME}/SKILL.md"

adobe_ok="false"
canva_ok="false"
[[ -f "${adobe_skill_md}" ]] && adobe_ok="true"
[[ -f "${canva_skill_md}" ]] && canva_ok="true"

if [[ "${adobe_ok}" != "true" ]]; then
  echo "Verification failed: ${adobe_skill_md} not found" >&2
  exit 1
fi
if [[ "${canva_ok}" != "true" ]]; then
  echo "Verification failed: ${canva_skill_md} not found" >&2
  exit 1
fi

python3 - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path
report = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "source_adobe_skill": "${SOURCE_ADOBE_SKILL}",
    "global_skills_root": "${GLOBAL_SKILLS_ROOT}",
    "installed_skills": {
        "adobe-csuite-pdf-skill": {
            "path": "${dest_adobe}",
            "skill_md_exists": True,
        },
        "canva-csuite-pdf-skill": {
            "path": "${GLOBAL_SKILLS_ROOT}/${CANVA_SKILL_NAME}",
            "skill_md_exists": True,
        },
    },
    "status": "PASS",
}
report_path = Path("${REPORT_PATH}")
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, indent=2) + "\\n", encoding="utf-8")
PY

echo "Global skill install verification passed."
echo "Report: ${REPORT_PATH}"
