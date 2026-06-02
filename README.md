# Middag-app v15 – Vercel-ready

Dette er Vercel-versjonen av Middag-appen.

## Filer

- `index.html`
- `styles.css`
- `app.js`
- `api/*.py` – Vercel serverless functions
- `vercel.json`
- `.gitignore`

## Environment Variables i Vercel

Legg inn disse i Vercel → Project → Settings → Environment Variables:

```text
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4.1-mini
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=sb_secret_...
APP_ID=oyvind-melanie
```

Ikke legg `.env` i GitHub.

## Etter deploy

Test:

```text
https://DIN-APP.vercel.app/api/health
```

Du bør se:

```json
{"ok": true, "storage": "supabase", "ai": true}
```
