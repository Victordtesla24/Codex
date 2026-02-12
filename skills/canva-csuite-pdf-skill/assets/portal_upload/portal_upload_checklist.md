# Portal Upload Checklist

1. In Canva Developer Portal, open app code upload page.
2. For local preview, set Development URL to http://localhost:8080.
3. For bundle upload, upload app.js.
4. Upload messages_en.json in Translations.
5. Confirm starter-kit .env uses frontend 8080 and backend host http://localhost:3001.
6. Confirm CANVA_APP_ID/CANVA_APP_ORIGIN match the Developer Portal credentials for this app.
7. For final JavaScript bundle submission, rebuild with CANVA_BACKEND_HOST set to a deployed HTTPS backend URL.
8. Confirm scopes match canva-app.json.
9. Verify bundle size and publish readiness.
