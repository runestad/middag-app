import json
import os
import time
import urllib.request
import urllib.error
import urllib.parse
import ssl

APP_ID = os.environ.get("APP_ID", "oyvind-melanie")

SHOPPING_CATEGORIES = [
    "Frukt og grønt", "Kjøtt", "Kjølevarer", "Meieri", "Frys",
    "Hermetikk/halvfabrikat", "Tørrvarer", "Krydder",
    "Glutenfritt", "Bakevarer", "Annet"
]


def get_ssl_context():
    return ssl.create_default_context()


def supabase_config():
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL eller SUPABASE_SERVICE_ROLE_KEY mangler i Vercel Environment Variables")
    return url.rstrip("/"), key


def supabase_request(method, path, payload=None, query=None, prefer="return=representation"):
    base, key = supabase_config()
    url = f"{base}/rest/v1/{path.lstrip('/')}"
    if query:
        url += "?" + query

    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Prefer": prefer,
    }

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60, context=get_ssl_context()) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase-feil {e.code}: {detail}")


def recipe_to_row(recipe):
    rid = str(recipe.get("id") or f"custom-{int(time.time()*1000)}")
    return {
        "id": rid,
        "app_id": APP_ID,
        "name": recipe.get("name") or recipe.get("title") or "",
        "category": recipe.get("category") or "",
        "source": recipe.get("source") or "",
        "link": recipe.get("link") or "",
        "status": recipe.get("status") or "",
        "data": recipe,
    }


def row_to_recipe(row):
    data = row.get("data") or {}
    data.setdefault("id", row.get("id"))
    data.setdefault("name", row.get("name"))
    data.setdefault("category", row.get("category"))
    data.setdefault("source", row.get("source"))
    data.setdefault("link", row.get("link"))
    data.setdefault("status", row.get("status"))
    return data


def read_body(handler):
    length = int(handler.headers.get("content-length", "0") or "0")
    if not length:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def send_json(handler, payload, status=200):
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)
