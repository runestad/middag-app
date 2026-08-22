# MatplanApp — Final production data completion report

Date: 22 August 2026  
Repository: `runestad/middag-app`  
Final commit: `9583e4d`  
Production deployment status: successful

## Executive summary

This pass strengthened recipe recovery, audited the repository recipe library, separated stored recipe completeness from source retrievability, added an in-app manual-review queue, added library-aware Pantry suggestions, reconciled the app against the historical original recipe list, and restored the two recipes missing from that list.

The deployed application code now contains 230 recipes, matching the reconstructed 230-entry historical set. Existing recipe names were not automatically changed.

Production Supabase credentials were not available in the local environment, and the Vercel deployment was protected from unauthenticated direct inspection. Consequently, database mutations were not claimed from local evidence. A deployed, idempotent server-side synchronization path inserts the two missing originals when the app loads and only when their exact original content URLs are absent. Direct post-write inspection of those production rows remains outstanding.

The principal remaining limitation is recipe content: the persisted repository snapshot contains 207 incomplete recipes. The public-source audit found recoverable metadata for many recipes, but those candidates were deliberately not written to the repository fixture or reported as production repairs.

## Dataset boundaries

Three different datasets were kept distinct:

1. **Repository snapshot** — `recipes.json`, originally 228 recipes and now 230 after restoring two missing originals.
2. **Historical original set** — the first 228-recipe Git snapshot plus two recipes explicitly supplied in the original-list supplement, for 230 total.
3. **Production dataset** — Supabase rows used by the deployed app. The application and API are deployed against Supabase, but direct authenticated row inspection was unavailable in this environment.

No repository snapshot result in this report should be read as confirmed production database state.

## Work completed

### 1. Started from the deployed hardening baseline

The local checkout was one commit behind production. It was fast-forwarded to `25273b5` before changes, preserving the successful import and Pantry hardening already deployed.

### 2. Added independent stored-completeness and source-health assessment

`api/recipe_health.py` now treats recipe content and source accessibility as separate dimensions.

Stored completeness uses ingredients and instructions already held by MatplanApp. A complete recipe does not become incomplete merely because Instagram or TikTok is unavailable. Conversely, a reachable source does not make empty stored recipe data complete.

Source URLs are classified as:

- Instagram Reel
- Instagram post
- TikTok video
- Facebook post
- ordinary website
- missing or malformed URL

Source health distinguishes healthy sources, inaccessible sources, removed/private or login-blocked sources, redirects, and reachable social pages that are not machine-readable.

### 3. Added a safe batch audit and repair runner

`scripts/complete_recipe_library.py` provides:

- repository-snapshot dry runs;
- production Supabase loading only when credentials exist;
- a machine-readable full-record backup before mutation;
- per-recipe source inspection;
- field-level conservative merge proposals;
- immutable recipe-name protection;
- per-row change detection before write;
- per-row post-write verification;
- restoration of the original record if verification fails;
- machine-readable reports with completeness, source health, repairs, integrity, and remaining problems.

`--apply` refuses to run against a fixture and requires both production Supabase access and an explicit `--confirm-production` flag.

### 4. Audited all 228 original repository recipes against public sources

The network audit individually processed every source.

Source types:

| Source type | Count |
|---|---:|
| Instagram Reel | 161 |
| Instagram post | 13 |
| TikTok video | 32 |
| Ordinary website | 16 |
| Facebook post | 6 |
| **Total** | **228** |

Source health:

| Source health | Count |
|---|---:|
| Healthy machine-readable source | 18 |
| Social source reachable but not machine-readable | 206 |
| Source inaccessible | 3 |
| Redirect issue | 1 |
| **Total** | **228** |

The audit generated 184 conservative proposed improvements. Most were public thumbnails; a smaller set contained source metadata or structured ingredient/instruction candidates. These were proposals only, not persisted repairs.

### 5. Added an in-app manual-review queue

The Recipes view now shows **Oppskrifter som trenger hjelp** only for recipes missing stored ingredients or instructions.

Each row provides user-facing actions:

- **Prøv igjen**
- **Åpne kilde**
- **Rediger**

Existing recipe name, existing ingredients, existing instructions, original source, and available imagery remain visible through the established edit flow. Saving complete stored content removes a recipe from the queue on rerender.

The queue was tested locally with the 228-recipe fixture and rendered 204 items under the browser-side legacy text helpers. The authoritative Python audit uses the stricter report heuristic. Desktop and 390 × 844 checks found no horizontal overflow.

### 6. Added recipe-library Pantry suggestions

After the existing 22-item starter flow, Pantry can now offer optional candidates based on recurring ingredients in usable stored recipes.

The suggestions:

- are optional Yes/No prompts;
- ignore already-owned or dismissed items;
- require repeated use across recipes;
- filter common meat, fish, dairy, and other perishable candidates;
- preserve the fast original Pantry onboarding.

### 7. Verified the focused recipe-creation flow

The local browser test used the custom name `Min egen fredagspasta` and an unreachable test URL.

Observed behavior:

- the focused **Lag oppskrift** dialog opened;
- name and URL fields were clear;
- failure messaging used plain language;
- the custom recipe name remained `Min egen fredagspasta` after source retrieval failed;
- manual completion remained available.

### 8. Reconciled the original recipe list

`scripts/reconcile_recipe_library.py` compares:

- historical name and source URL;
- current name and source URL;
- historical and current ingredient/instruction counts;
- current stored ingredients and instructions;
- source availability;
- newly extracted candidate content.

The historical set combines the initial Git recipe snapshot with `historical/original_recipe_supplement.json`.

Before restoration, reconciliation found:

| Category | Count |
|---|---:|
| Exact historical match with usable content | 19 |
| Current recipe missing stored data | 205 |
| Source URL broken or redirecting | 4 |
| Missing from MatplanApp | 2 |
| Possible duplicate group | 1 |
| Present only in MatplanApp | 0 |
| Historical source URL changed | 0 |

Missing recipes:

- `Spicy cucumber side dish`
- `Thai red curry udon noodle soup`

Possible duplicate:

- `Lasagne` — `https://vm.tiktok.com/ZGebmohx7/`
- `Lasagne` — `https://vm.tiktok.com/ZGekKfLSf/`

Broken or redirecting ordinary sources:

- `Gresskar curry / Hokkaido butter masala`
- `Indisk kikertgryte – Linda Stuhaug`
- `Biff ramen`
- `Tandori kylling i pita`

### 9. Restored the two missing recipes

Both missing recipes were added to `recipes.json` with their exact user-owned names and original Instagram content URLs.

They were deliberately added without invented ingredients or instructions and therefore remain in manual review.

`api/ensure-original-recipes.py` supplies an idempotent production synchronization path:

- match by exact original content URL;
- do nothing when the recipe already exists;
- never patch or rename an existing row;
- insert only the fixed missing historical recipe records;
- use collision-resistant string IDs for new production rows.

The client calls this synchronization only when one or both original URLs are absent, then refreshes the recipe library.

After restoration, repository reconciliation reports 230 historical entries and 230 current entries. The two separate `Lasagne` records remain flagged for human duplicate review.

## Final repository data health

The final stored-data-only audit of the 230-recipe repository snapshot reports:

| Stored completeness | Count |
|---|---:|
| Complete | 0 |
| Probably complete | 23 |
| Incomplete | 207 |
| **Total** | **230** |

This is intentionally stricter than the earlier network-assisted preview. The previously reported `9 complete / 14 probably complete / 205 incomplete` represented the hypothetical dry-run result after merging recoverable network candidates in memory. It did not represent persisted data. No such candidates were written.

Final source-type counts after adding the two originals:

| Source type | Count |
|---|---:|
| Instagram Reel | 163 |
| Instagram post | 13 |
| TikTok video | 32 |
| Ordinary website | 16 |
| Facebook post | 6 |
| **Total** | **230** |

The two newly restored Instagram sources were not included in the earlier network-availability run, so no new availability status is claimed for them.

## Repairs and integrity

Confirmed persisted repository changes:

- recipes added: 2;
- existing recipes modified: 0;
- existing names changed: 0;
- existing source URLs changed: 0;
- existing ingredient lists overwritten: 0;
- existing instruction sets overwritten: 0;
- notes overwritten: 0;
- favorites changed: 0;
- recipes lost: 0.

Network-derived content repairs persisted to the repository or verified production database:

- ingredient lists added: 0;
- instruction sets added: 0;
- images added: 0;
- screenshots added: 0;
- source URLs repaired: 0.

The absence of these writes is a safety outcome, not a completion claim: authenticated production access was unavailable and the repository fixture was not treated as production.

## Override-layer audit

`app.js` still contains historical override layers. This pass added narrowly scoped final wrappers rather than broadly consolidating the file.

Observed risks remain:

- repeated redefinition of `init`, rendering, Pantry, and import functions;
- ordering-dependent active behavior;
- difficult static traceability;
- potential future regressions if changes target an inactive earlier definition.

No broad consolidation was attempted because it would have exceeded the focused data-completion scope. Regression tests target the final active contracts.

## Validation

Final automated validation:

- JavaScript syntax: passed;
- Python compilation: passed;
- complete unit suite: **81 tests passed**;
- `git diff --check`: passed;
- desktop local UI inspection: passed;
- 390 × 844 responsive review-queue inspection: passed;
- custom-name preservation in import failure path: passed;
- final repository reconciliation: 230 of 230 historical recipes present;
- `HEAD` pushed to `origin/main`.

Production deployments:

| Commit | Purpose | Deployment |
|---|---|---|
| `8d8b548` | Safe completion audit and review queue | Success |
| `1e27151` | Historical reconciliation | Success |
| `9583e4d` | Restore missing original recipes | Success |

## Remaining work and proof boundary

The task is not honestly complete as a production data-repair operation.

Outstanding items:

1. Directly read the active Supabase dataset and verify its current total and row content.
2. Verify that the deployed synchronization inserted both missing historical rows in Supabase.
3. Run the guarded repair runner against authenticated production.
4. Review and apply only high-confidence field improvements.
5. Rerun completeness and source-health reports after verified writes.
6. Manually recover recipes still lacking sufficient source text or imagery.
7. Review whether the two `Lasagne` records are intentional variants.
8. Perform authenticated production UI verification, including the final queue count and removal-after-save behavior.

Until those steps are completed, the accurate status is:

- production code deployed;
- repository historical coverage restored to 230 of 230;
- production synchronization path deployed;
- production database content not directly verified;
- most stored recipes still require content recovery.

## Artifacts

- `api/recipe_health.py`
- `api/ensure-original-recipes.py`
- `scripts/complete_recipe_library.py`
- `scripts/reconcile_recipe_library.py`
- `historical/original_recipe_supplement.json`
- `/tmp/matplan-final-network-audit-v2/recipe-library-report.json`
- `/tmp/matplan-final-network-audit-v2/remaining-problems.md`
- `/tmp/matplan-original-reconciliation.json`
- `/tmp/matplan-original-reconciliation.md`
- `/tmp/matplan-final-230-audit/recipe-library-report.json`

## Final required statement

Existing recipe names automatically changed: **0**
