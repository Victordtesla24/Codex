# Adobe API Fallback

Use this path when Canva-first flow is unavailable/pending and API fallback is selected.

## Credential Source and Resolution
Default credentials file:
- `/Users/vics-macbook-pro/.codex/skills/.system/skill-creator/PDFServicesSDK/pdfservices-api-credentials.json`

Resolution order:
1. `--credentials-json`
2. `ADOBE_PDF_CREDENTIALS_JSON`
3. default credentials file above
4. env fallback:
   - `PDF_SERVICES_CLIENT_ID`, `PDF_SERVICES_CLIENT_SECRET`
   - `ADOBE_PDF_SERVICES_CLIENT_ID`, `ADOBE_PDF_SERVICES_CLIENT_SECRET`

## Router usage
```bash
python3 scripts/route_exec_renderer.py \
  --payload /tmp/executive_payload.json \
  --output /tmp/executive_brief.pdf \
  --renderer auto \
  --request-log /tmp/route_exec_log.json
```

Renderer behavior:
- `auto`: Canva pipeline first, Adobe API fallback second.
- `adobe-api`: direct API path.
- `adobe-connector`: produces connector prompt for manual ChatGPT connector run.

## Official REST Flow Used by Script
`adobe_api_render.py` live mode executes:
1. `POST https://pdf-services.adobe.io/token`
2. `POST https://pdf-services.adobe.io/assets`
3. upload source via returned `uploadUri`
4. `POST https://pdf-services.adobe.io/operation/createpdf`
5. poll `location` URL until terminal status
6. download output from `asset.downloadUri`

Headers for authenticated API calls:
- `Authorization: Bearer <access_token>`
- `x-api-key: <client_id>`

## Error handling
1. If credentials are missing, stop and surface exact missing keys/sources.
2. If token generation fails, capture HTTP status, `x-request-id`, and sanitized response excerpt.
3. If job polling times out, fail deterministically with last known status.
4. For live mode, only `--operation create-pdf` is supported in this rollout.
5. Always write request trace JSON next to the output for auditability.
