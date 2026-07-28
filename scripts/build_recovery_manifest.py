#!/usr/bin/env python3
"""Build the read-only Recipe Recovery manifest from reviewed local reports."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / ".data-migrations" / "20260727-203113"
RECOVERY_ROOT = REPORT_ROOT / "Recipe Recovery"
OUTPUT = ROOT / "recovery-manifest.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def source_label(path):
    value = str(path).replace("\\", "/")
    name = value.rsplit("/", 1)[-1]
    parent = value.rsplit("/", 2)[-2] if "/" in value else ""
    return f"{parent}/{name}" if parent else name


def main():
    high = load(RECOVERY_ROOT / "high-confidence-side-by-side.json")
    url_queue = load(RECOVERY_ROOT / "url-reimport-plan.json")
    recovery = load(REPORT_ROOT / "missing-recipes-recovery.json")["recipes"]

    high_ids = {str(item["id"]) for item in high}
    url_ids = {str(item["id"]) for item in url_queue}
    medium = [
        item for item in recovery
        if item.get("recoveryProbability") == "middels" and str(item["id"]) not in high_ids
    ]
    manual = [
        item for item in recovery
        if str(item["id"]) not in high_ids
        and str(item["id"]) not in url_ids
        and item not in medium
    ]

    high_items = []
    for item in high:
        candidate = item["candidateVersions"][0]
        high_items.append({
            "id": str(item["id"]),
            "name": item["name"],
            "link": item.get("link") or "",
            "missingFields": item.get("missingFields") or [],
            "productionSnapshot": item.get("production") or {},
            "candidate": candidate.get("recoverableFields") or {},
            "candidateFingerprint": candidate.get("fingerprint") or "",
            "sources": sorted({source_label(path) for path in candidate.get("sources") or []}),
            "confidence": "high",
        })

    def compact(item, confidence):
        return {
            "id": str(item["id"]),
            "name": item.get("name") or "",
            "source": item.get("source") or "",
            "link": item.get("link") or item.get("url") or "",
            "createdAt": item.get("createdAt") or "",
            "updatedAt": item.get("updatedAt") or "",
            "existingFields": item.get("existingFields") or [],
            "missingFields": item.get("missingFields") or [],
            "traces": item.get("traces") or {},
            "confidence": confidence,
        }

    manifest = {
        "version": "1.0",
        "generatedFrom": "Reviewed Recipe Recovery reports (2026-07-27)",
        "counts": {
            "total": len(high_items) + len(medium) + len(url_queue) + len(manual),
            "high": len(high_items),
            "medium": len(medium),
            "url": len(url_queue),
            "manual": len(manual),
        },
        "high": high_items,
        "medium": [compact(item, "medium") for item in medium],
        "url": [
            {
                "id": str(item["id"]),
                "name": item.get("name") or "",
                "source": item.get("sourceType") or item.get("source") or "",
                "link": item.get("url") or "",
                "missingFields": item.get("missingFields") or [],
                "confidence": "url",
            }
            for item in url_queue
        ],
        "manual": [compact(item, "manual") for item in manual],
    }
    OUTPUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
