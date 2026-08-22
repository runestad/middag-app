from http.server import BaseHTTPRequestHandler
from ._common import *

SHOPPING_EPOCH = "2000-01-01T00:00:00.000Z"


def _merge_shopping_items(stored_items, incoming_items):
    """Item-level last-write-wins; missing items never mean deletion."""
    merged = {}
    for item in list(stored_items or []) + list(incoming_items or []):
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        if not item_id:
            continue
        current = merged.get(item_id)
        item_time = str(item.get("updatedAt") or SHOPPING_EPOCH)
        current_time = str((current or {}).get("updatedAt") or SHOPPING_EPOCH)
        if current is None or item_time >= current_time:
            merged[item_id] = item
    return list(merged.values())


def _persist_plan_with_retry(key, incoming_data, attempts=5):
    """CAS retry prevents concurrent full-document requests from losing items."""
    last_error = None
    candidate_data = dict(incoming_data)
    for attempt in range(attempts):
        q = urllib.parse.urlencode({"key": f"eq.{key}", "select": "*"})
        rows = supabase_request("GET", "app_state", query=q) or []
        stored_data = rows[0].get("data") if rows and isinstance(rows[0].get("data"), dict) else {}
        merged_data = dict(candidate_data)
        merged_data["shoppingItems"] = _merge_shopping_items(
            stored_data.get("shoppingItems"), candidate_data.get("shoppingItems")
        )
        candidate_data = merged_data
        row = {"key": key, "app_id": APP_ID, "data": merged_data}

        if rows:
            stored_revision = stored_data.get("updatedAt")
            filters = {"key": f"eq.{key}"}
            filters["data->>updatedAt"] = f"eq.{stored_revision}" if stored_revision else "is.null"
            updated = supabase_request(
                "PATCH", "app_state", payload=row,
                query=urllib.parse.urlencode(filters), prefer="return=representation"
            ) or []
            if updated:
                return merged_data
            continue

        try:
            created = supabase_request("POST", "app_state", payload=row, prefer="return=representation") or []
            if created:
                return merged_data
        except RuntimeError as exc:
            last_error = exc
            if attempt == attempts - 1:
                raise

    if last_error:
        raise last_error
    raise RuntimeError("Kunne ikke lagre etter samtidige oppdateringer")

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            q = urllib.parse.urlencode({"key": f"eq.plan:{APP_ID}", "select": "*"})
            rows = supabase_request("GET", "app_state", query=q) or []
            data = rows[0].get("data") if rows else {}
            send_json(self, {"ok": True, "plan": data or {}, "storage": "supabase"})
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_POST(self):
        try:
            payload = read_body(self)
            data = payload.get("plan") if isinstance(payload.get("plan"), dict) else payload
            key = f"plan:{APP_ID}"

            merged_data = _persist_plan_with_retry(key, data)
            send_json(self, {"ok": True, "storage": "supabase", "plan": merged_data})
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
