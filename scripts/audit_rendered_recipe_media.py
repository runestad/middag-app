#!/usr/bin/env python3
"""Read-only audit of the image path the deployed recipe card will render."""

import argparse
import concurrent.futures
import json
import pathlib
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
MEDIA_FIELDS = ("image", "imageUrl", "thumbnail", "thumbnailUrl", "poster", "posterUrl", "sourceImage", "videoThumbnail", "sourceScreenshot")
BOX_FIELDS = ("data", "metadata", "sourceMetadata", "importMetadata", "recoveryMetadata")
SOURCE_FIELDS = ("originalSourceUrl", "sourceUrl", "originalUrl", "link", "resolvedSourceUrl")


def ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def first_value(recipe, fields, boxes=True):
    containers = [recipe]
    if boxes:
        containers += [recipe.get(key) for key in BOX_FIELDS if isinstance(recipe.get(key), dict)]
    for container in containers:
        for field in fields:
            value = container.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip(), field
        media = container.get("media")
        for item in media if isinstance(media, list) else ([media] if media else []):
            value = item if isinstance(item, str) else (item.get("url") or item.get("thumbnailUrl") or item.get("posterUrl") if isinstance(item, dict) else "")
            if isinstance(value, str) and value.strip():
                return value.strip(), "media"
    return "", ""


def load_json(url_or_path):
    if url_or_path.startswith(("http://", "https://")):
        with urllib.request.urlopen(url_or_path, timeout=60, context=ssl_context()) as response:
            return json.load(response)
    return json.loads(pathlib.Path(url_or_path).read_text(encoding="utf-8"))


def loadable(url, base):
    if not url:
        return False, "no-media"
    resolved = urllib.parse.urljoin(base.rstrip("/") + "/", url)
    try:
        request = urllib.request.Request(resolved, headers={"User-Agent": "Mozilla/5.0 SULTMediaAudit/1.0", "Range": "bytes=0-2047"})
        with urllib.request.urlopen(request, timeout=20, context=ssl_context()) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            raw = response.read(2048)
        valid = response.status < 400 and (content_type.startswith("image/") or raw.startswith((b"\xff\xd8\xff", b"\x89PNG", b"RIFF", b"GIF8", b"<svg")))
        return valid, f"HTTP {response.status} {content_type or 'unknown'}"
    except Exception as exc:
        return False, str(exc)[:180]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True, help="Deployed /api/recipes URL")
    parser.add_argument("--base", required=True, help="Deployment base URL")
    parser.add_argument("--manifest", default=str(ROOT / "recipe-media-manifest.json"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = load_json(args.api)
    recipes = payload.get("recipes", payload) if isinstance(payload, dict) else payload
    manifest = load_json(args.manifest)

    def audit(recipe):
        recipe_id = str(recipe.get("id", ""))
        source, _ = first_value(recipe, SOURCE_FIELDS, boxes=False)
        preferred, preferred_field = first_value(recipe, MEDIA_FIELDS)
        verified = recipe.get("verifiedFallbackImage", "")
        entry = manifest.get(recipe_id, {})
        local_asset = verified or entry.get("image", "")
        local_path = str(ROOT / local_asset.lstrip("/")) if local_asset.startswith("/assets/") else ""
        asset_exists = bool(local_path and pathlib.Path(local_path).is_file())
        preferred_ok, preferred_reason = loadable(preferred, args.base)
        fallback_ok, fallback_reason = loadable(verified, args.base) if verified and verified != preferred else (False, "not-selected")
        renderer_chooses = preferred if preferred_ok else (verified if fallback_ok else "")
        state = "image" if renderer_chooses else "sult-fallback"
        if state == "image":
            reason = "preferred-media-loads" if renderer_chooses == preferred else "preferred-failed-verified-fallback-loads"
        elif preferred:
            reason = f"preferred-failed: {preferred_reason}; verified-fallback: {fallback_reason}"
        else:
            reason = "no-renderable-media"
        return {
            "recipeId": recipe_id, "recipeName": recipe.get("name", ""), "mediaSource": source,
            "preferredMedia": preferred, "preferredField": preferred_field,
            "localAssetPath": local_path, "assetExists": asset_exists,
            "rendererChoosesAsset": bool(renderer_chooses), "rendererChoice": renderer_chooses,
            "expectedRenderedState": state, "reasonForFallback": "" if state == "image" else reason,
            "preferredLoad": {"ok": preferred_ok, "detail": preferred_reason},
            "verifiedFallbackLoad": {"ok": fallback_ok, "detail": fallback_reason},
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        rows = list(pool.map(audit, recipes))
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(), "mode": "READ_ONLY_RENDER_PATH_AUDIT",
        "api": args.api, "totalRecipes": len(rows),
        "renderedImages": sum(row["expectedRenderedState"] == "image" for row in rows),
        "sultFallbacks": sum(row["expectedRenderedState"] == "sult-fallback" for row in rows),
        "rows": rows,
    }
    pathlib.Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("mode", "totalRecipes", "renderedImages", "sultFallbacks")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
