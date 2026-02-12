# C-Suite PDF: Custom GPT + API Agent Setup

This guide is optimized for your current workflow:
- Canva-first executive PDF generation
- Adobe fallback path
- Strict legal preflight gates before final delivery

## 0) Locked Runtime Contract

Do not downgrade or change these defaults:
1. Model: `gpt-5.2-pro` (latest Pro-tier in your environment)
2. Reasoning effort: `xhigh`

Apply this consistently in:
1. Custom GPT configuration
2. Stored prompt configuration
3. Any direct Responses API fallback calls

## 1) Prerequisites

1. API key and project access:
   - Key must include `api.responses.write`.
   - Recommended additional scope: `api.model.read`.
2. Model access and quota:
   - Your OpenAI project must have access to at least one text model you plan to use.
   - Billing/quota must be available (no `insufficient_quota`).
3. Prompt object availability:
   - Prompt IDs (`pmpt_...`) are project-scoped.
   - The key must target the same OpenAI project where the prompt was created.

## 2) Custom GPT (ChatGPT UI) Setup

Use this when you want non-technical users to run the workflow in ChatGPT directly.

1. Open ChatGPT GPT builder and create a new GPT.
2. Set model to `gpt-5.2-pro` and keep it fixed.
3. Set reasoning/thinking effort to `xhigh`.
4. In Instructions, paste:
   - `chatgpt/custom-gpt/instructions.md`
5. Upload knowledge files:
   - Entire folder: `chatgpt/custom-gpt/knowledge/`
6. Optional actions/connectors:
   - Add Adobe Acrobat connector for fallback export workflows.
   - Keep Canva handoff instructions in prompts/knowledge if connector is not available.
7. Set conversation starters, for example:
   - "Generate a board-ready legal executive PDF brief from this payload."
   - "Run strict legal preflight on this draft and return PASS/FAIL with fixes."
8. Save and publish to:
   - "Only me" for testing, then
   - Workspace/org as needed.

## 3) API Agent Setup (Responses + Stored Prompt)

Use this for automation and deterministic runs.

1. Create/confirm your stored prompt in Prompt Management.
2. Set the prompt/model defaults to `gpt-5.2-pro` with `reasoning.effort = "xhigh"`.
3. Record the prompt ID (`pmpt_...`) and optional version.
4. Run the local prompt tester:
   ```bash
   /Users/Shared/codex/legal-strategy-dashboard/scripts/chatgpt/test_prompt_id_responses.sh \
     --prompt-id pmpt_YOUR_ID
   ```
5. If it passes, wire the same prompt into your backend Responses API calls.
6. Add tool/function hooks for:
   - Canva runtime job assembly/handoff
   - Adobe fallback execution
   - Strict preflight enforcement
7. Enforce output contract in code:
   - `PASS`: final artifact only after all gates pass
   - `PENDING`: explicit handoff instructions
   - `FAIL`: explicit failed gates + remediation

Example direct Responses fallback payload:
```json
{
  "model": "gpt-5.2-pro",
  "reasoning": { "effort": "xhigh" },
  "input": "Generate C-suite legal PDF brief structure..."
}
```

## 4) Validation Checklist

1. Prompt test returns `HTTP 200`.
2. Output includes:
   - executive summary
   - citation placeholders/ids
   - strict preflight PASS/FAIL logic
3. For connector fallback mode:
   - handoff instructions are explicit and deterministic.
4. Final artifact is blocked when preflight fails.

## 5) Current Environment Diagnostics

Latest observed test outcomes:
1. Prompt call with `pmpt_698d735c4eb48196ae12f6fe30d79f270136a2d693c7dbc5` returned:
   - `404 Prompt not found` (likely wrong project or missing prompt).
2. Direct model call returned:
   - `429 insufficient_quota`.
3. Therefore, to complete live end-to-end validation:
   - ensure prompt exists in this API key's project
   - ensure project quota is available

## 6) References

1. Responses API: https://platform.openai.com/docs/api-reference/responses/create
2. Prompt management guide: https://platform.openai.com/docs/guides/prompt-management
3. Creating a GPT (ChatGPT): https://help.openai.com/en/articles/8554397-creating-a-gpt
