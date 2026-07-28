import hashlib
import json
import os
import urllib.parse
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from ._common import (
    APP_ID,
    read_body,
    recipe_to_row,
    row_to_recipe,
    send_json,
    supabase_request,
)
from .ingredient_normalization import normalize_structured_ingredients


MANIFEST_PATH = Path(__file__).resolve().parents[1] / "recovery-manifest.json"
HISTORY_KEY = f"recovery-history:{APP_ID}"
STATE_KEY = f"recovery-state:{APP_ID}"
RESTORABLE_FIELDS = {
    "ingredientsText", "structuredIngredients", "instructions",
    "structuredInstructions", "caption", "image", "title",
    "name", "servings", "tags",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def token_for(payload):
    secret = os.environ.get("RECOVERY_TOKEN_SECRET") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "local")
    return hashlib.sha256((secret + canonical(payload)).encode("utf-8")).hexdigest()


def is_missing(value):
    return value is None or value == "" or value == [] or value == {}


def get_recipe_row(recipe_id):
    query = urllib.parse.urlencode({
        "id": f"eq.{recipe_id}",
        "app_id": f"eq.{APP_ID}",
        "select": "*",
        "limit": "1",
    })
    rows = supabase_request("GET", "recipes", query=query) or []
    return rows[0] if rows else None


def get_state(key, default):
    query = urllib.parse.urlencode({"key": f"eq.{key}", "app_id": f"eq.{APP_ID}", "select": "*", "limit": "1"})
    rows = supabase_request("GET", "app_state", query=query) or []
    return (rows[0].get("data") if rows else None) or default


def put_state(key, data):
    query = urllib.parse.urlencode({"key": f"eq.{key}", "app_id": f"eq.{APP_ID}", "select": "key"})
    rows = supabase_request("GET", "app_state", query=query) or []
    row = {"key": key, "app_id": APP_ID, "data": data}
    if rows:
        update_query = urllib.parse.urlencode({"key": f"eq.{key}", "app_id": f"eq.{APP_ID}"})
        return supabase_request("PATCH", "app_state", payload=row, query=update_query)
    return supabase_request("POST", "app_state", payload=row)


def candidate_for(recipe_id):
    for item in load_manifest().get("high", []):
        if str(item.get("id")) == str(recipe_id):
            return item
    return None


def candidate_fields(item):
    candidate = item.get("candidate") or {}
    result = {}
    ingredients = candidate.get("ingredienser") or {}
    instructions = candidate.get("fremgangsmåte") or {}
    for field in ("ingredientsText", "structuredIngredients"):
        if not is_missing(ingredients.get(field)):
            result[field] = ingredients[field]
    for field in ("instructions", "structuredInstructions"):
        if not is_missing(instructions.get(field)):
            result[field] = instructions[field]
    for field in RESTORABLE_FIELDS:
        if not is_missing(candidate.get(field)):
            result[field] = candidate[field]
    return result


def build_preview(recipe_id, requested_fields, allow_overwrite=None):
    row = get_recipe_row(recipe_id)
    if not row:
        raise ValueError("Oppskriften finnes ikke i produksjonsdatabasen.")
    item = candidate_for(recipe_id)
    if not item:
        raise ValueError("Ingen godkjent historisk kandidat finnes for oppskriften.")
    current = row_to_recipe(row)
    candidates = candidate_fields(item)
    allowed_overwrite = set(allow_overwrite or [])
    fields = []
    for field in requested_fields:
        if field not in RESTORABLE_FIELDS or field not in candidates:
            continue
        before, after = current.get(field), candidates[field]
        if not is_missing(before) and field not in allowed_overwrite:
            raise ValueError(f"Feltet «{field}» har allerede innhold og kan ikke overskrives uten særskilt bekreftelse.")
        if canonical(before) == canonical(after):
            continue
        fields.append({"field": field, "before": before, "after": after, "wasMissing": is_missing(before)})
    if not fields:
        raise ValueError("Ingen valgte, gjenopprettbare felt har en trygg endring.")
    token_payload = {
        "recipeId": str(recipe_id),
        "rowUpdatedAt": row.get("updated_at"),
        "candidateFingerprint": item.get("candidateFingerprint"),
        "fields": fields,
    }
    return {
        "recipeId": str(recipe_id),
        "recipeName": current.get("name") or row.get("name") or "",
        "source": item.get("sources") or [],
        "fields": fields,
        "previewToken": token_for(token_payload),
        "_tokenPayload": token_payload,
    }


def apply_preview(preview, actor="user"):
    current_row = get_recipe_row(preview["recipeId"])
    if not current_row or current_row.get("updated_at") != preview["_tokenPayload"]["rowUpdatedAt"]:
        raise ValueError("Oppskriften er endret etter forhåndsvisningen. Lag en ny preview før du fortsetter.")
    current = row_to_recipe(current_row)
    patch = {}
    for change in preview["fields"]:
        if canonical(current.get(change["field"])) != canonical(change["before"]):
            raise ValueError(f"Feltet «{change['field']}» er endret etter forhåndsvisningen.")
        value = change["after"]
        if change["field"] == "structuredIngredients":
            value = normalize_structured_ingredients(value)
        patch[change["field"]] = value
    history = get_state(HISTORY_KEY, {"entries": []})
    entry = {
        "id": str(uuid.uuid4()),
        "recipeId": preview["recipeId"],
        "recipeName": preview["recipeName"],
        "createdAt": now_iso(),
        "actor": actor,
        "source": preview.get("source") or [],
        "fields": preview["fields"],
        "status": "pending",
        "rollbackAvailable": False,
        "rolledBackAt": None,
    }
    history.setdefault("entries", []).insert(0, entry)
    put_state(HISTORY_KEY, history)

    updated = dict(current)
    updated.update(patch)
    updated["updatedAt"] = now_iso()
    row = recipe_to_row(updated)
    query = urllib.parse.urlencode({"id": f"eq.{preview['recipeId']}", "app_id": f"eq.{APP_ID}"})
    supabase_request("PATCH", "recipes", payload=row, query=query)

    entry["status"] = "applied"
    entry["rollbackAvailable"] = True
    try:
        put_state(HISTORY_KEY, history)
    except Exception:
        # The pre-write audit entry already contains the full before/after
        # backup. Keep reporting the successful recipe write truthfully and
        # let rollback validate the persisted "pending" entry against the
        # current row before it can be used.
        entry["auditStateWarning"] = True
    try:
        state = get_state(STATE_KEY, {"items": {}, "paused": False})
        state.setdefault("items", {})[str(preview["recipeId"])] = {
            "status": "recovered",
            "updatedAt": now_iso(),
        }
        put_state(STATE_KEY, state)
    except Exception:
        entry["queueStateWarning"] = True
    return entry


def build_rollback_preview(history_id):
    history = get_state(HISTORY_KEY, {"entries": []})
    entry = next((item for item in history.get("entries", []) if item.get("id") == history_id), None)
    can_validate_pending = entry and entry.get("status") == "pending"
    if not entry or (not entry.get("rollbackAvailable") and not can_validate_pending) or entry.get("rolledBackAt"):
        raise ValueError("Denne gjenopprettingen kan ikke rulles tilbake.")
    row = get_recipe_row(entry["recipeId"])
    if not row:
        raise ValueError("Oppskriften finnes ikke lenger.")
    current = row_to_recipe(row)
    changes = []
    for field in entry.get("fields", []):
        if canonical(current.get(field["field"])) != canonical(field["after"]):
            raise ValueError(f"«{field['field']}» er endret etter gjenopprettingen. Rollback er stoppet for å beskytte nyere data.")
        changes.append({"field": field["field"], "before": field["after"], "after": field["before"]})
    payload = {"historyId": history_id, "recipeId": entry["recipeId"], "rowUpdatedAt": row.get("updated_at"), "fields": changes}
    return {"historyId": history_id, "recipeId": entry["recipeId"], "recipeName": entry["recipeName"], "fields": changes, "previewToken": token_for(payload), "_tokenPayload": payload}


def apply_rollback(preview):
    row = get_recipe_row(preview["recipeId"])
    if not row or row.get("updated_at") != preview["_tokenPayload"]["rowUpdatedAt"]:
        raise ValueError("Oppskriften er endret etter rollback-preview. Start på nytt.")
    history = get_state(HISTORY_KEY, {"entries": []})
    entry = next((item for item in history.get("entries", []) if item.get("id") == preview["historyId"]), None)
    if not entry:
        raise ValueError("Fant ikke audit-loggen for denne gjenopprettingen.")
    current = row_to_recipe(row)
    for change in preview["fields"]:
        if canonical(current.get(change["field"])) != canonical(change["before"]):
            raise ValueError("Nyere innhold beskytter oppskriften mot rollback.")
        current[change["field"]] = change["after"]
    current["updatedAt"] = now_iso()
    query = urllib.parse.urlencode({"id": f"eq.{preview['recipeId']}", "app_id": f"eq.{APP_ID}"})
    supabase_request("PATCH", "recipes", payload=recipe_to_row(current), query=query)

    entry["rolledBackAt"] = now_iso()
    entry["rollbackAvailable"] = False
    entry["status"] = "rolled_back"
    try:
        put_state(HISTORY_KEY, history)
    except Exception:
        entry["auditStateWarning"] = True
    try:
        state = get_state(STATE_KEY, {"items": {}, "paused": False})
        state.setdefault("items", {})[str(preview["recipeId"])] = {
            "status": "pending",
            "updatedAt": now_iso(),
        }
        put_state(STATE_KEY, state)
    except Exception:
        entry["queueStateWarning"] = True
    return entry


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            action = (params.get("action") or ["dashboard"])[0]
            manifest = load_manifest()
            if action == "history":
                return send_json(self, {"ok": True, **get_state(HISTORY_KEY, {"entries": []})})
            if action == "item":
                recipe_id = (params.get("id") or [""])[0]
                item = candidate_for(recipe_id)
                row = get_recipe_row(recipe_id)
                if not item or not row:
                    return send_json(self, {"ok": False, "error": "Oppskriften eller kandidaten finnes ikke."}, 404)
                return send_json(self, {"ok": True, "item": item, "production": row_to_recipe(row)})
            state = get_state(STATE_KEY, {"items": {}, "paused": False})
            return send_json(self, {"ok": True, "manifest": manifest, "state": state})
        except Exception as exc:
            return send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_POST(self):
        try:
            payload = read_body(self)
            action = payload.get("action")
            if action == "preview":
                preview = build_preview(payload.get("id"), payload.get("fields") or [], payload.get("allowOverwriteFields") or [])
                public = {key: value for key, value in preview.items() if not key.startswith("_")}
                return send_json(self, {"ok": True, "preview": public})
            if action == "confirm":
                preview = build_preview(payload.get("id"), payload.get("fields") or [], payload.get("allowOverwriteFields") or [])
                if payload.get("previewToken") != preview["previewToken"]:
                    return send_json(self, {"ok": False, "error": "Preview er utløpt eller endret. Lag en ny preview."}, 409)
                entry = apply_preview(preview)
                return send_json(self, {"ok": True, "history": entry})
            if action == "rollback-preview":
                preview = build_rollback_preview(payload.get("historyId"))
                public = {key: value for key, value in preview.items() if not key.startswith("_")}
                return send_json(self, {"ok": True, "preview": public})
            if action == "rollback-confirm":
                preview = build_rollback_preview(payload.get("historyId"))
                if payload.get("previewToken") != preview["previewToken"]:
                    return send_json(self, {"ok": False, "error": "Rollback-preview er utløpt. Lag en ny preview."}, 409)
                entry = apply_rollback(preview)
                return send_json(self, {"ok": True, "history": entry})
            if action == "queue-state":
                state = get_state(STATE_KEY, {"items": {}, "paused": False})
                if "paused" in payload:
                    state["paused"] = bool(payload["paused"])
                recipe_id = str(payload.get("id") or "")
                if recipe_id:
                    state.setdefault("items", {})[recipe_id] = {
                        "status": payload.get("status") or "pending",
                        "updatedAt": now_iso(),
                    }
                put_state(STATE_KEY, state)
                return send_json(self, {"ok": True, "state": state})
            return send_json(self, {"ok": False, "error": "Ukjent handling."}, 400)
        except ValueError as exc:
            return send_json(self, {"ok": False, "error": str(exc)}, 409)
        except Exception as exc:
            return send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
