# Canva Portal Code Upload

## Build artifacts
Run:
```bash
python3 scripts/prepare_canva_portal_bundle.py \
  --starter-kit /Users/vics-macbook-pro/.codex/skills/.system/skill-creator/canva-apps-sdk-starter-kit \
  --app-source assets/canva_app \
  --output-dir assets/portal_upload
```

Expected files in `assets/portal_upload`:
- `app.js`
- `messages_en.json`
- `canva-app.json`
- `config.json`
- `build_report.json`
- `starter_kit_env_recommended.env`

## Developer Portal steps
1. Open app in Canva Developer Portal.
2. Verify starter-kit `.env`:
```bash
CANVA_FRONTEND_PORT=8080
CANVA_BACKEND_PORT=3001
CANVA_BACKEND_HOST=http://localhost:3001
CANVA_APP_ID=AAHAAJ2LL3A
CANVA_APP_ORIGIN=https://app-aahaaj2ll3a.canva-apps.com
CANVA_HMR_ENABLED=TRUE
```
These values match the app URL pattern in the portal screenshot and keep frontend/backend routing correct.
For final JavaScript bundle submission, rebuild with `CANVA_BACKEND_HOST` set to your deployed HTTPS backend URL (not localhost).
3. In Code upload:
   - Use Development URL `http://localhost:8080` for local preview, or
   - Upload `app.js` under JavaScript bundle/file.
4. Upload `messages_en.json` under Translations.
5. Confirm scopes in manifest align with portal Scopes page.
6. Validate bundle is a single JS file and within size constraints.
