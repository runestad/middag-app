# MatplanApp workflow

## What the user does

Describe the desired change in the MatplanApp ChatGPT project.

ChatGPT can turn the request into a precise implementation brief when useful. Codex then works directly in this repository.

## What Codex does

Codex should complete the full delivery loop:

```text
Inspect current app
→ implement the requested change
→ run syntax/API/UI checks
→ review the diff
→ commit
→ push to origin/main
→ wait for/check Vercel
→ report the live result
```

The user should normally only need to refresh the deployed app after Codex confirms that Vercel is ready.

## Repository identity

- GitHub: `runestad/middag-app`
- Primary branch: `main`
- Local remote: `origin`
- Hosting: Vercel, automatically deployed from `main`
- Database: Supabase
- AI parsing: OpenAI API through server-side Vercel functions

## Task brief template

Use this format when passing a request to Codex:

```text
Work in the MatplanApp repository.

Goal:
<what should change for the user>

Current problem:
<what happens now>

Acceptance criteria:
- <observable result 1>
- <observable result 2>
- No regression to <important existing flow>

Safety:
- Preserve existing Supabase data.
- Do not run bulk database mutations.
- Do not expose or commit secrets.

Delivery:
- Implement and test the change.
- Commit and push to origin/main.
- Verify the Vercel deployment.
- Return the commit SHA, checks run, and live deployment status.
```

## Environment variables

Production values live in Vercel and must include the variables used by the API functions, currently:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `APP_ID`

Codex should verify names from the code and Vercel configuration when changing integrations. Secret values must never be copied into GitHub.

