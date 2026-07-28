import ipaddress
import json
import re
import socket
import urllib.parse
import urllib.request
from html import unescape
from http.server import BaseHTTPRequestHandler

from ._common import get_ssl_context, read_body, send_json


MAX_BYTES = 2_000_000


def validate_public_url(value):
    parsed = urllib.parse.urlparse(str(value or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Lim inn en gyldig http- eller https-lenke.")
    for result in socket.getaddrinfo(parsed.hostname, parsed.port or 443):
        address = ipaddress.ip_address(result[4][0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            raise ValueError("Private eller lokale adresser kan ikke hentes.")
    return parsed.geturl()


class PublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        validate_public_url(new_url)
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


def fetch_text(url):
    validate_public_url(url)
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; MatplanRecipeImporter/1.0)",
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    })
    opener = urllib.request.build_opener(
        PublicRedirectHandler(),
        urllib.request.HTTPSHandler(context=get_ssl_context()),
    )
    with opener.open(request, timeout=20) as response:
        validate_public_url(response.geturl())
        content_type = response.headers.get("content-type", "")
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Kilden er for stor til sikker automatisk behandling.")
        return raw.decode("utf-8", errors="replace"), content_type, response.geturl()


def meta_value(html, key):
    patterns = [
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']*)',
        rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.I)
        if match:
            return unescape(match.group(1)).strip()
    return ""


def text_content(value):
    value = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(value)).strip()


def json_ld_recipes(html):
    found = []
    for raw in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>', html, re.I):
        try:
            payload = json.loads(unescape(raw).strip())
        except Exception:
            continue
        stack = payload if isinstance(payload, list) else [payload]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                item_type = item.get("@type")
                types = item_type if isinstance(item_type, list) else [item_type]
                if "Recipe" in types:
                    found.append(item)
                graph = item.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
    return found


def recipe_text(recipe):
    ingredients = recipe.get("recipeIngredient") or []
    instructions = recipe.get("recipeInstructions") or []
    steps = []
    for item in instructions:
        if isinstance(item, str):
            steps.append(item)
        elif isinstance(item, dict):
            steps.append(item.get("text") or item.get("name") or "")
    sections = []
    if ingredients:
        sections.append("Ingredienser:\n" + "\n".join(f"- {item}" for item in ingredients))
    if steps:
        sections.append("Fremgangsmåte:\n" + "\n".join(f"{index + 1}. {text}" for index, text in enumerate(steps) if text))
    return "\n\n".join(sections)


def tiktok_oembed(url):
    endpoint = "https://www.tiktok.com/oembed?" + urllib.parse.urlencode({"url": url})
    raw, _, resolved = fetch_text(endpoint)
    payload = json.loads(raw)
    return {
        "resolvedUrl": resolved,
        "title": payload.get("title") or "",
        "caption": payload.get("title") or "",
        "image": payload.get("thumbnail_url") or "",
        "author": payload.get("author_name") or "",
        "provider": "TikTok oEmbed",
    }


def extract(url):
    host = urllib.parse.urlparse(url).hostname or ""
    if "tiktok.com" in host:
        try:
            return {**tiktok_oembed(url), "sourceType": "TikTok", "method": "oembed"}
        except Exception:
            pass

    html, content_type, resolved = fetch_text(url)
    if "json" in content_type:
        return {"resolvedUrl": resolved, "caption": html, "sourceType": "Web", "method": "json"}
    recipes = json_ld_recipes(html)
    recipe = recipes[0] if recipes else {}
    title_match = re.search(r"<title[^>]*>([\s\S]*?)</title>", html, re.I)
    title = recipe.get("name") or meta_value(html, "og:title") or (text_content(title_match.group(1)) if title_match else "")
    description = recipe.get("description") or meta_value(html, "og:description") or meta_value(html, "description")
    image = recipe.get("image") or meta_value(html, "og:image")
    if isinstance(image, list):
        image = image[0] if image else ""
    if isinstance(image, dict):
        image = image.get("url") or ""
    structured = recipe_text(recipe)
    source_type = "Instagram" if "instagram.com" in host else "TikTok" if "tiktok.com" in host else "Web"
    return {
        "resolvedUrl": resolved,
        "title": text_content(str(title)),
        "caption": structured or text_content(str(description)),
        "image": image or "",
        "sourceType": source_type,
        "method": "json-ld" if structured else "metadata",
        "hasStructuredRecipe": bool(structured),
    }


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            payload = read_body(self)
            url = validate_public_url(payload.get("url"))
            result = extract(url)
            result["needsManualSource"] = not bool(result.get("caption"))
            return send_json(self, {"ok": True, "result": result})
        except Exception as exc:
            return send_json(self, {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "needsManualSource": True,
            }, 422)
