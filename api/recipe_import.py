"""Deterministic recipe import primitives shared by import and audit paths."""

import re
import urllib.parse
from datetime import datetime, timezone


TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "igsh", "igshid", "si"}
GENERIC_SOCIAL_PATHS = {"", "/", "/login", "/explore"}


def normalize_source_url(value):
    raw = str(value or "").strip()
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Lim inn en gyldig http- eller https-lenke.")
    host = (parsed.hostname or "").lower()
    keep = []
    for key, val in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
        lower = key.lower()
        if lower.startswith("utm_") or lower in TRACKING_KEYS:
            continue
        keep.append((key, val))
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    return urllib.parse.urlunparse((parsed.scheme.lower(), host, path, "", urllib.parse.urlencode(keep), ""))


def is_content_source_url(value, original=""):
    try:
        parsed = urllib.parse.urlparse(normalize_source_url(value))
    except ValueError:
        return False
    host, path = (parsed.hostname or "").lower(), parsed.path.rstrip("/").lower()
    if "tiktok.com" in host:
        return bool(re.match(r"^/@[^/]+/video/\d+", path) or re.match(r"^/t/[a-z0-9]+", path))
    if "instagram.com" in host:
        return bool(re.match(r"^/(reel|reels|p)/[^/]+", path))
    if any(social in host for social in ("facebook.com", "pinterest.com")):
        return path not in GENERIC_SOCIAL_PATHS
    return path not in GENERIC_SOCIAL_PATHS or not any(s in host for s in ("tiktok.com", "instagram.com"))


def choose_resolved_url(original, resolved):
    """Keep the user's content URL when a redirect lands on a generic/social page."""
    try:
        normalized_original = normalize_source_url(original)
    except ValueError:
        normalized_original = str(original or "").strip()
    try:
        normalized_resolved = normalize_source_url(resolved)
    except ValueError:
        return normalized_original
    original_host = urllib.parse.urlparse(normalized_original).hostname or ""
    if any(s in original_host for s in ("tiktok.com", "instagram.com")) and not is_content_source_url(normalized_resolved):
        return normalized_original
    return normalized_resolved


def instruction_lines(value):
    result = []
    stack = value if isinstance(value, list) else [value]
    while stack:
        item = stack.pop(0)
        if isinstance(item, str):
            text = item.strip()
            if text:
                result.append(text)
        elif isinstance(item, dict):
            nested = item.get("itemListElement")
            if isinstance(nested, list):
                stack[0:0] = nested
            else:
                text = str(item.get("text") or item.get("name") or "").strip()
                if text:
                    result.append(text)
    return result


def parse_iso_duration(value):
    match = re.match(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?$", str(value or ""), re.I)
    if not match:
        return None
    return int(match.group(1) or 0) * 1440 + int(match.group(2) or 0) * 60 + int(match.group(3) or 0)


def servings_value(value):
    if isinstance(value, list):
        value = value[0] if value else ""
    match = re.search(r"\d+(?:[.,]\d+)?", str(value or ""))
    return match.group(0).replace(",", ".") if match else ""


def structured_recipe(recipe, source_url, resolved_url, source_domain, image=""):
    ingredients = [str(v).strip() for v in (recipe.get("recipeIngredient") or []) if str(v).strip()]
    instructions = instruction_lines(recipe.get("recipeInstructions") or [])
    result = {
        "sourceTitle": str(recipe.get("name") or "").strip(),
        "sourceUrl": normalize_source_url(source_url),
        "resolvedSourceUrl": choose_resolved_url(source_url, resolved_url),
        "sourceDomain": source_domain,
        "ingredientsText": "\n".join(ingredients),
        "ingredientLines": ingredients,
        "instructions": "\n".join("{}. {}".format(i + 1, step) for i, step in enumerate(instructions)),
        "instructionSteps": instructions,
        "servings": servings_value(recipe.get("recipeYield")),
        "prepMinutes": parse_iso_duration(recipe.get("prepTime")),
        "cookTimeMinutes": parse_iso_duration(recipe.get("cookTime")),
        "totalMinutes": parse_iso_duration(recipe.get("totalTime")),
        "image": image,
        "sourceLastChecked": datetime.now(timezone.utc).isoformat(),
        "extractionMethod": "json-ld",
    }
    quality = assess_import_quality(result)
    result["importQuality"] = quality
    return result


def assess_import_quality(recipe):
    ingredients = recipe.get("ingredientLines") or [v for v in str(recipe.get("ingredientsText") or "").splitlines() if v.strip()]
    steps = recipe.get("instructionSteps") or [v for v in str(recipe.get("instructions") or "").splitlines() if v.strip()]
    suspicious = []
    joined = " ".join([str(v) for v in ingredients + steps]).lower()
    if not ingredients:
        suspicious.append("missing_ingredients")
    elif len(ingredients) == 1 and len(str(ingredients[0])) > 400:
        suspicious.append("malformed_ingredients")
    if not steps:
        suspicious.append("missing_instructions")
    elif len(steps) == 1 and len(str(steps[0])) > 1600:
        suspicious.append("malformed_instructions")
    if any(term in joined for term in ("accept cookies", "log in to continue", "captcha", "privacy policy")):
        suspicious.append("interstitial_content")
    if "interstitial_content" in suspicious:
        status = "BROKEN_SOURCE"
    elif not ingredients and not steps:
        status = "IMPORT_FAILED"
    elif suspicious:
        status = "INCOMPLETE"
    elif len(ingredients) >= 3 and len(steps) >= 2:
        status = "COMPLETE"
    else:
        status = "PROBABLY_COMPLETE"
    return {"status": status, "issues": suspicious, "ingredientCount": len(ingredients), "instructionCount": len(steps)}


def safe_recipe_merge(existing, imported):
    """Add high-confidence improvements without renaming or degrading good data."""
    old, new = dict(existing or {}), dict(imported or {})
    merged = dict(old)
    protected_name = old.get("name") or old.get("title")
    for key, value in new.items():
        if key in ("name", "title") or value in (None, "", [], {}):
            continue
        if key in ("ingredientsText", "ingredientLines"):
            old_count = len(old.get("ingredientLines") or [v for v in str(old.get("ingredientsText") or "").splitlines() if v.strip()])
            new_count = len(new.get("ingredientLines") or [v for v in str(new.get("ingredientsText") or "").splitlines() if v.strip()])
            if old_count and new_count < max(3, old_count // 2):
                continue
        if key in ("instructions", "instructionSteps"):
            old_count = len(old.get("instructionSteps") or [v for v in str(old.get("instructions") or "").splitlines() if v.strip()])
            new_count = len(new.get("instructionSteps") or [v for v in str(new.get("instructions") or "").splitlines() if v.strip()])
            if old_count and new_count < max(2, old_count // 2):
                continue
        if not old.get(key) or key in ("sourceLastChecked", "importQuality", "resolvedSourceUrl", "sourceDomain"):
            merged[key] = value
    if protected_name:
        merged["name"] = protected_name
    return merged
