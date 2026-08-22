"""Stored recipe completeness and source health are deliberately independent."""

import re
import urllib.parse


SOCIAL_HOSTS = ("instagram.com", "tiktok.com", "facebook.com")


def _lines(value):
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict):
                item = item.get("text") or item.get("item") or item.get("original") or ""
            text = str(item).strip()
            if text:
                result.append(text)
        return result
    return [line.strip(" \t-*\u2022") for line in str(value or "").splitlines() if line.strip(" \t-*\u2022")]


def stored_completeness(recipe):
    ingredients = max((_lines(recipe.get(key)) for key in ("structuredIngredients", "ingredientLines", "ingredientsText")), key=len)
    instructions = max((_lines(recipe.get(key)) for key in ("structuredInstructions", "instructionSteps", "instructions")), key=len)
    issues = []
    if not ingredients:
        issues.append("missing_ingredients")
    if not instructions:
        issues.append("missing_instructions")
    if len(ingredients) == 1 and len(ingredients[0]) > 400:
        issues.append("truncated_or_malformed_ingredients")
    if len(instructions) == 1 and len(instructions[0]) > 1600:
        issues.append("truncated_or_malformed_instructions")
    if issues:
        status = "INCOMPLETE"
    elif len(ingredients) >= 3 and (len(instructions) >= 2 or len(instructions[0]) >= 35):
        status = "COMPLETE"
    else:
        status = "PROBABLY_COMPLETE"
    return {"status": status, "issues": issues, "ingredientCount": len(ingredients),
            "instructionCount": len(instructions), "needsManualRecovery": status == "INCOMPLETE"}


def classify_source(url):
    raw = str(url or "").strip()
    if not raw:
        return "NO_SOURCE"
    try:
        parsed = urllib.parse.urlparse(raw)
    except ValueError:
        return "MALFORMED_URL"
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "MALFORMED_URL"
    host, path = parsed.hostname.lower(), parsed.path.lower()
    if "tiktok.com" in host:
        return "TIKTOK_VIDEO" if re.search(r"/@[^/]+/video/\d+|/t/[a-z0-9]+", path) or host.startswith("vm.") else "TIKTOK_OTHER"
    if "instagram.com" in host:
        if re.match(r"^/(reel|reels)/", path):
            return "INSTAGRAM_REEL"
        if re.match(r"^/p/", path):
            return "INSTAGRAM_POST"
        return "INSTAGRAM_OTHER"
    if "facebook.com" in host:
        return "FACEBOOK_POST"
    return "WEBSITE"


def source_health(source_type, extracted=None, error=""):
    text = str(error or "").lower()
    if any(token in text for token in ("404", "410", "removed", "private", "not found")):
        return "SOURCE_REMOVED_OR_PRIVATE"
    if any(token in text for token in ("login", "sign in", "captcha")):
        return "SOURCE_REMOVED_OR_PRIVATE"
    if error:
        return "SOURCE_INACCESSIBLE"
    quality = (extracted or {}).get("importQuality") or {}
    if source_type.startswith(("TIKTOK", "INSTAGRAM")) and quality.get("status") not in ("COMPLETE", "PROBABLY_COMPLETE"):
        return "SOCIAL_REACHABLE_NOT_MACHINE_READABLE"
    if (extracted or {}).get("resolvedUrl") and not (extracted or {}).get("caption"):
        return "REDIRECT_ISSUE"
    return "HEALTHY_SOURCE"
