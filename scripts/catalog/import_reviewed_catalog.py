#!/usr/bin/env python3
"""Import reviewed motorcycle spare-part research records as DRAFT products.

Input is a JSON array. This tool never publishes products, never uploads/copies
third-party images, and refuses non-product/category/shop pages. It uses the
existing FastAPI catalog mutation endpoint so server-side RBAC, RLS, audit,
and idempotency remain authoritative.

Required environment:
  OTOCLINIC_API_BASE_URL (defaults to production API URL)
  OTOCLINIC_ADMIN_BEARER_TOKEN (active, authorized staff session token)

Run:
  python scripts/catalog/import_reviewed_catalog.py --input reviewed-products.json --dry-run
  python scripts/catalog/import_reviewed_catalog.py --input reviewed-products.json --apply

Every record must have record_type="product", canonical product_detail_url,
title, category, condition, listed_price_idr, source evidence, and a rights
status for image handling. Records with unknown condition/price are rejected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_API = "https://otoclinic-api-production.up.railway.app"
ALLOWED_CONDITIONS = {
    "new_oem",
    "new_aftermarket",
    "used",
    "refurbished",
    "remanufactured",
    "damaged_for_parts",
}


def fail(message: str) -> None:
    raise ValueError(message)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:110].strip("-") or "spare-part"


def stable_sku(record: dict[str, Any]) -> str:
    supplied = str(record.get("sku") or "").strip()
    if supplied:
        return supplied[:120]
    source = str(record["product_detail_url"]).strip()
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16].upper()
    return f"SRC-MOTO-{digest}"


def validate(record: Any, index: int) -> dict[str, Any]:
    if not isinstance(record, dict):
        fail(f"record[{index}] must be an object")
    if record.get("record_type") != "product":
        fail(f"record[{index}] is a lead/shop/category page, not a verified product record")
    title = str(record.get("title") or "").strip()
    url = str(record.get("product_detail_url") or "").strip()
    parsed = urlparse(url)
    if not title or len(title) < 5:
        fail(f"record[{index}] needs a descriptive title")
    if parsed.scheme != "https" or parsed.hostname not in {"shopee.co.id", "www.tokopedia.com", "lazada.co.id", "www.lazada.co.id"}:
        fail(f"record[{index}] product_detail_url must be a supported HTTPS product page")
    if not re.search(r"(?:-i\.\d+\.\d+|/product/\d+/\d+|/products/)", parsed.path):
        fail(f"record[{index}] URL does not look like a canonical product-detail URL")
    condition = str(record.get("condition") or "").strip().lower()
    if condition not in ALLOWED_CONDITIONS:
        fail(f"record[{index}] has unknown/unsupported condition")
    category = str(record.get("category") or "").strip()
    if not category:
        fail(f"record[{index}] needs a normalized category")
    price = record.get("listed_price_idr")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or price < 0:
        fail(f"record[{index}] needs an observed listed_price_idr")
    evidence = str(record.get("source_evidence") or "").strip()
    if not evidence:
        fail(f"record[{index}] needs a source evidence excerpt")
    captured_at = str(record.get("captured_at") or "").strip()
    if not captured_at:
        fail(f"record[{index}] needs captured_at timestamp")
    rights_status = str(record.get("image_rights_status") or "unverified").strip().lower()
    if rights_status not in {"unverified", "permission_granted", "licensed", "original_created", "rejected", "not_applicable"}:
        fail(f"record[{index}] has invalid image_rights_status")
    return {
        "title": title,
        "url": url,
        "condition": condition,
        "category": category,
        "price": int(price),
        "brand": str(record.get("brand") or "").strip() or None,
        "part_number": str(record.get("part_number") or "").strip() or None,
        "description": str(record.get("description") or evidence).strip(),
        "evidence": evidence,
        "captured_at": captured_at,
        "rights_status": rights_status,
        "sku": stable_sku(record),
    }


def post_product(api: str, token: str, product: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "sku": product["sku"],
        "slug": slugify(product["title"]) + "-" + hashlib.sha256(product["url"].encode()).hexdigest()[:8],
        "name": product["title"][:240],
        "description": product["description"][:5000],
        "brand": product["brand"],
        "part_number": product["part_number"],
        "category": product["category"][:80],
        "condition": product["condition"],
        "condition_grade": None,
        "package_quantity": 1,
        "warranty_days": 0,
        "retail_price": product["price"],
        "fitment_summary": None,
        "source_rights_evidence": json.dumps({
            "source_url": product["url"],
            "source_evidence": product["evidence"],
            "captured_at": product["captured_at"],
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "image_rights_status": product["rights_status"],
            "images_imported": False,
            "publication_note": "Draft only; requires source, image rights, stock and fitment review.",
        }, ensure_ascii=False, separators=(",", ":")),
    }
    request_id = str(uuid.uuid5(uuid.NAMESPACE_URL, product["url"]))
    body = json.dumps({
        "action": "create_product",
        "payload": payload,
    }).encode("utf-8")
    req = urllib.request.Request(
        api.rstrip("/") + "/v1/admin/catalog/mutations",
        data=body,
        method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Idempotency-Key": request_id,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return {"status": response.status, "body": json.loads(response.read().decode("utf-8"))}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        return {"status": exc.code, "error": detail}
    except urllib.error.URLError as exc:
        return {"status": 0, "error": str(exc.reason)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path, help="JSON array of reviewed product records")
    parser.add_argument("--dry-run", action="store_true", help="Validate only; no API calls")
    parser.add_argument("--apply", action="store_true", help="Create draft products through the authorized API")
    args = parser.parse_args()
    if args.dry_run == args.apply:
        parser.error("choose exactly one of --dry-run or --apply")
    try:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            fail("input must be a JSON array")
        products = [validate(record, i) for i, record in enumerate(raw)]
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps({
            "ok": True,
            "validated_records": len(products),
            "note": "Validation only. No API/database changes were made.",
            "eligible_conditions": sorted(ALLOWED_CONDITIONS),
        }, ensure_ascii=False))
        return 0

    token = os.environ.get("OTOCLINIC_ADMIN_BEARER_TOKEN", "").strip()
    if not token:
        print("OTOCLINIC_ADMIN_BEARER_TOKEN is required for --apply", file=sys.stderr)
        return 2
    api = os.environ.get("OTOCLINIC_API_BASE_URL", DEFAULT_API).strip()
    results = []
    for product in products:
        result = post_product(api, token, product)
        results.append({
            "sku": product["sku"],
            "source_url": product["url"],
            **result,
        })
    ok_count = sum(200 <= int(row.get("status", 0)) < 300 for row in results)
    print(json.dumps({
        "validated_records": len(products),
        "created_or_replayed": ok_count,
        "failed": len(results) - ok_count,
        "results": results,
        "note": "Products are created as draft only; no images are uploaded and nothing is published.",
    }, ensure_ascii=False))
    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
