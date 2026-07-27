# Codex working agreement

This repository is the single source of truth for MatplanApp (`runestad/middag-app`).

## Standard workflow

For every requested code change:

1. Read the relevant code and reproduce or understand the current behavior.
2. Preserve unrelated behavior and user data.
3. Implement the smallest coherent fix.
4. Run the checks below.
5. Review the diff for secrets, generated files, and accidental regressions.
6. Commit to `main` with a clear message.
7. Push to `origin/main`.
8. Verify the pushed commit and its Vercel deployment status.
9. Report the commit SHA, tests run, and deployment result.

If a push or deployment check fails, diagnose and fix it before declaring the task complete.

## Required checks

Run at minimum:

```bash
node --check app.js
python3 -m py_compile api/*.py
git diff --check
```

For UI changes, also run the app locally and verify the affected flow at both desktop and iPhone-sized viewports when browser tooling is available.

For API changes, exercise the affected endpoint locally or through a safe deployed read-only check when practical.

## Data safety

Supabase production data is user data. Never run broad migrations, cleanup scripts, destructive SQL, or bulk recipe rewrites without all of the following:

1. A fresh export/backup.
2. A dry-run or generated diff.
3. A reviewable sample of at least 10 representative rows.
4. Explicit user approval for the exact mutation.
5. A rollback plan.

Do not infer missing recipe ingredients or overwrite non-empty recipe fields during cleanup. Prefer narrowly targeted updates.

## Secrets

- Never commit `.env` files, OpenAI keys, Supabase secret/service-role keys, or Vercel secrets.
- Keep production secrets in Vercel environment variables.
- Do not print secret values in logs or responses.

## Repository hygiene

- Work from the repository root, not from old versioned ZIP/build folders.
- Do not add new `middag_app_vXX` directories.
- Edit the current root files in place.
- Keep `vercel.json` compatible with Vercel's detected Python runtime; do not add a pinned function runtime unless verified against current Vercel support.
- Do not commit `__pycache__`, local backups, exports, or temporary database files.

## Deployment

`origin/main` is connected to Vercel production deployment. A successful push is not sufficient by itself: confirm the commit receives a successful Vercel status before reporting completion.

