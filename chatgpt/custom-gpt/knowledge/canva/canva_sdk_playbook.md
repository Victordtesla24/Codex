# Canva SDK Playbook

## Runtime model
- Use the Canva design editor intent bootstrap:
  - `prepareDesignEditor(...)`
  - `src/intents/design_editor/index.tsx`
- Do not rely on legacy `canva.init()` for this rollout.

## Local setup
1. Use Node 20 and npm 10 for the starter kit.
2. Keep starter-kit `.env` aligned to Portal Code Upload preview:
```bash
CANVA_FRONTEND_PORT=8080
CANVA_BACKEND_PORT=3001
CANVA_BACKEND_HOST=http://localhost:3001
CANVA_APP_ID=AAHAAJ2LL3A
CANVA_APP_ORIGIN=https://app-aahaaj2ll3a.canva-apps.com
CANVA_HMR_ENABLED=TRUE
```
3. Start preview server:
```bash
export PATH="/opt/homebrew/opt/node@20/bin:$PATH"
cd /Users/vics-macbook-pro/.codex/skills/.system/skill-creator/canva-apps-sdk-starter-kit
npm start
```
4. In Canva Developer Portal, set Development URL to `http://localhost:8080`.

## One-click export behavior
- App loads runtime job JSON.
- App applies mapped content to current design/template page.
- App calls `requestExport({ acceptedFileTypes: ["pdf_standard"] })`.
- User confirms export in active Canva session.
