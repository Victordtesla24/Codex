#!/usr/bin/env bash
set -euo pipefail

PROMPT_ID=""
OUTPUT_DIR="/Users/Shared/codex/legal-strategy-dashboard/artifacts/chatgpt-tests"
INPUT_TEXT="Generate a C-suite executive legal PDF brief structure with strict legal preflight PASS/FAIL checklist, citation placeholders, and delivery status."
ENV_FILE="/Users/Shared/codex/legal-strategy-dashboard/.env.prompt-test"

usage() {
  cat <<'USAGE'
Usage: test_prompt_id_responses.sh --prompt-id <pmpt_id> [options]

Options:
  --prompt-id <id>      Prompt ID (pmpt_...)
  --input-text <text>   Input text to send
  --output-dir <path>   Output directory for reports
  --env-file <path>     Environment file path (default: .env.prompt-test)
  -h, --help            Show help

Env:
  OPENAI_API_KEY        Required, must include responses.write scope
  OPENAI_ORG            Optional organization ID header
  OPENAI_PROJECT        Optional project ID header
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prompt-id)
      PROMPT_ID="${2:-}"
      shift 2
      ;;
    --input-text)
      INPUT_TEXT="${2:-}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --env-file)
      ENV_FILE="${2:-}"
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

if [[ -z "${PROMPT_ID}" ]]; then
  echo "--prompt-id is required" >&2
  exit 1
fi

# Load environment file if present.
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY is not set. Export a key with responses.write scope." >&2
  exit 1
fi

if [[ "${OPENAI_API_KEY}" =~ ^(your_|YOUR_|changeme|CHANGE_ME|<) ]]; then
  echo "OPENAI_API_KEY appears to be a placeholder. Populate ${ENV_FILE} with a real key." >&2
  exit 1
fi

api_headers=(
  -H "Authorization: Bearer ${OPENAI_API_KEY}"
  -H "Content-Type: application/json"
)
if [[ -n "${OPENAI_ORG:-}" ]]; then
  api_headers+=(-H "OpenAI-Organization: ${OPENAI_ORG}")
fi
if [[ -n "${OPENAI_PROJECT:-}" ]]; then
  api_headers+=(-H "OpenAI-Project: ${OPENAI_PROJECT}")
fi

extract_missing_scopes() {
  local response_file="$1"
  python3 - "${response_file}" <<'PY'
import json, pathlib, re, sys
p = pathlib.Path(sys.argv[1])
if not p.exists():
    print("")
    raise SystemExit(0)
raw = p.read_text(encoding="utf-8", errors="replace")
try:
    msg = str((json.loads(raw) or {}).get("error", {}).get("message", ""))
except Exception:
    msg = raw
m = re.search(r"Missing scopes:\s*([A-Za-z0-9._,\-]+)", msg)
print(m.group(1).strip() if m else "")
PY
}

preflight_scope_check() {
  local models_resp="/tmp/openai_scope_models.json"
  local responses_resp="/tmp/openai_scope_responses.json"
  local models_code responses_code missing

  models_code="$(curl -sS -o "${models_resp}" -w '%{http_code}' \
    https://api.openai.com/v1/models \
    "${api_headers[@]}" || true)"

  responses_code="$(curl -sS -o "${responses_resp}" -w '%{http_code}' \
    https://api.openai.com/v1/responses \
    "${api_headers[@]}" \
    --data '{}' || true)"

  case "${responses_code}" in
    2*|400|422)
      ;;
    *)
    missing="$(extract_missing_scopes "${responses_resp}")"
    if [[ -n "${missing}" ]]; then
      echo "Scope check failed for /v1/responses. Missing scopes: ${missing}" >&2
    else
      echo "Scope check failed for /v1/responses (HTTP ${responses_code})." >&2
    fi
    echo "Ensure your key has at least: api.responses.write" >&2
    exit 1
      ;;
  esac

  if ! [[ "${models_code}" =~ ^2 ]]; then
    missing="$(extract_missing_scopes "${models_resp}")"
    if [[ "${missing}" == *"api.model.read"* ]]; then
      echo "Warning: key missing api.model.read scope. Responses test can still run." >&2
    fi
  fi
}

preflight_scope_check

mkdir -p "${OUTPUT_DIR}"

req_json="/tmp/test_prompt_req_${PROMPT_ID}.json"
resp_json="/tmp/test_prompt_resp_${PROMPT_ID}.json"
report_json="${OUTPUT_DIR}/test_${PROMPT_ID}.json"

cat > "${req_json}" <<JSON
{"prompt":{"id":"${PROMPT_ID}"},"input":"${INPUT_TEXT}"}
JSON

http_code="$(curl -sS -o "${resp_json}" -w '%{http_code}' \
  https://api.openai.com/v1/responses \
  "${api_headers[@]}" \
  --data @"${req_json}" || true)"

export REPORT_JSON="${report_json}"
export REQ_JSON="${req_json}"
export RESP_JSON="${resp_json}"
export PROMPT_ID
export HTTP_CODE="${http_code}"
export ENV_FILE

python3 - <<'PY'
import json, os
from datetime import datetime, timezone
from pathlib import Path

report_path = Path(os.environ["REPORT_JSON"])
req_path = Path(os.environ["REQ_JSON"])
resp_path = Path(os.environ["RESP_JSON"])
prompt_id = os.environ["PROMPT_ID"]
http_code = os.environ.get("HTTP_CODE", "").strip()

report = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "prompt_id": prompt_id,
    "env_file": os.environ.get("ENV_FILE", ""),
    "request": json.loads(req_path.read_text(encoding="utf-8")),
    "http_status": int(http_code) if http_code.isdigit() else http_code,
}

payload_raw = resp_path.read_text(encoding="utf-8", errors="replace") if resp_path.exists() else ""
try:
    payload = json.loads(payload_raw) if payload_raw.strip() else {}
except Exception:
    payload = {"raw": payload_raw}

report["response"] = payload
report["status"] = "PASS" if str(report["http_status"]).startswith("2") else "FAILED"

output_text = ""
if isinstance(payload, dict):
    output_text = payload.get("output_text", "") or ""
    if not output_text:
      for item in payload.get("output", []) or []:
          if item.get("type") == "message":
              for content in item.get("content", []) or []:
                  if content.get("type") in {"output_text", "text"}:
                      output_text += content.get("text", "")

report["extracted_output_text"] = output_text

report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(f"Report: {report_path}")
print(f"Status: {report['status']}")
print(f"HTTP: {report['http_status']}")
if output_text:
    print("Output preview:")
    print(output_text[:1200])
PY
