#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

OUTPUT_ROOT="${REPO_ROOT}/chatgpt"
ADOBE_SKILL_ROOT="${REPO_ROOT}/Skills/adobe-csuite-pdf-skill"
CANVA_SKILL_ROOT="${CODEX_HOME:-$HOME/.codex}/skills/canva-csuite-pdf-skill"
REPORT_PATH="${REPO_ROOT}/artifacts/cloud-sync/chatgpt_pack_report.json"

usage() {
  cat <<'USAGE'
Usage: build_chatgpt_pack.sh [options]

Options:
  --output-root <path>       Output root for ChatGPT assets
  --adobe-skill-root <path>  Adobe skill source root
  --canva-skill-root <path>  Canva skill source root
  -h, --help                 Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-root)
      OUTPUT_ROOT="${2:-}"
      shift 2
      ;;
    --adobe-skill-root)
      ADOBE_SKILL_ROOT="${2:-}"
      shift 2
      ;;
    --canva-skill-root)
      CANVA_SKILL_ROOT="${2:-}"
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

for required_dir in "${ADOBE_SKILL_ROOT}" "${CANVA_SKILL_ROOT}"; do
  if [[ ! -d "${required_dir}" ]]; then
    echo "Missing required skill directory: ${required_dir}" >&2
    exit 1
  fi
done

custom_gpt_dir="${OUTPUT_ROOT}/custom-gpt"
knowledge_dir="${custom_gpt_dir}/knowledge"
adobe_knowledge_dir="${knowledge_dir}/adobe"
canva_knowledge_dir="${knowledge_dir}/canva"

mkdir -p "${custom_gpt_dir}" "${adobe_knowledge_dir}" "${canva_knowledge_dir}"

adobe_openai_yaml="${ADOBE_SKILL_ROOT}/agents/openai.yaml"
canva_openai_yaml="${CANVA_SKILL_ROOT}/agents/openai.yaml"

adobe_default_prompt="$(sed -n 's/.*default_prompt: "\(.*\)"/\1/p' "${adobe_openai_yaml}" | head -n1)"
canva_default_prompt="$(sed -n 's/.*default_prompt: "\(.*\)"/\1/p' "${canva_openai_yaml}" | head -n1)"

adobe_refs=(
  "input_schema.md"
  "chatgpt_connector_playbook.md"
  "strict_legal_quality_gates.md"
  "executive_layout_spec.md"
  "adobe_api_fallback.md"
)
canva_refs=(
  "canva_sdk_playbook.md"
  "template_enforcement.md"
  "placeholder_mapping.md"
  "portal_code_upload.md"
  "skill_chaining_contract.md"
)

for ref in "${adobe_refs[@]}"; do
  src="${ADOBE_SKILL_ROOT}/references/${ref}"
  if [[ -f "${src}" ]]; then
    cp "${src}" "${adobe_knowledge_dir}/${ref}"
  fi
done

for ref in "${canva_refs[@]}"; do
  src="${CANVA_SKILL_ROOT}/references/${ref}"
  if [[ -f "${src}" ]]; then
    cp "${src}" "${canva_knowledge_dir}/${ref}"
  fi
done

cat > "${custom_gpt_dir}/README.md" <<EOF
# ChatGPT Custom GPT Pack: Legal Strategy C-Suite PDF

## What this pack provides
- Canva-first C-suite PDF generation workflow.
- Adobe fallback path when Canva export is unavailable.
- Strict legal preflight gating before any final delivery.

## Files in this pack
- \`instructions.md\`: System instructions for the Custom GPT.
- \`knowledge/\`: Supporting references from Adobe and Canva skill assets.

## Setup in ChatGPT
1. Create a new Custom GPT.
2. Paste \`instructions.md\` into the GPT Instructions section.
3. Upload key files from \`knowledge/\` as GPT knowledge.
4. Optionally configure actions/connectors used by your organization.
5. Validate behavior using a sample executive payload.
EOF

cat > "${custom_gpt_dir}/instructions.md" <<EOF
# Role
You are a legal-executive PDF orchestration assistant for C-suite and board-ready outputs.

# Core Routing Contract
1. Route executive/legal PDF requests through Canva-first processing.
2. Use Adobe connector/API fallback when Canva path is unavailable, pending, or explicitly bypassed.
3. Do not deliver a final artifact unless strict legal preflight passes.

# Mandatory Quality Gates
1. Require privilege/confidentiality markers in output text.
2. Preserve required citations and section order.
3. Reject unresolved redaction markers and forbidden metadata patterns.
4. Block final output when any gate fails; return remediation steps.

# Prompt Anchors
- Adobe skill default prompt:
  ${adobe_default_prompt}
- Canva skill default prompt:
  ${canva_default_prompt}

# Output Contract
- For success: return final artifact status, path/location, and gate result = PASS.
- For pending: return status = PENDING plus explicit handoff steps.
- For failure: return status = FAIL plus precise failed gates and next actions.
EOF

cat > "${knowledge_dir}/index.md" <<EOF
# Knowledge Index

## Adobe references
$(for ref in "${adobe_refs[@]}"; do if [[ -f "${adobe_knowledge_dir}/${ref}" ]]; then echo "- adobe/${ref}"; fi; done)

## Canva references
$(for ref in "${canva_refs[@]}"; do if [[ -f "${canva_knowledge_dir}/${ref}" ]]; then echo "- canva/${ref}"; fi; done)
EOF

cat > "${OUTPUT_ROOT}/account-custom-instructions.md" <<'EOF'
# ChatGPT Account Custom Instructions (Recommended)

When handling legal or executive PDF requests:
1. Prioritize Canva-first C-suite PDF flow.
2. Use Adobe fallback only if Canva path is blocked or unavailable.
3. Enforce strict legal preflight checks before final delivery.
4. Return explicit PASS/PENDING/FAIL status with concise reason.

Never mark delivery complete if legal preflight has unresolved failures.
EOF

python3 - <<PY
import json
from pathlib import Path

output_root = Path("${OUTPUT_ROOT}")
files_generated = sorted(
    str(p)
    for p in output_root.rglob("*")
    if p.is_file()
)
required_files = [
    output_root / "custom-gpt" / "README.md",
    output_root / "custom-gpt" / "instructions.md",
    output_root / "account-custom-instructions.md",
]
status = "PASS" if all(p.exists() for p in required_files) else "FAIL"

report = {
    "timestamp_utc": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    "output_root": str(output_root),
    "files_generated": files_generated,
    "source_inputs": {
        "adobe_openai_yaml": "${adobe_openai_yaml}",
        "canva_openai_yaml": "${canva_openai_yaml}",
        "adobe_references_root": "${ADOBE_SKILL_ROOT}/references",
        "canva_references_root": "${CANVA_SKILL_ROOT}/references",
    },
    "validation_status": status,
}
report_path = Path("${REPORT_PATH}")
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, indent=2) + "\\n", encoding="utf-8")
PY

echo "ChatGPT pack created at: ${OUTPUT_ROOT}"
echo "Report: ${REPORT_PATH}"
