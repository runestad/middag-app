import hashlib
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from ._common import *

SHOPPING_EPOCH = "2000-01-01T00:00:00.000Z"


class PlanChangedError(RuntimeError):
    pass


def _revision_etag(row):
    """Use the database trigger's revision, including edits from other clients."""
    revision = (row or {}).get("updated_at")
    if not revision:
        return None
    token = json.dumps([APP_ID, revision], ensure_ascii=False).encode("utf-8")
    return 'W/"plan-v2-' + hashlib.sha256(token).hexdigest() + '"'


def _etag_matches(header, etag):
    # GET validators use weak comparison. Vercel may weaken a strong ETag when
    # compressing the response, so comparing the raw header strings is unsafe.
    def opaque(value):
        value = value.strip()
        return value[2:] if value.startswith("W/") else value
    return any(value.strip() == "*" or opaque(value) == opaque(etag)
               for value in (header or "").split(","))


def _send_not_modified(handler, etag):
    handler.send_response(304)
    handler.send_header("ETag", etag)
    handler.send_header("Cache-Control", "private, no-cache")
    handler.end_headers()


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


def _persist_plan_with_retry(key, incoming_data, attempts=5, expected_revision=None):
    """CAS retry prevents concurrent full-document requests from losing items."""
    last_error = None
    candidate_data = dict(incoming_data)
    for attempt in range(attempts):
        q = urllib.parse.urlencode({"key": f"eq.{key}", "select": "*"})
        rows = supabase_request("GET", "app_state", query=q) or []
        stored_data = rows[0].get("data") if rows and isinstance(rows[0].get("data"), dict) else {}
        if expected_revision is not None and stored_data.get("updatedAt") != expected_revision:
            raise PlanChangedError("Handlelisten er endret siden gjennomgangen. Hent en ny forhåndsvisning.")
        merged_data = dict(candidate_data)
        # Older clients do not know about the card; their routine saves must
        # not erase it. An explicit card update can still replace the value.
        stored_code = (stored_data.get("meta") or {}).get("remaCustomerCode")
        if stored_code and "remaCustomerCode" not in (merged_data.get("meta") or {}):
            merged_data["meta"] = {**(merged_data.get("meta") or {}), "remaCustomerCode": stored_code}
        merged_data["shoppingItems"] = _merge_shopping_items(
            stored_data.get("shoppingItems"), candidate_data.get("shoppingItems")
        )
        candidate_data = merged_data
        row = {"key": key, "app_id": APP_ID, "data": merged_data}

        if rows:
            stored_revision = stored_data.get("updatedAt")
            # Only the key is needed to distinguish CAS success from a conflict.
            # Returning the full JSON document duplicates a large transfer.
            filters = {"key": f"eq.{key}", "select": "key"}
            filters["data->>updatedAt"] = f"eq.{stored_revision}" if stored_revision else "is.null"
            updated = supabase_request(
                "PATCH", "app_state", payload=row,
                query=urllib.parse.urlencode(filters), prefer="return=representation"
            ) or []
            if updated:
                return merged_data
            continue

        try:
            created = supabase_request("POST", "app_state", payload=row,
                                       query="select=key", prefer="return=representation") or []
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
            key = f"eq.plan:{APP_ID}"
            validator = self.headers.get("If-None-Match", "")
            if validator:
                # Check a tiny revision BEFORE fetching the document. An HTTP
                # 304 alone only saves Vercel egress if Supabase already sent it.
                q = urllib.parse.urlencode({"key": key, "select": "updated_at", "limit": "1"})
                revisions = supabase_request("GET", "app_state", query=q) or []
                etag = _revision_etag(revisions[0]) if revisions else None
                if etag and _etag_matches(validator, etag):
                    return _send_not_modified(self, etag)

            q = urllib.parse.urlencode({"key": key, "select": "data,updated_at", "limit": "1"})
            rows = supabase_request("GET", "app_state", query=q) or []
            data = rows[0].get("data") if rows else {}
            body = json.dumps({"ok": True, "plan": data or {}, "storage": "supabase"}, ensure_ascii=False, sort_keys=True).encode("utf-8")
            # Bind the validator to the same snapshot as the returned body,
            # rather than the earlier probe (a save may happen between reads).
            etag = (_revision_etag(rows[0]) if rows else None) or ('W/"' + hashlib.sha256(body).hexdigest() + '"')
            if _etag_matches(validator, etag):
                return _send_not_modified(self, etag)
            self.send_response(200)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "private, no-cache")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_POST(self):
        try:
            payload = read_body(self)
            if payload.get("action") == "setRemaCustomerCode":
                code = str(payload.get("code") or "")
                if not re.fullmatch(r"\d{6,30}", code, flags=re.ASCII):
                    return send_json(self, {"ok": False, "error": "Ugyldig kundenummer."}, 400)
                key = f"plan:{APP_ID}"
                query = urllib.parse.urlencode({"key": f"eq.{key}", "select": "*"})
                rows = supabase_request("GET", "app_state", query=query) or []
                if not rows:
                    return send_json(self, {"ok": False, "error": "Fant ikke appdata."}, 404)
                current = rows[0].get("data") or {}
                revision = current.get("updatedAt")
                if not revision:
                    return send_json(self, {"ok": False, "error": "Last appen før du lagrer kundekort."}, 409)
                updated = {**current, "meta": {**(current.get("meta") or {}), "remaCustomerCode": code}, "updatedAt": datetime.now(timezone.utc).isoformat()}
                _persist_plan_with_retry(key, updated, expected_revision=revision)
                return send_json(self, {"ok": True})
            data = payload.get("plan") if isinstance(payload.get("plan"), dict) else payload
            key = f"plan:{APP_ID}"

            merged_data = _persist_plan_with_retry(key, data, expected_revision=payload.get("expectedUpdatedAt"))
            send_json(self, {"ok": True, "storage": "supabase", "plan": merged_data})
        except PlanChangedError as exc:
            send_json(self, {"ok": False, "error": str(exc)}, 409)
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)

