# Environment Variables

## **Set these in Netlify site settings:**
* `AI_PROVIDER`: `openrouter` (default) or `gemini`
* `OPENROUTER_API_KEY`: required when `AI_PROVIDER=openrouter`
* `OPENROUTER_MODEL`: optional, default `openai/gpt-4.1-mini`
* `OPENROUTER_REFERER`: optional, default `https://legaldash.netlify.app`
* `GEMINI_API_KEY`: required when `AI_PROVIDER=gemini`
* `GEMINI_MODEL`: optional, default `gemini-1.5-pro`
* `LEGALDASH_STORE_DIR`: optional local path for serverless storage (defaults to `/tmp/legaldash-store`)

## **Notes:**
* Browser no longer stores provider API keys.
- `LEGALDASH_STORE_DIR` uses ephemeral storage in serverless contexts unless replaced by a managed datastore.

<!--stackedit_data:
eyJoaXN0b3J5IjpbLTE0MTA5Nzc0NTMsLTg4ODI0MjI4MSwtND
YwODk4MjA0LDExMzAxODAyNTRdfQ==
-->