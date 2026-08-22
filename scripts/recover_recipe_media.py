#!/usr/bin/env python3
"""Audit and safely recover exact-source recipe media.

Dry-run is the default. Applying requires an explicit API URL and writes a full
backup plus a reviewable diff before sending any patch. Existing images are
never replaced.
"""
import argparse
import concurrent.futures
import importlib.util
import imghdr
import json
import pathlib
import re
import ssl
import sys
import types
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
MEDIA_FIELDS = ("image", "imageUrl", "thumbnail", "thumbnailUrl", "poster", "posterUrl", "sourceImage", "videoThumbnail", "sourceScreenshot")
BOX_FIELDS = ("data", "metadata", "sourceMetadata", "importMetadata", "recoveryMetadata")
SOURCE_FIELDS = ("originalSourceUrl", "sourceUrl", "originalUrl", "link", "resolvedSourceUrl")


def meaningful_url(value):
    return isinstance(value, str) and value.strip().lower().startswith(("http://", "https://"))


def meaningful_image(value):
    return meaningful_url(value) or (isinstance(value, str) and value.strip().startswith("/assets/"))


def stored_image(recipe):
    boxes = [recipe] + [recipe.get(key) for key in BOX_FIELDS if isinstance(recipe.get(key), dict)]
    for box in boxes:
        for field in MEDIA_FIELDS:
            if meaningful_image(box.get(field)):
                return box[field].strip(), "stored-metadata"
        media = box.get("media")
        for item in media if isinstance(media, list) else ([media] if media else []):
            value = item if isinstance(item, str) else (item.get("url") or item.get("thumbnailUrl") or item.get("posterUrl") if isinstance(item, dict) else "")
            if meaningful_image(value):
                return value.strip(), "stored-metadata"
    return "", ""


def source_url(recipe):
    for field in SOURCE_FIELDS:
        if meaningful_url(recipe.get(field)):
            return recipe[field].strip()
    return ""


def load_fetch_module():
    path = ROOT / "api" / "fetch-recipe.py"
    if "api" not in sys.modules:
        package = types.ModuleType("api")
        package.__path__ = [str(ROOT / "api")]
        sys.modules["api"] = package
    spec = importlib.util.spec_from_file_location("api.fetch_recipe_media", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def method_group(result):
    method = result.get("imageMethod") or result.get("method") or ""
    if method == "video-thumbnail" or result.get("sourceType") in ("TikTok", "Instagram"):
        return "video-social-thumbnail"
    return "source-metadata"


def recover_one(recipe, fetcher):
    existing, existing_method = stored_image(recipe)
    if existing:
        recovered_method = recipe.get("imageRecoveryMethod")
        if recovered_method in ("source-metadata", "video-social-thumbnail") and recipe.get("imageSourceUrl") == source_url(recipe):
            return {"id": str(recipe.get("id", "")), "name": recipe.get("name", ""), "status": "recovered", "image": existing, "method": recovered_method, "sourceUrl": source_url(recipe)}
        return {"id": str(recipe.get("id", "")), "name": recipe.get("name", ""), "status": "already-usable", "image": existing, "method": existing_method, "sourceUrl": source_url(recipe)}
    source = source_url(recipe)
    if not source:
        return {"id": str(recipe.get("id", "")), "name": recipe.get("name", ""), "status": "unrecoverable", "method": "unrecoverable", "sourceUrl": "", "reason": "missing-source-url"}
    try:
        result = fetcher(source) or {}
        image = result.get("image") or ""
        if not meaningful_url(image):
            raise ValueError("no-authentic-image")
        return {"id": str(recipe.get("id", "")), "name": recipe.get("name", ""), "status": "recovered", "image": image.strip(), "method": method_group(result), "sourceUrl": source, "sourcePreserved": result.get("resolvedUrl", source) == source or bool(source)}
    except Exception as exc:
        return {"id": str(recipe.get("id", "")), "name": recipe.get("name", ""), "status": "unrecoverable", "method": "unrecoverable", "sourceUrl": source, "reason": str(exc)[:180]}


def read_recipes(source):
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=60) as response:
            payload = json.load(response)
    else:
        with open(source, encoding="utf-8") as handle:
            payload = json.load(handle)
    return payload.get("recipes", payload) if isinstance(payload, dict) else payload


def post_patch(api_base, row):
    body = json.dumps({"id": row["id"], "patch": {"image": row["image"], "imageRecoveryMethod": row["method"], "imageRecoveredAt": datetime.now(timezone.utc).isoformat(), "imageSourceUrl": row["sourceUrl"]}}).encode("utf-8")
    request = urllib.request.Request(api_base.rstrip("/") + "/api/save-recipe", data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.load(response)
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "save failed")


def persist_asset(row, asset_dir):
    if row["status"] != "recovered":
        return row
    if row["image"].startswith("/assets/"):
        target = ROOT / row["image"].lstrip("/")
        return {**row, "persisted": True} if target.is_file() else {**row, "status": "unrecoverable", "method": "unrecoverable", "reason": "persisted-asset-missing"}
    try:
        request = urllib.request.Request(row["image"], headers={"User-Agent": "Mozilla/5.0 (compatible; SULTMediaArchiver/1.0)"})
        try:
            import certifi
            context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            context = ssl.create_default_context()
        with urllib.request.urlopen(request, timeout=40, context=context) as response:
            raw = response.read(8_000_001)
        if not raw or len(raw) > 8_000_000:
            raise ValueError("invalid-image-size")
        kind = imghdr.what(None, raw)
        if not kind and raw.startswith(b"\xff\xd8\xff"):
            kind = "jpeg"
        extensions = {"jpeg": "jpg", "png": "png", "webp": "webp", "gif": "gif"}
        if kind not in extensions:
            raise ValueError("invalid-image-content")
        safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", row["id"]).strip("-") or "recipe"
        target = asset_dir / f"{safe_id}.{extensions[kind]}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        return {**row, "sourceImage": row["image"], "image": "/" + str(target.relative_to(ROOT)), "persisted": True}
    except Exception as exc:
        return {**row, "status": "unrecoverable", "method": "unrecoverable", "reason": f"asset-persist-failed: {str(exc)[:140]}"}


def write_report(path, recipes, rows, applied=False):
    counts = Counter(row["method"] for row in rows)
    summary = {
        "generatedAt": datetime.now(timezone.utc).isoformat(), "dryRun": not applied,
        "totalRecipes": len(recipes), "alreadyUsable": sum(row["status"] == "already-usable" for row in rows),
        "successfullyRecovered": sum(row["status"] == "recovered" for row in rows),
        "stillMissing": sum(row["status"] == "unrecoverable" for row in rows),
        "methods": {"storedMetadata": counts["stored-metadata"], "sourceMetadata": counts["source-metadata"], "videoSocialThumbnail": counts["video-social-thumbnail"], "screenshotFrame": counts["screenshot-frame"], "unrecoverable": counts["unrecoverable"]},
        "remainingUnrecoverable": [{"id": row["id"], "name": row["name"], "sourceUrl": row.get("sourceUrl", ""), "reason": row.get("reason", "")} for row in rows if row["status"] == "unrecoverable"],
        "recoveries": [row for row in rows if row["status"] == "recovered"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def write_manifest(path, rows):
    manifest = {row["id"]: {"image": row["image"], "sourceUrl": row["sourceUrl"], "method": row["method"]} for row in rows if row["status"] == "recovered"}
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_local_recipes(path, recipes, rows):
    recovered = {row["id"]: row for row in rows if row["status"] == "recovered"}
    for recipe in recipes:
        row = recovered.get(str(recipe.get("id", "")))
        prior_recovery = recipe.get("imageRecoveryMethod") in ("source-metadata", "video-social-thumbnail") and recipe.get("imageSourceUrl") == source_url(recipe)
        if row and source_url(recipe) == row["sourceUrl"] and (not stored_image(recipe)[0] or prior_recovery):
            recipe["image"] = row["image"]
            recipe["imageRecoveryMethod"] = row["method"]
            recipe["imageSourceUrl"] = row["sourceUrl"]
    path.write_text(json.dumps(recipes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(ROOT / "recipes.json"))
    parser.add_argument("--output", default=str(ROOT / "reports" / "recipe-media-recovery.json"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--apply-api", help="Explicit application base URL. Omit for dry-run.")
    parser.add_argument("--backup", help="Required with --apply-api.")
    parser.add_argument("--manifest", help="Write a reviewed static ID/source/image manifest.")
    parser.add_argument("--write-local", action="store_true", help="Populate missing image fields in a local JSON input.")
    parser.add_argument("--asset-dir", help="Archive verified source images beneath the project root.")
    args = parser.parse_args()
    recipes = read_recipes(args.input)
    fetcher = load_fetch_module().extract
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        rows = list(pool.map(lambda recipe: recover_one(recipe, fetcher), recipes))
    if args.asset_dir:
        asset_dir = pathlib.Path(args.asset_dir).resolve()
        if ROOT not in asset_dir.parents:
            parser.error("--asset-dir must be inside the project root")
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            rows = list(pool.map(lambda row: persist_asset(row, asset_dir), rows))
    applied = bool(args.apply_api)
    if applied:
        if not args.backup:
            parser.error("--backup is required with --apply-api")
        pathlib.Path(args.backup).write_text(json.dumps(recipes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for row in rows:
            if row["status"] == "recovered":
                post_patch(args.apply_api, row)
    summary = write_report(pathlib.Path(args.output), recipes, rows, applied)
    if args.manifest:
        write_manifest(pathlib.Path(args.manifest), rows)
    if args.write_local:
        if args.input.startswith(("http://", "https://")):
            parser.error("--write-local requires a local JSON input")
        write_local_recipes(pathlib.Path(args.input), recipes, rows)
    print(json.dumps({key: summary[key] for key in ("totalRecipes", "alreadyUsable", "successfullyRecovered", "stillMissing", "methods", "dryRun")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
