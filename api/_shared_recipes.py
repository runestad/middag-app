"""Project only cookbook fields into public, scope-checked recipe responses."""
import re
from urllib.parse import urlencode, urlsplit

from ._access import signature, valid_signature
from ._common import APP_ID, row_to_recipe, supabase_request

SUMMARY_FIELDS = ("tags", "image", "thumbnail", "userImagePath", "verifiedFallbackImage",
                  "sourceUrl", "originalSourceUrl", "resolvedSourceUrl", "imageIsIllustration")
SUMMARY_SELECT = ",".join(["id", "name", "category", "source", "link"] +
                          [f"{field}:data->{field}" for field in SUMMARY_FIELDS])
SOURCE_KEYS = ("link", "sourceUrl", "sourceURL", "source_url", "sourceLink", "source_link",
               "originalSourceUrl", "originalUrl", "resolvedSourceUrl")


def share_proof(scope, recipe_id):
    return signature("recipe-share", [scope, recipe_id if scope == "recipe" else ""])


def allowed_share(scope, recipe_id, proof):
    if scope not in ("book", "recipe") or (scope == "recipe" and not recipe_id):
        return False
    return valid_signature("recipe-share", [scope, recipe_id if scope == "recipe" else ""], proof)


def recipe_row(recipe_id):
    query = urlencode({"app_id": f"eq.{APP_ID}", "id": f"eq.{recipe_id}", "select": "*", "limit": "1"})
    rows = supabase_request("GET", "recipes", query=query) or []
    return row_to_recipe(rows[0]) if rows else None


def library_rows():
    offset = 0
    while True:
        query = urlencode({"app_id": f"eq.{APP_ID}", "select": SUMMARY_SELECT,
                           "order": "name.asc,id.asc", "offset": offset, "limit": 200})
        rows = supabase_request("GET", "recipes", query=query) or []
        yield from rows
        if len(rows) < 200:
            break
        offset += len(rows)


def web_url(value):
    if isinstance(value, str):
        try:
            url = urlsplit(value.strip())
            if url.scheme in ("https", "http") and url.hostname and not url.username and not url.password:
                return value.strip()
        except ValueError:
            pass
    return ""


def image_url(value, detail):
    if not isinstance(value, str):
        return ""
    if re.fullmatch(r"/?assets/recipe-media/[\w.-]+\.(?:jpe?g|png|webp)", value, re.I):
        return "/" + value.lstrip("/")
    if detail and re.match(r"^data:image/(?:jpeg|webp|png);base64,", value, re.I):
        return value
    return web_url(value)


def text_lines(value, separator):
    items = value if isinstance(value, list) else re.split(separator, str(value or ""))
    return [item.strip() for item in items if isinstance(item, str) and item.strip()]


def ingredient_lines(recipe):
    lines = []
    for item in recipe.get("structuredIngredients") or []:
        if isinstance(item, str):
            lines.append(item.strip())
        elif isinstance(item, dict):
            name = item.get("item") or item.get("name")
            line = " ".join(str(v).strip() for v in (item.get("amount"), item.get("unit"), name)
                            if v is not None and str(v).strip())
            if name and item.get("note"):
                line += " (" + str(item["note"]) + ")"
            lines.append(line if name else str(item.get("original") or ""))
    return [s for s in lines if s] or text_lines(recipe.get("ingredientsText") or recipe.get("ingredientLines"), r"[;\n]")


def public_recipe(recipe, detail):
    rid = str(recipe["id"])
    title = recipe.get("name") or "Oppskrift"
    result = {"id": rid, "name": title, "category": recipe.get("category") or "",
              "tags": text_lines(recipe.get("tags"), r","),
              "source": str(recipe.get("source") or "")}
    images = []
    if recipe.get("userImagePath"):
        params = {"sharedPhoto": rid, "proof": signature("recipe-photo", rid)}
        images.append("/api/recipes?" + urlencode(params))
    for key in ("verifiedFallbackImage", "image", "thumbnail", "imageUrl", "posterUrl"):
        url = image_url(recipe.get(key), detail)
        if url and url not in images:
            images.append(url)
    result["images"] = images
    if detail:
        data = recipe.get("data") if isinstance(recipe.get("data"), dict) else {}
        urls = (web_url(box.get(key)) for box in (recipe, data) for key in SOURCE_KEYS)
        source = next(filter(None, urls), "")
        meta = recipe.get("sourceMetadata") or {}
        resolved = web_url(recipe.get("resolvedSourceUrl")) or (web_url(meta.get("resolvedSourceUrl")) if isinstance(meta, dict) else "")
        result.update({
            "link": source, "videoSource": resolved,
            "videoUrl": web_url(recipe.get("videoUrl") or recipe.get("video")),
            "servings": recipe.get("servings") or recipe.get("baseServings") or "",
            "ingredients": ingredient_lines(recipe),
            "steps": text_lines(recipe.get("instructions") or recipe.get("structuredInstructions")
                                or recipe.get("instructionSteps"), r"\n"),
            "imageIsIllustration": bool(recipe.get("imageIsIllustration")),
        })
    return result
