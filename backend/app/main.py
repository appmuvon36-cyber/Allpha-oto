import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from html import unescape as html_unescape
import hashlib
import re
from typing import Any
from urllib.parse import quote, urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "OtoClinic API"
    environment: str = "production"
    allowed_origins: str = (
        "http://localhost:3000,http://localhost:3001,"
        "https://otoclinic-web-production.up.railway.app,"
        "https://otoclinic-admin-production.up.railway.app"
    )
    supabase_url: str = ""
    supabase_anon_key: str = ""
    # RajaOngkir shipping-cost integration. API key and origin ID remain unset
    # until the owner adds a real key and resolves the warehouse destination ID.
    rajaongkir_api_key: str = ""
    rajaongkir_quote_signing_secret: str = ""
    rajaongkir_base_url: str = "https://rajaongkir.komerce.id/api/v1"
    rajaongkir_origin_address: str = ""
    rajaongkir_origin_search: str = ""
    rajaongkir_origin_id: str = ""
    rajaongkir_default_couriers: str = "jne:jnt:sicepat:ide:sap:ninja:tiki:lion:anteraja:pos"
    rajaongkir_quote_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    # International WhatsApp Business number (digits with country code, e.g. 62...).
    whatsapp_business_phone: str = ""
    # Optional WhatsApp Cloud API adapter; never expose these values to the browser.
    whatsapp_cloud_api_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_graph_api_version: str = ""
    whatsapp_order_status_template: str = ""
    whatsapp_template_language: str = "id"
    integration_worker_secret: str = ""
    whatsapp_webhook_verify_token: str = ""
    whatsapp_app_secret: str = ""
    # RajaOngkir/Komerce Payment API; credentials are server-side only.
    rajaongkir_payment_api_key: str = ""
    rajaongkir_payment_environment: str = "sandbox"
    rajaongkir_payment_callback_secret: str = ""
    rajaongkir_payment_callback_url: str = "https://otoclinic-api-production.up.railway.app/v1/webhooks/rajaongkir"
    supabase_service_role_key: str = ""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
app = FastAPI(
    title=settings.app_name,
    version="0.4.0",
    docs_url=None if settings.environment.lower() == "production" else "/docs",
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
)


@app.middleware("http")
async def attach_correlation_id(request, call_next):
    supplied = request.headers.get("X-Request-ID", "").strip()
    correlation_id = supplied if re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", supplied) else str(uuid4())
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = correlation_id
    return response

bearer_scheme = HTTPBearer(auto_error=False)
PRODUCT_CONDITIONS = {
    "new_oem", "new_aftermarket", "used", "refurbished", "remanufactured", "damaged_for_parts"
}
VEHICLE_TYPES = {"motorcycle", "car", "commercial", "other"}


def require_supabase_configuration() -> tuple[str, str]:
    url = settings.supabase_url.rstrip("/")
    key = settings.supabase_anon_key
    if not url or not key:
        raise HTTPException(status_code=503, detail="Supabase Auth is not configured on the API service.")
    return url, key


async def get_current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    """Verify a Supabase bearer token and resolve only the caller's own profile."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer access token required.")

    supabase_url, anon_key = require_supabase_configuration()
    access_token = credentials.credentials
    headers = {"apikey": anon_key, "Authorization": f"Bearer {access_token}"}

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            auth_response = await client.get(f"{supabase_url}/auth/v1/user", headers=headers)
            if auth_response.status_code in (401, 403):
                raise HTTPException(status_code=401, detail="Invalid or expired access token.")
            if auth_response.status_code == 429 or auth_response.status_code >= 500:
                raise HTTPException(status_code=503, detail="Supabase Auth is temporarily unavailable.")
            if auth_response.status_code != 200:
                raise HTTPException(status_code=401, detail="Access token could not be verified.")

            auth_user = auth_response.json()
            user_id = auth_user.get("id")
            if not user_id:
                raise HTTPException(status_code=401, detail="Verified identity is missing a user ID.")

            profile_response = await client.get(
                f"{supabase_url}/rest/v1/user_profiles",
                params={"id": f"eq.{user_id}", "select": "id,display_name,phone,role,is_active", "limit": "1"},
                headers={**headers, "Accept": "application/json"},
            )
            if profile_response.status_code in (401, 403):
                raise HTTPException(
                    status_code=503,
                    detail="Profile access is not available under the current database policies.",
                )
            if profile_response.status_code == 429 or profile_response.status_code >= 500:
                raise HTTPException(status_code=503, detail="Profile service is temporarily unavailable.")
            if profile_response.status_code != 200:
                raise HTTPException(status_code=503, detail="Profile lookup failed.")

            profiles = profile_response.json()
            profile = profiles[0] if profiles else None
            if profile and profile.get("is_active") is False:
                raise HTTPException(status_code=403, detail="This account is inactive.")

            return {
                "user": {"id": user_id, "email": auth_user.get("email")},
                "profile": profile,
                "role": profile.get("role") if profile else None,
                "_access_token": access_token,
            }
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=503, detail="Supabase request timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Could not reach Supabase.") from exc


async def require_active_profile(
    identity: dict[str, Any] = Depends(get_current_identity),
) -> dict[str, Any]:
    profile = identity.get("profile")
    if not isinstance(profile, dict) or profile.get("is_active") is not True:
        raise HTTPException(status_code=403, detail="An active, provisioned user profile is required.")
    return identity


def require_roles(*allowed_roles: str) -> Callable[..., Any]:
    """Require an active profile and an explicit allowlisted role."""
    normalized_roles = frozenset(role.strip().lower() for role in allowed_roles if role.strip())
    if not normalized_roles:
        raise ValueError("require_roles needs at least one non-empty role.")

    async def role_dependency(
        identity: dict[str, Any] = Depends(get_current_identity),
    ) -> dict[str, Any]:
        profile = identity.get("profile")
        if not isinstance(profile, dict) or profile.get("is_active") is not True:
            raise HTTPException(status_code=403, detail="An active, provisioned user profile is required.")
        role = profile.get("role")
        if not isinstance(role, str) or role.strip().lower() not in normalized_roles:
            raise HTTPException(status_code=403, detail="Your role is not allowed to perform this action.")
        return identity

    return role_dependency


async def supabase_get(
    table: str,
    params: dict[str, str],
    access_token: str | None = None,
) -> list[dict[str, Any]]:
    """Read through Supabase REST using anon key and optional caller JWT; RLS remains authoritative."""
    supabase_url, anon_key = require_supabase_configuration()
    headers = {"apikey": anon_key, "Accept": "application/json"}
    headers["Authorization"] = f"Bearer {access_token}" if access_token else f"Bearer {anon_key}"

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(f"{supabase_url}/rest/v1/{table}", params=params, headers=headers)
        if response.status_code in (401, 403):
            raise HTTPException(status_code=503, detail="Data access is unavailable under current database policies.")
        if response.status_code == 429 or response.status_code >= 500:
            raise HTTPException(status_code=503, detail="Data service is temporarily unavailable.")
        if response.status_code != 200:
            raise HTTPException(status_code=503, detail="Data query failed.")
        rows = response.json()
        if not isinstance(rows, list):
            raise HTTPException(status_code=503, detail="Data service returned an invalid response.")
        return rows
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=503, detail="Data request timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Could not reach the data service.") from exc



async def supabase_rpc(function: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Call an explicitly allowlisted public, read-only RPC using the anon key."""
    if function not in {"oto_public_stock_status", "oto_public_product_categories", "oto_public_homepage_best_sellers", "oto_public_homepage_popular"}:
        raise HTTPException(status_code=422, detail="Unsupported public RPC.")
    supabase_url, anon_key = require_supabase_configuration()
    headers = {"apikey": anon_key, "Authorization": f"Bearer {anon_key}", "Content-Type": "application/json", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(f"{supabase_url}/rest/v1/rpc/{function}", headers=headers, json=payload)
        if response.status_code == 429 or response.status_code >= 500:
            raise HTTPException(status_code=503, detail="Public catalog availability is temporarily unavailable.")
        if response.status_code != 200:
            raise HTTPException(status_code=503, detail="Public catalog availability could not be read.")
        data = response.json()
        if not isinstance(data, list):
            raise HTTPException(status_code=503, detail="Public catalog availability returned an invalid response.")
        return data
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=503, detail="Public catalog availability request timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Could not reach public catalog availability.") from exc


async def record_product_search_events(query: str, product_ids: list[str]) -> None:
    """Record only products returned by a real search; service credentials never leave the API."""
    if not settings.supabase_service_role_key or not product_ids:
        return
    supabase_url = settings.supabase_url.rstrip("/")
    if not supabase_url:
        return
    normalized = re.sub(r"[^a-z0-9]+", " ", query.casefold()).strip()[:100]
    if len(normalized) < 2:
        return
    payload = [{"normalized_query": normalized, "product_id": product_id} for product_id in list(dict.fromkeys(product_ids))[:20]]
    headers = {"apikey": settings.supabase_service_role_key, "Authorization": f"Bearer {settings.supabase_service_role_key}", "Content-Type": "application/json", "Prefer": "return=minimal"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{supabase_url}/rest/v1/oto_product_search_events", headers=headers, json=payload)
    except httpx.HTTPError:
        # Search remains available if optional analytics logging is temporarily unavailable.
        return


async def supabase_write(method: str, table: str, access_token: str, payload: dict[str, Any], filters: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Write allowlisted payloads through PostgREST with the caller JWT; RLS remains authoritative."""
    if method not in {"POST", "PATCH"} or table not in {"product_categories", "product_media", "sourcing_requests", "oto_coupons", "oto_wishlist_items", "oto_saved_vehicles", "oto_notifications", "part_number_cross_references", "oto_homepage_settings", "oto_homepage_promotions"}:
        raise HTTPException(status_code=422, detail="Unsupported data mutation.")
    supabase_url, anon_key = require_supabase_configuration()
    headers = {"apikey": anon_key, "Authorization": f"Bearer {access_token}", "Content-Type": "application/json", "Accept": "application/json", "Prefer": "return=representation"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(method, f"{supabase_url}/rest/v1/{table}", params=filters or {}, headers=headers, json=payload)
        if response.status_code in (401, 403): raise HTTPException(status_code=403, detail="This data mutation is not permitted.")
        if response.status_code == 409: raise HTTPException(status_code=409, detail="A request with this key already exists.")
        if response.status_code == 429 or response.status_code >= 500: raise HTTPException(status_code=503, detail="Data service is temporarily unavailable.")
        if response.status_code not in (200, 201, 204):
            try: code = str(response.json().get("code", ""))
            except (ValueError, AttributeError): code = ""
            if code in {"23505"}: raise HTTPException(status_code=409, detail="A request with this key or unique value already exists.")
            if code in {"23514", "23502", "22P02"}: raise HTTPException(status_code=422, detail="Submitted data failed validation.")
            raise HTTPException(status_code=503, detail="Data mutation could not be completed.")
        data = response.json() if response.content else []
        return data if isinstance(data, list) else []
    except HTTPException: raise
    except httpx.TimeoutException as exc: raise HTTPException(status_code=503, detail="Data request timed out.") from exc
    except httpx.HTTPError as exc: raise HTTPException(status_code=503, detail="Could not reach data service.") from exc


async def supabase_count(
    table: str,
    params: dict[str, str],
    access_token: str,
    select_column: str = "id",
) -> int:
    """Count rows visible to the caller under Postgres grants and RLS."""
    supabase_url, anon_key = require_supabase_configuration()
    query = {"select": select_column, "limit": "1", **params}
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Prefer": "count=exact",
        "Range": "0-0",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(f"{supabase_url}/rest/v1/{table}", params=query, headers=headers)
        if response.status_code in (401, 403):
            raise HTTPException(status_code=503, detail="Dashboard data is unavailable under current database policies.")
        if response.status_code == 429 or response.status_code >= 500:
            raise HTTPException(status_code=503, detail="Dashboard data service is temporarily unavailable.")
        if response.status_code not in (200, 206):
            raise HTTPException(status_code=503, detail="Dashboard count query failed.")
        content_range = response.headers.get("content-range", "")
        total = content_range.rsplit("/", 1)[-1] if "/" in content_range else ""
        if not total.isdigit():
            raise HTTPException(status_code=503, detail="Dashboard count response was incomplete.")
        return int(total)
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=503, detail="Dashboard count request timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Could not reach dashboard data service.") from exc

def safe_search_term(value: str) -> str:
    """Keep user search input from altering PostgREST filter grammar."""
    return re.sub(r"[^\w .\-]", " ", value, flags=re.UNICODE).strip()


def normalize_part_number(value: str) -> str:
    """Normalize OEM/SKU-like identifiers without claiming semantic equivalence."""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _score_part_search_candidate(query: str, product: dict[str, Any]) -> tuple[int, list[str]]:
    """Deterministic retrieval score for ordering candidates; it is not a probability."""
    needle = normalize_part_number(query)
    part = normalize_part_number(str(product.get("part_number") or ""))
    sku = normalize_part_number(str(product.get("sku") or ""))
    name = normalize_part_number(str(product.get("name") or ""))
    brand = normalize_part_number(str(product.get("brand") or ""))
    if not needle:
        return 0, []
    if part and needle == part:
        return 100, ["Nomor part cocok persis setelah normalisasi."]
    if sku and needle == sku:
        return 97, ["SKU cocok persis setelah normalisasi."]
    if name and needle == name:
        return 90, ["Nama produk cocok persis setelah normalisasi."]
    if len(needle) >= 4 and part and (part.startswith(needle) or needle.startswith(part)):
        return 86, ["Nomor part memiliki kecocokan awalan."]
    if len(needle) >= 4 and part and (needle in part or part in needle):
        return 78, ["Nomor part memiliki kecocokan sebagian."]
    if len(needle) >= 4 and sku and (needle in sku or sku in needle):
        return 72, ["SKU memiliki kecocokan sebagian."]
    if len(needle) >= 4 and name and needle in name:
        return 65, ["Nama produk memuat istilah pencarian."]
    if len(needle) >= 4 and brand and needle in brand:
        return 55, ["Merek memuat istilah pencarian."]
    query_tokens = set(re.findall(r"[A-Z0-9]+", query.upper()))
    searchable_tokens = set(re.findall(
        r"[A-Z0-9]+",
        " ".join(str(product.get(key) or "") for key in ("name", "brand", "part_number", "sku")).upper(),
    ))
    overlap = query_tokens & searchable_tokens
    if query_tokens and overlap:
        ratio = len(overlap) / len(query_tokens)
        return 35 + round(35 * ratio), [f"{len(overlap)} dari {len(query_tokens)} token pencarian cocok."]
    return 20, ["Ditemukan melalui pencarian teks; relevansi perlu diperiksa manual."]


def _unwrap_relation(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        value = value[0] if value else {}
    return value if isinstance(value, dict) else {}


def _fitment_matches_vehicle(
    fitment: dict[str, Any],
    variant_id: UUID | None,
    model_id: UUID | None,
    make_id: UUID | None,
    vehicle_year: int | None,
) -> tuple[bool, int, list[str]]:
    """Return a ranking boost only for a fitment already marked verified in the database."""
    variant = _unwrap_relation(fitment.get("vehicle_variants"))
    model = _unwrap_relation(variant.get("vehicle_models"))
    make = _unwrap_relation(model.get("vehicle_makes"))
    if not variant:
        return False, 0, []
    if variant_id and str(variant.get("id")) != str(variant_id):
        return False, 0, []
    if model_id and str(model.get("id")) != str(model_id):
        return False, 0, []
    if make_id and str(make.get("id")) != str(make_id):
        return False, 0, []
    if vehicle_year is not None:
        year_start = variant.get("year_start")
        year_end = variant.get("year_end")
        if year_start is None or year_end is None or not int(year_start) <= vehicle_year <= int(year_end):
            return False, 0, []
    reasons = ["Memiliki bukti fitment yang sudah berstatus verified untuk pilihan kendaraan."]
    boost = 30 if variant_id else 20 if model_id else 12 if make_id else 8
    if vehicle_year is not None:
        boost += 8
        reasons.append(f"Rentang tahun fitment mencakup {vehicle_year}.")
    return True, boost, reasons


def _cross_reference_matches_product(
    mapping: dict[str, Any], query_normalized: str, product: dict[str, Any]
) -> bool:
    canonical = str(mapping.get("canonical_normalized") or "")
    alternate = str(mapping.get("alternate_normalized") or "")
    part = normalize_part_number(str(product.get("part_number") or ""))
    return (
        query_normalized in {canonical, alternate}
        and part in {canonical, alternate}
        and part != query_normalized
    )


@app.get("/v1/search/parts", tags=["search"])
async def search_part_candidates(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=10, ge=1, le=20),
    vehicle_variant_id: UUID | None = Query(default=None),
    vehicle_model_id: UUID | None = Query(default=None),
    vehicle_make_id: UUID | None = Query(default=None),
    vehicle_year: int | None = Query(default=None, ge=1900, le=2200),
) -> dict[str, Any]:
    """Rank published catalog candidates by text, approved cross-references and verified vehicle evidence."""
    normalized_query = normalize_part_number(q)
    if len(normalized_query) < 2:
        raise HTTPException(status_code=422, detail="Masukkan minimal dua huruf atau angka yang dapat dicari.")
    if vehicle_year is not None and not any((vehicle_variant_id, vehicle_model_id, vehicle_make_id)):
        raise HTTPException(status_code=422, detail="Pilih merek, model, atau varian kendaraan saat menyertakan tahun.")
    safe_query = safe_search_term(q)
    variants = list(dict.fromkeys(term for term in (safe_query, normalized_query) if term))

    # Only approved mappings with explicit source provenance are eligible for public retrieval.
    cross_references = await supabase_get(
        "part_number_cross_references",
        {
            "select": "id,canonical_part_number,alternate_part_number,canonical_normalized,alternate_normalized,canonical_type,alternate_type,relation_type,manufacturer,source_type,source_name,source_url,source_reference,source_checked_at,review_status,reviewed_at",
            "or": f"(canonical_normalized.eq.{normalized_query},alternate_normalized.eq.{normalized_query})",
            "review_status": "eq.approved",
            "limit": "50",
        },
    )
    cross_references = [
        row for row in cross_references
        if row.get("review_status") == "approved"
        and row.get("source_type") in {
            "manufacturer_catalog", "oem_catalog", "authorized_distributor_catalog",
            "tecdoc", "verified_supplier_catalog",
        }
        and str(row.get("source_url") or "").startswith(("https://", "http://"))
    ]
    search_terms = list(variants)
    for mapping in cross_references:
        for field in ("canonical_part_number", "alternate_part_number", "canonical_normalized", "alternate_normalized"):
            value = safe_search_term(str(mapping.get(field) or ""))
            if value and value not in search_terms:
                search_terms.append(value)

    clauses: list[str] = []
    for term in search_terms:
        for field in ("part_number", "sku", "name", "brand"):
            clauses.append(f"{field}.ilike.*{term}*")
    for token in re.findall(r"[A-Za-z0-9]+", q):
        if len(token) >= 3:
            safe_token = safe_search_term(token)
            if safe_token:
                for field in ("part_number", "sku", "name", "brand"):
                    clauses.append(f"{field}.ilike.*{safe_token}*")
    params = {
        "select": "id,sku,slug,name,description,brand,part_number,category,condition,condition_grade,package_quantity,warranty_days,currency,retail_price,fitment_summary,published_at,status",
        "status": "eq.published",
        "or": f"({','.join(dict.fromkeys(clauses))})",
        "order": "name.asc",
        "limit": "100",
    }
    retrieved_products = await supabase_get("products", params)
    # The live catalog has contained a row marked published whose own metadata says draft/unverified.
    products = [
        row for row in retrieved_products
        if "belum diverifikasi" not in str(row.get("condition_grade") or "").casefold()
        and "belum diverifikasi" not in str(row.get("description") or "").casefold()
        and "kandidat draft" not in str(row.get("description") or "").casefold()
        and "tetap draft" not in str(row.get("description") or "").casefold()
        and "hanya untuk review internal" not in str(row.get("description") or "").casefold()
    ]
    product_ids = list(dict.fromkeys(str(row["id"]) for row in products if row.get("id")))
    fitments_by_product: dict[str, list[dict[str, Any]]] = {product_id: [] for product_id in product_ids}
    if product_ids:
        fitment_rows = await supabase_get(
            "product_fitments",
            {
                "select": "product_id,variant_id,status,evidence_url,evidence_note,verified_at,vehicle_variants(id,name,year_start,year_end,engine_code,vehicle_models(id,name,vehicle_makes(id,name)))",
                "product_id": f"in.({','.join(product_ids)})",
                "status": "eq.verified",
                "limit": "500",
            },
        )
        for fitment in fitment_rows:
            product_id = str(fitment.get("product_id") or "")
            if product_id in fitments_by_product:
                fitments_by_product[product_id].append(fitment)

    vehicle_filter_requested = any((vehicle_variant_id, vehicle_model_id, vehicle_make_id, vehicle_year is not None))
    ranked: list[dict[str, Any]] = []
    for product in products:
        text_score, reasons = _score_part_search_candidate(q, product)
        product_id = str(product.get("id") or "")
        verified_fitments = fitments_by_product.get(product_id, [])
        matched_mappings = [
            mapping for mapping in cross_references
            if _cross_reference_matches_product(mapping, normalized_query, product)
        ]
        if matched_mappings and text_score < 95:
            text_score = 95
            reasons.append("Nomor part terkait melalui cross-reference yang disetujui; periksa bukti sumber sebelum menyimpulkan kompatibilitas.")

        vehicle_matched = False
        vehicle_boost = 0
        vehicle_reasons: list[str] = []
        for fitment in verified_fitments:
            matched, boost, fitment_reasons = _fitment_matches_vehicle(
                fitment, vehicle_variant_id, vehicle_model_id, vehicle_make_id, vehicle_year
            )
            if matched and boost > vehicle_boost:
                vehicle_matched, vehicle_boost, vehicle_reasons = True, boost, fitment_reasons
        uncertainty = ["Skor adalah heuristik pengurutan, bukan probabilitas kecocokan."]
        if not verified_fitments:
            uncertainty.append("Tidak ada bukti fitment terverifikasi yang dikembalikan untuk kandidat ini.")
        if vehicle_filter_requested and not vehicle_matched:
            uncertainty.append("Belum ada bukti fitment terverifikasi yang cocok dengan kendaraan pilihan; kandidat ini tidak boleh dianggap kompatibel.")
        if not product.get("condition") or product.get("condition") == "unknown":
            uncertainty.append("Kondisi produk belum terverifikasi secara memadai.")
        uncertainty.append("Stok dan ongkos kirim tidak diverifikasi oleh endpoint pencarian ini.")
        ranked.append({
            "product": product,
            "match_score": text_score,
            "vehicle_relevance_score": vehicle_boost,
            "relevance_score": text_score + vehicle_boost,
            "match_strength": "exact" if text_score >= 97 else "strong" if text_score >= 78 else "partial" if text_score >= 55 else "weak",
            "match_reasons": reasons,
            "vehicle_match_status": "verified_fitment_match" if vehicle_matched else "no_verified_match" if vehicle_filter_requested else "not_requested",
            "vehicle_match_reasons": vehicle_reasons,
            "verified_fitments": verified_fitments,
            "matched_cross_references": [
                {
                    "id": mapping.get("id"),
                    "canonical_part_number": mapping.get("canonical_part_number"),
                    "alternate_part_number": mapping.get("alternate_part_number"),
                    "canonical_type": mapping.get("canonical_type"),
                    "alternate_type": mapping.get("alternate_type"),
                    "relation_type": mapping.get("relation_type"),
                    "source_type": mapping.get("source_type"),
                    "source_name": mapping.get("source_name"),
                    "source_url": mapping.get("source_url"),
                    "review_status": mapping.get("review_status"),
                    "reviewed_at": mapping.get("reviewed_at"),
                } for mapping in matched_mappings
            ],
            "uncertainty": uncertainty,
        })
    ranked.sort(key=lambda item: (
        0 if item["vehicle_match_status"] == "verified_fitment_match" else 1,
        -item["relevance_score"],
        str(item["product"].get("name") or "").casefold(),
    ))
    candidates = ranked[:limit]
    candidate_ids = [str(item["product"].get("id")) for item in candidates if item["product"].get("id")]
    await record_product_search_events(q, candidate_ids)
    try:
        media_by_product = await public_product_media(candidate_ids)
    except HTTPException:
        media_by_product = {}
    stock_by_product: dict[str, dict[str, Any]] = {}
    if candidate_ids:
        try:
            stock_rows = await supabase_rpc("oto_public_stock_status", {"p_product_ids": candidate_ids})
            stock_by_product = {
                str(item["product_id"]): {"stock_status": item["stock_status"], "stock_checked_at": item.get("checked_at")}
                for item in stock_rows if item.get("product_id")
            }
        except HTTPException:
            # Search relevance must remain available if optional public stock summary is unavailable.
            stock_by_product = {}
    for item in candidates:
        product = item["product"]
        product_id = str(product.get("id") or "")
        product["images"] = media_by_product.get(product_id, [])
        product["image_url"] = next(
            (media["url"] for media in product["images"] if media.get("is_primary")),
            product["images"][0]["url"] if product["images"] else None,
        )
        product["stock_status"] = stock_by_product.get(product_id, {}).get("stock_status", "unverified")
        product["stock_checked_at"] = stock_by_product.get(product_id, {}).get("stock_checked_at")
    return {
        "query": q,
        "normalized_query": normalized_query,
        "scoring_method": "deterministic_heuristic_not_probability",
        "vehicle_filter": {
            "variant_id": str(vehicle_variant_id) if vehicle_variant_id else None,
            "model_id": str(vehicle_model_id) if vehicle_model_id else None,
            "make_id": str(vehicle_make_id) if vehicle_make_id else None,
            "year": vehicle_year,
            "verified_fitment_is_required_for_compatibility_claim": True,
        },
        "items": candidates,
        "count": len(candidates),
        "candidate_count_before_limit": len(ranked),
        "limit": limit,
        "notice": "Hasil pencarian adalah kandidat. Cross-reference hanya memakai sumber yang disetujui; skor tidak mengubah status fitment. Verifikasi nomor part, kondisi, fitment, stok, dan sumber sebelum membeli atau memublikasikan data.",
    }


class PartNumberMappingCreate(BaseModel):
    canonical_part_number: str = Field(min_length=1, max_length=120)
    alternate_part_number: str = Field(min_length=1, max_length=120)
    canonical_type: str
    alternate_type: str
    relation_type: str = "cross_reference"
    manufacturer: str | None = Field(default=None, max_length=180)
    source_type: str
    source_name: str = Field(min_length=2, max_length=180)
    source_url: str = Field(min_length=8, max_length=1000)
    source_reference: str | None = Field(default=None, max_length=300)
    review_note: str | None = Field(default=None, max_length=1000)
    model_config = {"extra": "forbid"}


class PartNumberMappingReview(BaseModel):
    action: str
    review_note: str | None = Field(default=None, max_length=1000)
    model_config = {"extra": "forbid"}


@app.get("/v1/admin/part-number-mappings", tags=["admin-search"])
async def list_part_number_mappings(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    identity: dict[str, Any] = Depends(require_roles("admin", "catalog_editor", "moderator")),
) -> dict[str, Any]:
    rows = await supabase_get(
        "part_number_cross_references",
        {"select": "id,canonical_part_number,alternate_part_number,canonical_type,alternate_type,relation_type,manufacturer,source_type,source_name,source_url,source_reference,source_checked_at,review_status,review_note,reviewed_by,reviewed_at,created_by,created_at,updated_at", "order": "created_at.desc", "limit": str(limit), "offset": str(offset)},
        access_token=identity["_access_token"],
    )
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset}


@app.post("/v1/admin/part-number-mappings", tags=["admin-search"], status_code=201)
async def create_part_number_mapping(
    request: PartNumberMappingCreate = Body(...),
    identity: dict[str, Any] = Depends(require_roles("admin", "catalog_editor", "moderator")),
) -> dict[str, Any]:
    allowed_sources = {"manufacturer_catalog", "oem_catalog", "authorized_distributor_catalog", "tecdoc", "verified_supplier_catalog"}
    if request.canonical_type not in {"oem", "aftermarket"} or request.alternate_type not in {"oem", "aftermarket"} or request.canonical_type == request.alternate_type:
        raise HTTPException(status_code=422, detail="Pemetaan harus menyatakan satu nomor OEM dan satu nomor aftermarket.")
    if request.relation_type not in {"cross_reference", "supersedes", "replaces"}:
        raise HTTPException(status_code=422, detail="Jenis relasi nomor part tidak didukung.")
    if request.source_type not in allowed_sources:
        raise HTTPException(status_code=422, detail="Jenis sumber tidak termasuk daftar sumber tepercaya yang diizinkan.")
    if not re.match(r"^https?://[^\s]+$", request.source_url.strip(), flags=re.IGNORECASE):
        raise HTTPException(status_code=422, detail="URL sumber harus berupa tautan HTTP/HTTPS yang valid.")
    if normalize_part_number(request.canonical_part_number) == normalize_part_number(request.alternate_part_number):
        raise HTTPException(status_code=422, detail="Nomor part kanonis dan alternatif tidak boleh identik setelah normalisasi.")
    actor_id = str((identity.get("user") or {}).get("id") or "")
    payload = request.model_dump(mode="json", exclude_none=True)
    payload.update({
        "canonical_part_number": request.canonical_part_number.strip(),
        "alternate_part_number": request.alternate_part_number.strip(),
        "source_url": request.source_url.strip(),
        "source_checked_at": datetime.now(timezone.utc).isoformat(),
        "review_status": "pending_review",
        "reviewed_by": None,
        "reviewed_at": None,
        "created_by": actor_id,
    })
    rows = await supabase_write("POST", "part_number_cross_references", identity["_access_token"], payload)
    if not rows:
        raise HTTPException(status_code=503, detail="Pemetaan nomor part tidak dapat disimpan.")
    return {"item": rows[0], "notice": "Pemetaan tersimpan sebagai pending_review; belum dipakai pada pencarian publik."}


@app.patch("/v1/admin/part-number-mappings/{mapping_id}/review", tags=["admin-search"])
async def review_part_number_mapping(
    mapping_id: UUID,
    request: PartNumberMappingReview = Body(...),
    identity: dict[str, Any] = Depends(require_roles("admin", "catalog_editor", "moderator")),
) -> dict[str, Any]:
    if request.action not in {"approve", "reject"}:
        raise HTTPException(status_code=422, detail="Aksi review harus approve atau reject.")
    actor_id = str((identity.get("user") or {}).get("id") or "")
    payload = {
        "review_status": "approved" if request.action == "approve" else "rejected",
        "reviewed_by": actor_id,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "review_note": request.review_note.strip() if request.review_note else None,
    }
    rows = await supabase_write(
        "PATCH", "part_number_cross_references", identity["_access_token"], payload,
        filters={"id": f"eq.{mapping_id}", "review_status": "eq.pending_review"},
    )
    if not rows:
        raise HTTPException(status_code=409, detail="Pemetaan tidak ditemukan atau sudah direview.")
    return {"item": rows[0], "notice": "Status cross-reference diperbarui. Status fitment produk tidak diubah."}



@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "otoclinic-api", "environment": settings.environment}


@app.get("/ready", tags=["system"])
async def readiness() -> dict[str, str]:
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(
            status_code=503,
            detail="configuration-required: set SUPABASE_URL and SUPABASE_ANON_KEY",
        )
    return {"status": "configured", "service": "otoclinic-api"}


@app.get("/v1/auth/me", tags=["auth"])
async def get_current_user(
    identity: dict[str, Any] = Depends(get_current_identity),
) -> dict[str, Any]:
    """Return the verified user's identity/profile for any active user category."""
    return {key: value for key, value in identity.items() if not key.startswith("_")}


async def public_product_media(product_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Return only approved media and short-lived signed URLs from the private product-media bucket."""
    if not product_ids:
        return {}
    media_rows = await supabase_get(
        "product_media",
        {
            "select": "id,product_id,storage_path,source_url,alt_text,media_kind,is_primary",
            "product_id": f"in.({','.join(product_ids)})",
            "review_status": "eq.approved",
            "rights_status": "in.(permission_granted,licensed,public_domain,user_owned)",
            "order": "is_primary.desc,created_at.asc",
            "limit": str(min(500, len(product_ids) * 10)),
        },
    )
    supabase_url, anon_key = require_supabase_configuration()
    grouped: dict[str, list[dict[str, Any]]] = {}
    async with httpx.AsyncClient(timeout=8.0) as client:
        for media in media_rows:
            path = media.get("storage_path")
            image_url = media.get("source_url") if not path else None
            if path:
                response = await client.post(
                    f"{supabase_url}/storage/v1/object/sign/product-media/{quote(path, safe='/')}",
                    headers={"apikey": anon_key, "Authorization": f"Bearer {anon_key}", "Content-Type": "application/json"},
                    json={"expiresIn": 3600},
                )
                if response.status_code != 200:
                    continue
                signed = response.json().get("signedURL")
                if not signed:
                    continue
                image_url = signed if signed.startswith("http") else f"{supabase_url}/storage/v1{signed if signed.startswith('/') else '/' + signed}"
            if not image_url:
                continue
            product_id = str(media["product_id"])
            grouped.setdefault(product_id, []).append({
                "id": media["id"],
                "url": image_url,
                "alt_text": media["alt_text"],
                "media_kind": media["media_kind"],
                "is_primary": media["is_primary"],
            })
    return grouped


class SourcingRequestCreate(BaseModel):
    part_name: str = Field(min_length=2, max_length=180)
    part_number: str | None = Field(default=None, max_length=120)
    vehicle_make: str | None = Field(default=None, max_length=100)
    vehicle_model: str | None = Field(default=None, max_length=120)
    vehicle_year: int | None = Field(default=None, ge=1950, le=2100)
    quantity: int = Field(default=1, ge=1, le=100)
    details: str | None = Field(default=None, max_length=2000)
    contact_phone: str | None = Field(default=None, max_length=40)
    model_config = {"extra": "forbid"}


@app.get("/v1/sourcing/requests", tags=["sourcing"])
async def list_own_sourcing_requests(identity: dict[str, Any] = Depends(require_roles("customer"))) -> dict[str, Any]:
    user_id = (identity.get("user") or {}).get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Verified customer identity required.")
    rows = await supabase_get(
        "sourcing_requests",
        {"select": "id,part_name,part_number,vehicle_make,vehicle_model,vehicle_year,quantity,details,status,created_at", "customer_user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": "100"},
        access_token=identity["_access_token"],
    )
    return {"items": rows, "count": len(rows)}


@app.post("/v1/sourcing/requests", tags=["sourcing"], status_code=201)
async def create_sourcing_request(
    request: SourcingRequestCreate = Body(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    identity: dict[str, Any] = Depends(require_roles("customer")),
) -> dict[str, Any]:
    user_id = (identity.get("user") or {}).get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Verified customer identity required.")
    if not idempotency_key or len(idempotency_key.strip()) < 8 or len(idempotency_key) > 128:
        raise HTTPException(status_code=422, detail="A valid Idempotency-Key header is required.")
    payload = request.model_dump(mode="json", exclude_none=True)
    payload.update({"customer_user_id": user_id, "idempotency_key": idempotency_key.strip(), "status": "requested"})
    try:
        rows = await supabase_write("POST", "sourcing_requests", identity["_access_token"], payload)
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        existing = await supabase_get(
            "sourcing_requests",
            {"select": "id,part_name,part_number,vehicle_make,vehicle_model,vehicle_year,quantity,details,status,created_at", "customer_user_id": f"eq.{user_id}", "idempotency_key": f"eq.{idempotency_key.strip()}", "limit": "1"},
            access_token=identity["_access_token"],
        )
        if existing:
            return {"request": existing[0], "replayed": True}
        raise
    if not rows:
        raise HTTPException(status_code=503, detail="Sourcing request was not returned after save.")
    row = rows[0]
    return {"request": {key: row.get(key) for key in ("id","part_name","part_number","vehicle_make","vehicle_model","vehicle_year","quantity","details","status","created_at")}, "replayed": False}


@app.get("/v1/catalog/products", tags=["catalog"])
async def list_public_products(
    q: str | None = Query(default=None, min_length=1, max_length=100),
    category: str | None = Query(default=None, min_length=1, max_length=80),
    category_id: UUID | None = None,
    condition: str | None = Query(default=None, min_length=1, max_length=40),
    part_number: str | None = Query(default=None, min_length=1, max_length=100),
    variant_id: UUID | None = None,
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
) -> dict[str, Any]:
    """Public catalog search with descendant-aware categories and published-only stock summaries."""
    params = {
        "select": "id,sku,slug,name,description,brand,part_number,category,condition,condition_grade,package_quantity,warranty_days,currency,retail_price,fitment_summary,published_at",
        "status": "eq.published",
        "order": "name.asc",
        "limit": str(limit),
        "offset": str(offset),
    }
    category_clauses: list[str] = []
    if category_id:
        category_rows = await supabase_rpc("oto_public_product_categories", {})
        category_by_id = {str(item["id"]): item for item in category_rows}
        if str(category_id) not in category_by_id:
            raise HTTPException(status_code=404, detail="Kategori tidak ditemukan atau tidak aktif.")
        descendant_ids = {str(category_id)}
        changed = True
        while changed:
            changed = False
            for item in category_rows:
                if item.get("parent_id") and str(item["parent_id"]) in descendant_ids and str(item["id"]) not in descendant_ids:
                    descendant_ids.add(str(item["id"]))
                    changed = True
        for item in category_rows:
            if str(item["id"]) in descendant_ids:
                term = safe_search_term(str(item["name"]))
                if term:
                    category_clauses.append(f"category.ilike.*{term}*")
    elif category:
        term = safe_search_term(category)
        if term:
            category_clauses.append(f"category.ilike.*{term}*")
    if condition:
        normalized = condition.strip().lower()
        if normalized not in PRODUCT_CONDITIONS:
            raise HTTPException(status_code=422, detail="Unsupported product condition.")
        params["condition"] = f"eq.{normalized}"
    if part_number:
        term = safe_search_term(part_number)
        if term:
            params["part_number"] = f"ilike.*{term}*"
    query_clauses: list[str] = []
    if q:
        term = safe_search_term(q)
        if term:
            query_clauses.extend([f"name.ilike.*{term}*", f"sku.ilike.*{term}*", f"brand.ilike.*{term}*", f"part_number.ilike.*{term}*"])
    if category_clauses and query_clauses:
        params["and"] = f"(or({','.join(category_clauses)}),or({','.join(query_clauses)}))"
    elif category_clauses:
        params["or"] = f"({','.join(category_clauses)})"
    elif query_clauses:
        params["or"] = f"({','.join(query_clauses)})"
    if variant_id:
        fitment_rows = await supabase_get(
            "product_fitments",
            {"select": "product_id", "variant_id": f"eq.{variant_id}", "status": "eq.verified", "limit": "500"},
        )
        product_ids = list(dict.fromkeys(str(row["product_id"]) for row in fitment_rows if row.get("product_id")))
        if not product_ids:
            return {"items": [], "count": 0, "limit": limit, "offset": offset}
        params["id"] = f"in.({','.join(product_ids)})"
    rows = await supabase_get("products", params)
    ids = [str(row["id"]) for row in rows if row.get("id")]
    media = await public_product_media(ids)
    stock: dict[str, dict[str, Any]] = {}
    if ids:
        try:
            stock_rows = await supabase_rpc("oto_public_stock_status", {"p_product_ids": ids})
            stock = {str(item["product_id"]): {"stock_status": item["stock_status"], "stock_checked_at": item.get("checked_at")} for item in stock_rows if item.get("product_id")}
        except HTTPException:
            stock = {}
    for row in rows:
        row["images"] = media.get(str(row["id"]), [])
        row["image_url"] = next((item["url"] for item in row["images"] if item["is_primary"]), row["images"][0]["url"] if row["images"] else None)
        row["stock_status"] = stock.get(str(row["id"]), {}).get("stock_status", "unverified")
        row["stock_checked_at"] = stock.get(str(row["id"]), {}).get("stock_checked_at")
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset}


@app.get("/v1/vehicles/makes", tags=["vehicles"])
async def list_vehicle_makes() -> dict[str, Any]:
    rows = await supabase_get(
        "vehicle_makes",
        {"select": "id,name,slug", "is_active": "eq.true", "order": "name.asc", "limit": "200"},
    )
    return {"items": rows, "count": len(rows)}


@app.get("/v1/vehicles/models", tags=["vehicles"])
async def list_vehicle_models(
    make_id: UUID | None = None,
    vehicle_type: str | None = Query(default=None, min_length=1, max_length=30),
) -> dict[str, Any]:
    params = {"select": "id,make_id,name,slug,vehicle_type", "is_active": "eq.true", "order": "name.asc", "limit": "500"}
    if make_id:
        params["make_id"] = f"eq.{make_id}"
    if vehicle_type:
        normalized = vehicle_type.strip().lower()
        if normalized not in VEHICLE_TYPES:
            raise HTTPException(status_code=422, detail="Unsupported vehicle type.")
        params["vehicle_type"] = f"eq.{normalized}"
    rows = await supabase_get("vehicle_models", params)
    return {"items": rows, "count": len(rows)}


@app.get("/v1/vehicles/variants", tags=["vehicles"])
async def list_vehicle_variants(model_id: UUID = Query(...)) -> dict[str, Any]:
    rows = await supabase_get(
        "vehicle_variants",
        {
            "select": "id,model_id,name,year_start,year_end,engine_code,transmission,notes",
            "model_id": f"eq.{model_id}",
            "is_active": "eq.true",
            "order": "year_start.asc.nullsfirst,name.asc",
            "limit": "500",
        },
    )
    return {"items": rows, "count": len(rows)}


@app.get("/v1/catalog/products/{product_id}", tags=["catalog"])
async def get_public_product(product_id: UUID) -> dict[str, Any]:
    """Return one published product only; public reads continue to obey Supabase RLS."""
    rows = await supabase_get(
        "products",
        {
            "select": "id,sku,slug,name,description,brand,part_number,category,condition,condition_grade,package_quantity,warranty_days,currency,retail_price,fitment_summary,published_at",
            "id": f"eq.{product_id}",
            "status": "eq.published",
            "limit": "1",
        },
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan atau belum dipublikasikan.")
    product_id = str(rows[0]["id"])
    media = await public_product_media([product_id])
    rows[0]["images"] = media.get(product_id, [])
    rows[0]["image_url"] = next((item["url"] for item in rows[0]["images"] if item["is_primary"]), rows[0]["images"][0]["url"] if rows[0]["images"] else None)
    try:
        stock_rows = await supabase_rpc("oto_public_stock_status", {"p_product_ids": [product_id]})
        stock_row = stock_rows[0] if stock_rows else None
    except HTTPException:
        stock_row = None
    rows[0]["stock_status"] = stock_row.get("stock_status", "unverified") if stock_row else "unverified"
    rows[0]["stock_checked_at"] = stock_row.get("checked_at") if stock_row else None
    return {"product": rows[0]}


@app.get("/v1/catalog/products/{product_id}/fitments", tags=["fitment"])
async def list_verified_product_fitments(product_id: UUID) -> dict[str, Any]:
    """Only verified fitments attached to published products are visible under the existing RLS policy."""
    rows = await supabase_get(
        "product_fitments",
        {
            "select": "id,product_id,variant_id,status,evidence_url,evidence_note,verified_at,vehicle_variants(id,model_id,name,year_start,year_end,engine_code,transmission,vehicle_models(id,make_id,name,slug,vehicle_type,vehicle_makes(id,name,slug)))",
            "product_id": f"eq.{product_id}",
            "status": "eq.verified",
            "order": "verified_at.desc",
            "limit": "100",
        },
    )
    return {"items": rows, "count": len(rows)}

class CatalogMutation(BaseModel):
    action: str = Field(min_length=1, max_length=40)
    product_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SupplierOnboarding(BaseModel):
    legal_name: str = Field(min_length=2, max_length=200)
    display_name: str = Field(min_length=2, max_length=160)
    supplier_type: str = Field(default="supplier", min_length=1, max_length=40)
    contact_name: str | None = Field(default=None, max_length=160)
    contact_email: str | None = Field(default=None, max_length=254)
    contact_phone: str | None = Field(default=None, max_length=40)
    business_registration_number: str | None = Field(default=None, max_length=100)
    website_url: str | None = Field(default=None, max_length=500)
    address: dict[str, Any] = Field(default_factory=dict)


class SupplierDocumentRegistration(BaseModel):
    document_type: str = Field(min_length=1, max_length=40)
    storage_path: str = Field(min_length=1, max_length=1024)
    original_filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=100)
    file_size_bytes: int = Field(ge=1, le=10485760)
    sha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    expires_at: datetime | None = None


class SupplierOfferSubmission(BaseModel):
    product_id: UUID | None = None
    supplier_sku: str | None = Field(default=None, max_length=160)
    source_url: str | None = Field(default=None, max_length=2048)
    source_evidence: dict[str, Any] = Field(default_factory=dict)
    condition: str = Field(min_length=1, max_length=40)
    unit_cost: Decimal = Field(ge=0)
    asking_price: Decimal | None = Field(default=None, ge=0)
    stock_quantity: int = Field(ge=0)
    quote_expires_at: datetime
    lead_time_days: int = Field(default=0, ge=0, le=365)
    minimum_order_quantity: int = Field(default=1, ge=1, le=1000000)
    warranty_days: int = Field(default=0, ge=0, le=3650)


class SupplierAdminMutation(BaseModel):
    action: str = Field(min_length=1, max_length=40)
    supplier_id: UUID | None = None
    offer_id: UUID | None = None
    document_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


async def supabase_catalog_rpc(
    action: str,
    product_id: UUID | None,
    payload: dict[str, Any],
    request_id: str,
    access_token: str,
) -> Any:
    supabase_url, anon_key = require_supabase_configuration()
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = {
        "p_action": action,
        "p_product_id": str(product_id) if product_id else None,
        "p_payload": payload,
        "p_request_id": request_id,
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(
                f"{supabase_url}/rest/v1/rpc/oto_catalog_mutate",
                headers=headers,
                json=body,
            )
        if response.status_code in (401, 403):
            raise HTTPException(status_code=403, detail="Catalog operation is not permitted.")
        if response.status_code == 429 or response.status_code >= 500:
            raise HTTPException(status_code=503, detail="Catalog service is temporarily unavailable.")
        if response.status_code not in (200, 201):
            # Map known database validation outcomes to safe client errors.
            try:
                db_error = response.json()
                message = str(db_error.get("message", ""))
                code = str(db_error.get("code", ""))
            except (ValueError, AttributeError):
                message, code = "", ""
            # Translate known RPC outcomes into actionable, non-sensitive messages.
            # Never forward raw Postgres/PostgREST messages to the browser.
            safe_validation_messages = {
                "request_id_required_or_length_invalid": "Kunci idempotensi tidak valid. Muat ulang lalu coba lagi.",
                "request_id_reused_for_different_operation": "Permintaan bertabrakan dengan aksi sebelumnya. Muat ulang katalog lalu ulangi aksi.",
                "unsupported_catalog_action": "Aksi katalog tidak dikenali. Muat ulang halaman Admin.",
                "product_id_required": "Pilih produk yang akan diproses.",
                "product_and_variant_required": "Pilih produk dan varian kendaraan serta isi bukti kecocokan.",
                "product_and_fitment_required": "Pilih produk dan bukti fitment yang akan ditinjau.",
                "invalid_product_transition": "Status produk sudah berubah atau tidak mengizinkan aksi ini. Muat ulang katalog.",
                "only_draft_or_rejected_products_are_editable": "Hanya produk draft atau ditolak yang dapat diedit.",
                "publication_requirements_missing": "Produk belum memenuhi persyaratan publikasi. Periksa SKU, slug, nama, kategori, kondisi, harga, bukti sumber, dan berat kirim.",
                "published_product_shipping_weight_required": "Berat kirim wajib diisi sebelum produk dipublikasikan.",
                "rejection_reason_required": "Isi alasan penolakan sebelum melanjutkan.",
                "fitment_evidence_required": "Bukti kecocokan kendaraan wajib diisi sebelum verifikasi.",
                "fitment_review_status_invalid": "Keputusan review fitment tidak valid.",
                "product_already_archived": "Produk sudah diarsipkan.",
            }
            if code == "P0002" or "not_found" in message:
                raise HTTPException(status_code=404, detail="Data katalog tidak ditemukan atau sudah tidak tersedia.")
            if code == "42501":
                raise HTTPException(status_code=403, detail="Aksi tidak diizinkan untuk role akun ini atau sesi tidak lagi aktif.")
            # This production constraint is intentional: products with an unknown
            # condition must remain drafts until a staff member verifies the condition.
            if "products_condition_known_before_review" in message:
                raise HTTPException(status_code=422, detail="Kondisi produk masih 'Belum diverifikasi'. Edit produk dan pilih kondisi yang benar-benar terkonfirmasi sebelum mengajukan review.")
            if message in safe_validation_messages:
                raise HTTPException(status_code=422, detail=safe_validation_messages[message])
            if code == "23505":
                raise HTTPException(status_code=409, detail="Data katalog bertabrakan dengan perubahan lain. Muat ulang lalu coba lagi.")
            if code in ("22023", "22P02", "23514", "23502", "23503"):
                # Constraint names, SQL details and row values are intentionally not exposed.
                raise HTTPException(status_code=422, detail="Data katalog belum memenuhi aturan validasi. Periksa kolom wajib dan status produk, lalu coba lagi.")
            raise HTTPException(status_code=503, detail="Operasi katalog belum dapat diselesaikan. Coba lagi nanti.")
        return response.json()
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=503, detail="Catalog service timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Could not reach catalog service.") from exc


async def verify_product_media_upload(storage_path: str, content_type: str, declared_size: int, expected_sha256: str, access_token: str) -> str:
    """Read the caller-uploaded private product image back from Storage and verify its bytes before registering metadata."""
    supabase_url, anon_key = require_supabase_configuration()
    encoded_path = quote(storage_path, safe="/")
    headers = {"apikey": anon_key, "Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{supabase_url}/storage/v1/object/product-media/{encoded_path}", headers=headers)
        if response.status_code in (401, 403):
            raise HTTPException(status_code=403, detail="Product media storage access is not permitted.")
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Uploaded product image was not found.")
        if response.status_code == 429 or response.status_code >= 500:
            raise HTTPException(status_code=503, detail="Product media storage is temporarily unavailable.")
        if response.status_code != 200:
            raise HTTPException(status_code=422, detail="Uploaded product image could not be verified.")
        actual_size = len(response.content)
        actual_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if actual_size < 1 or actual_size > 15728640 or actual_size != declared_size:
            raise HTTPException(status_code=422, detail="Uploaded image size does not match its declaration.")
        if actual_type != content_type.lower():
            raise HTTPException(status_code=422, detail="Uploaded image content type does not match its declaration.")
        actual_sha256 = hashlib.sha256(response.content).hexdigest()
        if actual_sha256.lower() != expected_sha256.lower():
            raise HTTPException(status_code=422, detail="Uploaded image checksum does not match its bytes.")
        return actual_sha256
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=503, detail="Product image verification timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Could not verify product image storage object.") from exc


async def verify_supplier_document_upload(
    storage_path: str,
    content_type: str,
    declared_size: int,
    expected_sha256: str | None,
    access_token: str,
) -> str:
    """Download the private object through the caller's RLS token and verify its bytes."""
    supabase_url, anon_key = require_supabase_configuration()
    encoded_path = quote(storage_path, safe="/")
    headers = {"apikey": anon_key, "Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"{supabase_url}/storage/v1/object/supplier-verification-documents/{encoded_path}",
                headers=headers,
            )
        if response.status_code in (401, 403):
            raise HTTPException(status_code=403, detail="Supplier document storage access is not permitted.")
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Uploaded supplier document was not found.")
        if response.status_code == 429 or response.status_code >= 500:
            raise HTTPException(status_code=503, detail="Supplier document storage is temporarily unavailable.")
        if response.status_code != 200:
            raise HTTPException(status_code=422, detail="Supplier document could not be verified.")
        actual_size = len(response.content)
        actual_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if actual_size < 1 or actual_size > 10485760 or actual_size != declared_size:
            raise HTTPException(status_code=422, detail="Uploaded file size does not match its declaration.")
        if actual_type != content_type.lower():
            raise HTTPException(status_code=422, detail="Uploaded file content type does not match its declaration.")
        actual_sha256 = hashlib.sha256(response.content).hexdigest()
        if expected_sha256 and actual_sha256.lower() != expected_sha256.lower():
            raise HTTPException(status_code=422, detail="Uploaded file checksum does not match its bytes.")
        return actual_sha256
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=503, detail="Supplier document verification timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Could not verify supplier document storage object.") from exc


async def supabase_supplier_rpc(
    function_name: str,
    body: dict[str, Any],
    access_token: str,
) -> Any:
    """Call only allowlisted supplier RPCs with the verified caller JWT."""
    allowed_functions = {
        "oto_supplier_onboard",
        "oto_supplier_document_register",
        "oto_supplier_offer_submit",
        "oto_supplier_admin_mutate",
        "oto_supplier_offer_match_candidates",
    }
    if function_name not in allowed_functions:
        raise HTTPException(status_code=422, detail="Unsupported supplier operation.")
    supabase_url, anon_key = require_supabase_configuration()
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(
                f"{supabase_url}/rest/v1/rpc/{function_name}",
                headers=headers,
                json=body,
            )
        if response.status_code in (401, 403):
            raise HTTPException(status_code=403, detail="Supplier operation is not permitted.")
        if response.status_code == 429 or response.status_code >= 500:
            raise HTTPException(status_code=503, detail="Supplier service is temporarily unavailable.")
        if response.status_code not in (200, 201):
            try:
                db_error = response.json()
                message = str(db_error.get("message", ""))
                code = str(db_error.get("code", ""))
            except (ValueError, AttributeError):
                message, code = "", ""
            if code == "P0002" or "not_found" in message:
                raise HTTPException(status_code=404, detail="Supplier record was not found.")
            if code == "42501" or "ownership_required" in message or "active_supplier_required" in message:
                raise HTTPException(status_code=403, detail="Supplier operation is not permitted for this account.")
            if code == "23505" or "already_exists" in message or "duplicate key" in message:
                raise HTTPException(status_code=409, detail="A matching supplier record already exists.")
            if code in ("22023", "22P02", "23514", "23502"):
                raise HTTPException(status_code=422, detail="Supplier operation failed validation.")
            raise HTTPException(status_code=503, detail="Supplier operation could not be completed.")
        return response.json()
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=503, detail="Supplier operation timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Could not reach supplier service.") from exc


async def get_owned_supplier(identity: dict[str, Any]) -> dict[str, Any]:
    user = identity.get("user")
    user_id = user.get("id") if isinstance(user, dict) else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Authenticated user required.")
    rows = await supabase_get(
        "suppliers",
        {
            "select": "id,owner_user_id,legal_name,display_name,supplier_type,status,contact_name,contact_email,contact_phone,address,business_registration_number,website_url,reviewed_at,review_note,created_at,updated_at",
            "owner_user_id": f"eq.{user_id}",
            "limit": "1",
        },
        access_token=identity["_access_token"],
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Supplier onboarding has not been submitted.")
    return rows[0]


@app.get("/v1/admin/catalog/fitments", tags=["fitment"])
async def list_admin_fitments(
    product_id: UUID | None = None,
    identity: dict[str, Any] = Depends(require_roles("admin", "catalog_editor", "moderator")),
) -> dict[str, Any]:
    params = {
        "select": "id,product_id,variant_id,status,evidence_url,evidence_note,verified_by,verified_at,created_at,vehicle_variants(id,model_id,name,year_start,year_end,engine_code,transmission,vehicle_models(id,make_id,name,slug,vehicle_type,vehicle_makes(id,name,slug)))",
        "order": "created_at.desc",
        "limit": "200",
    }
    if product_id:
        params["product_id"] = f"eq.{product_id}"
    rows = await supabase_get("product_fitments", params, access_token=identity["_access_token"])
    return {"items": rows, "count": len(rows)}


@app.post("/v1/admin/catalog/mutations", tags=["catalog"])
async def mutate_catalog(
    mutation: CatalogMutation = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_roles("admin", "catalog_editor", "moderator")),
) -> dict[str, Any]:
    allowed = {
        "create_product", "update_product", "submit_review", "approve_product",
        "publish_product", "reject_product", "archive_product", "save_fitment", "review_fitment",
    }
    if mutation.action not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported catalog action.")
    if len(str(mutation.payload)) > 20000:
        raise HTTPException(status_code=413, detail="Catalog payload is too large.")
    result = await supabase_catalog_rpc(
        mutation.action, mutation.product_id, mutation.payload,
        idempotency_key, identity["_access_token"],
    )
    return {"result": result}


class ProductMediaRegister(BaseModel):
    storage_path: str = Field(min_length=3, max_length=500)
    alt_text: str = Field(min_length=3, max_length=300)
    content_type: str = Field(min_length=3, max_length=100)
    byte_size: int = Field(ge=1, le=15728640)
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    rights_status: str = Field(pattern=r"^(unknown|permission_granted|licensed|public_domain|user_owned|not_permitted)$")
    rights_evidence_note: str | None = Field(default=None, max_length=2000)
    model_config = {"extra": "forbid"}


@app.post("/v1/admin/catalog/products/{product_id}/media", tags=["catalog"], status_code=201)
async def register_admin_product_media(product_id: UUID, request: ProductMediaRegister = Body(...), identity: dict[str, Any] = Depends(require_roles("admin", "catalog_editor", "moderator"))) -> dict[str, Any]:
    user = identity.get("user") or {}
    actor_id = user.get("id")
    if not actor_id: raise HTTPException(status_code=401, detail="Authenticated user required.")
    if request.content_type.lower() not in {"image/jpeg", "image/png", "image/webp", "image/avif"}:
        raise HTTPException(status_code=422, detail="Only JPEG, PNG, WebP, or AVIF product images are accepted.")
    path_parts = request.storage_path.split("/")
    if not request.storage_path.startswith(f"{product_id}/") or any(part in {"", ".", ".."} for part in path_parts):
        raise HTTPException(status_code=422, detail="Product image path must stay inside its product folder.")
    product_rows = await supabase_get("products", {"select": "id,status", "id": f"eq.{product_id}", "limit": "1"}, access_token=identity["_access_token"])
    if not product_rows: raise HTTPException(status_code=404, detail="Product was not found.")
    actual_sha256 = await verify_product_media_upload(request.storage_path, request.content_type, request.byte_size, request.sha256, identity["_access_token"])
    payload = {
        "product_id": str(product_id), "storage_path": request.storage_path, "source_name": "staff_file_upload",
        "media_kind": "product_photo", "alt_text": request.alt_text.strip(), "content_type": request.content_type.lower(),
        "byte_size": request.byte_size, "sha256": actual_sha256, "rights_status": request.rights_status,
        "rights_evidence_note": request.rights_evidence_note.strip() if request.rights_evidence_note and request.rights_evidence_note.strip() else None,
        "review_status": "pending", "is_primary": False, "captured_at": datetime.now(timezone.utc).isoformat(), "created_by": actor_id,
    }
    rows = await supabase_write("POST", "product_media", identity["_access_token"], payload)
    if not rows: raise HTTPException(status_code=503, detail="Product image metadata was not returned after save.")
    return {"media": rows[0], "review_status": "pending"}


class MarketplaceProductMediaImport(BaseModel):
    image_url: str = Field(min_length=12, max_length=2048)
    source_listing_url: str = Field(min_length=12, max_length=2048)
    alt_text: str = Field(min_length=3, max_length=300)
    model_config = {"extra": "forbid"}


def validate_marketplace_image_url(value: str, *, listing: bool = False) -> str:
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Marketplace source must be a valid HTTPS URL.") from exc
    if parsed.scheme != "https" or not host or parsed.username or parsed.password or port not in (None, 443):
        raise HTTPException(status_code=422, detail="Marketplace source must be a valid HTTPS URL.")
    if listing:
        allowed = host in {"shopee.co.id", "www.shopee.co.id", "tokopedia.com", "www.tokopedia.com"}
    else:
        allowed = host.endswith(".susercontent.com") or host.endswith(".tokopedia-static.net") or host in {"images.tokopedia.net", "images.tokopedia.com"}
    if not allowed:
        raise HTTPException(status_code=422, detail="Image or listing URL is outside the supported marketplace domains.")
    return value


def extract_marketplace_image_url(page_html: str) -> str | None:
    """Extract only an explicitly declared Open Graph/Twitter image from marketplace HTML."""
    for tag in re.findall(r"<meta\b[^>]*>", page_html, flags=re.IGNORECASE):
        name_match = re.search(r"""(?:property|name)\s*=\s*["']([^"']+)["']""", tag, flags=re.IGNORECASE)
        content_match = re.search(r"""\bcontent\s*=\s*["']([^"']+)["']""", tag, flags=re.IGNORECASE)
        if not name_match or not content_match or name_match.group(1).strip().lower() not in {"og:image", "twitter:image"}:
            continue
        candidate = html_unescape(content_match.group(1).strip())
        try:
            return validate_marketplace_image_url(candidate)
        except HTTPException:
            continue
    return None


async def refresh_marketplace_image_url(listing_url: str) -> str | None:
    """Refresh expiring marketplace CDN image URLs from the public listing metadata."""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            response = await client.get(
                listing_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; OtoClinicCatalogBot/1.0)", "Accept-Language": "id-ID,id;q=0.9,en;q=0.8"},
            )
        if response.status_code != 200:
            return None
        return extract_marketplace_image_url(response.text)
    except (httpx.HTTPError, HTTPException):
        return None


def detect_product_image_type(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if len(content) >= 12 and content[4:8] == b"ftyp" and content[8:12] in {b"avif", b"avis"}:
        return "image/avif"
    return None


@app.post("/v1/admin/catalog/products/{product_id}/media/import-marketplace", tags=["catalog"], status_code=201)
async def import_marketplace_product_media(
    product_id: UUID,
    request: MarketplaceProductMediaImport = Body(...),
    identity: dict[str, Any] = Depends(require_roles("admin", "catalog_editor", "moderator")),
) -> dict[str, Any]:
    """Copy a marketplace image into private Storage for draft review only; never grants image rights."""
    user = identity.get("user") or {}
    actor_id = user.get("id")
    if not actor_id:
        raise HTTPException(status_code=401, detail="Authenticated user required.")
    image_url = validate_marketplace_image_url(request.image_url)
    listing_url = validate_marketplace_image_url(request.source_listing_url, listing=True)
    refreshed_image_url = await refresh_marketplace_image_url(listing_url)
    if refreshed_image_url:
        image_url = refreshed_image_url
    product_rows = await supabase_get("products", {"select": "id,status", "id": f"eq.{product_id}", "limit": "1"}, access_token=identity["_access_token"])
    if not product_rows:
        raise HTTPException(status_code=404, detail="Product was not found.")
    if str(product_rows[0].get("status", "")).lower() not in {"draft", "in_review", "review"}:
        raise HTTPException(status_code=409, detail="Marketplace reference images may only be attached to draft products awaiting review.")

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0), follow_redirects=False) as client:
            async with client.stream("GET", image_url, headers={"Accept": "image/avif,image/webp,image/png,image/jpeg"}) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    raise HTTPException(status_code=422, detail="Image CDN redirect is not accepted; provide the final image URL.")
                if response.status_code == 404:
                    raise HTTPException(status_code=404, detail="Marketplace image was not found.")
                if response.status_code != 200:
                    raise HTTPException(status_code=502, detail="Marketplace image source is unavailable.")
                declared_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if declared_type not in {"image/jpeg", "image/png", "image/webp", "image/avif"}:
                    raise HTTPException(status_code=422, detail="Marketplace URL did not return a supported image type.")
                declared_length = response.headers.get("content-length")
                if declared_length and declared_length.isdigit() and int(declared_length) > 15 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="Marketplace image exceeds the 15 MB limit.")
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > 15 * 1024 * 1024:
                        raise HTTPException(status_code=413, detail="Marketplace image exceeds the 15 MB limit.")
                content = bytes(chunks)
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Marketplace image download timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Marketplace image could not be downloaded.") from exc

    detected_type = detect_product_image_type(content)
    if not content or detected_type is None or detected_type != declared_type:
        raise HTTPException(status_code=422, detail="Downloaded bytes do not match a supported image format.")
    supabase_url, anon_key = require_supabase_configuration()
    sha256 = hashlib.sha256(content).hexdigest()
    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/avif": "avif"}[detected_type]
    storage_path = f"{product_id}/{uuid4()}.{extension}"
    headers = {"apikey": anon_key, "Authorization": f"Bearer {identity['_access_token']}", "Content-Type": detected_type, "x-upsert": "false"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            upload = await client.post(f"{supabase_url}/storage/v1/object/product-media/{quote(storage_path, safe='/')}", headers=headers, content=content)
        if upload.status_code in (401, 403):
            raise HTTPException(status_code=403, detail="Storage policy does not permit this staff upload.")
        if upload.status_code == 413:
            raise HTTPException(status_code=413, detail="Storage rejected the image size.")
        if upload.status_code not in (200, 201):
            raise HTTPException(status_code=503, detail="Private product image could not be stored.")
        verified_sha256 = await verify_product_media_upload(storage_path, detected_type, len(content), sha256, identity["_access_token"])
        payload = {
            "product_id": str(product_id), "storage_path": storage_path, "source_url": image_url,
            "source_listing_url": listing_url, "source_name": "marketplace_image_import",
            "media_kind": "product_photo", "alt_text": request.alt_text.strip(), "content_type": detected_type,
            "byte_size": len(content), "sha256": verified_sha256, "rights_status": "unknown",
            "rights_evidence_note": "Marketplace image copied for internal draft review only. Usage rights are UNVERIFIED; do not approve or publish until written permission or a valid license is verified.",
            "review_status": "pending", "is_primary": False, "captured_at": datetime.now(timezone.utc).isoformat(), "created_by": actor_id,
        }
        rows = await supabase_write("POST", "product_media", identity["_access_token"], payload)
        if not rows:
            raise HTTPException(status_code=503, detail="Image metadata was not returned after save.")
        return {"media": rows[0], "review_status": "pending", "rights_status": "unknown", "customer_visible": False}
    except Exception:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                await client.delete(f"{supabase_url}/storage/v1/object/product-media/{quote(storage_path, safe='/')}", headers={"apikey": anon_key, "Authorization": f"Bearer {identity['_access_token']}"})
        except Exception:
            pass
        raise


class ProductCategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    slug: str = Field(min_length=2, max_length=110, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    code: str = Field(min_length=2, max_length=6, pattern=r"^[A-Z0-9]{2,6}$")
    parent_id: UUID | None = None
    description: str | None = Field(default=None, max_length=500)
    vehicle_scope: str = Field(default="all", pattern=r"^(all|motorcycle|car|commercial)$")
    sort_order: int = Field(default=100, ge=0, le=10000)
    model_config = {"extra": "forbid"}


class ProductCategoryUpdate(BaseModel):
    is_active: bool | None = None
    description: str | None = Field(default=None, max_length=500)
    sort_order: int | None = Field(default=None, ge=0, le=10000)
    model_config = {"extra": "forbid"}


@app.get("/v1/catalog/categories", tags=["catalog"])
async def list_public_product_categories() -> dict[str, Any]:
    rows = await supabase_rpc("oto_public_product_categories", {})
    return {"items": rows, "count": len(rows)}


@app.get("/v1/admin/catalog/categories", tags=["catalog"])
async def list_admin_product_categories(identity: dict[str, Any] = Depends(require_roles("admin", "catalog_editor", "moderator"))) -> dict[str, Any]:
    rows = await supabase_get("product_categories", {"select": "id,parent_id,name,slug,code,description,vehicle_scope,sort_order,is_active,created_at,updated_at", "order": "sort_order.asc,name.asc", "limit": "500"}, access_token=identity["_access_token"])
    return {"items": rows, "count": len(rows)}


@app.post("/v1/admin/catalog/categories", tags=["catalog"], status_code=201)
async def create_product_category(request: ProductCategoryCreate = Body(...), identity: dict[str, Any] = Depends(require_roles("admin", "catalog_editor"))) -> dict[str, Any]:
    actor_id = (identity.get("user") or {}).get("id")
    if not actor_id: raise HTTPException(status_code=401, detail="Authenticated user required.")
    payload = request.model_dump(mode="json", exclude_none=True)
    payload.update({"created_by": actor_id, "updated_by": actor_id})
    rows = await supabase_write("POST", "product_categories", identity["_access_token"], payload)
    if not rows: raise HTTPException(status_code=503, detail="Category was not returned after save.")
    return {"category": rows[0]}


@app.patch("/v1/admin/catalog/categories/{category_id}", tags=["catalog"])
async def update_product_category(category_id: UUID, request: ProductCategoryUpdate = Body(...), identity: dict[str, Any] = Depends(require_roles("admin", "catalog_editor"))) -> dict[str, Any]:
    if not request.model_fields_set: raise HTTPException(status_code=422, detail="Provide at least one category field to update.")
    actor_id = (identity.get("user") or {}).get("id")
    if not actor_id: raise HTTPException(status_code=401, detail="Authenticated user required.")
    payload = request.model_dump(mode="json", exclude_unset=True)
    payload["updated_by"] = actor_id
    rows = await supabase_write("PATCH", "product_categories", identity["_access_token"], payload, {"id": f"eq.{category_id}"})
    if not rows: raise HTTPException(status_code=404, detail="Category was not found or could not be updated.")
    return {"category": rows[0]}


@app.post("/v1/admin/catalog/sku/next", tags=["catalog"])
async def next_product_sku(category_id: UUID = Body(..., embed=True), identity: dict[str, Any] = Depends(require_roles("admin", "catalog_editor"))) -> dict[str, Any]:
    supabase_url, anon_key = require_supabase_configuration()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{supabase_url}/rest/v1/rpc/oto_next_product_sku", headers={"apikey": anon_key, "Authorization": f"Bearer {identity['_access_token']}", "Content-Type": "application/json", "Accept": "application/json"}, json={"p_category_id": str(category_id)})
        if response.status_code in (401, 403): raise HTTPException(status_code=403, detail="SKU generation is not permitted.")
        if response.status_code == 429 or response.status_code >= 500: raise HTTPException(status_code=503, detail="SKU allocator is temporarily unavailable.")
        if response.status_code != 200:
            try: code = str(response.json().get("code", ""))
            except (ValueError, AttributeError): code = ""
            if code == "22023": raise HTTPException(status_code=409, detail="SKU capacity for this category has been reached.")
            if code == "P0002": raise HTTPException(status_code=404, detail="Active category was not found.")
            raise HTTPException(status_code=422, detail="SKU could not be generated for this category.")
        return {"sku": response.json(), "capacity_per_category": 999999, "generation": "on-demand"}
    except HTTPException: raise
    except httpx.TimeoutException as exc: raise HTTPException(status_code=503, detail="SKU generation timed out.") from exc
    except httpx.HTTPError as exc: raise HTTPException(status_code=503, detail="Could not reach SKU allocator.") from exc


@app.get("/v1/admin/products", tags=["catalog"])
async def list_admin_products(
    identity: dict[str, Any] = Depends(require_roles("admin", "catalog_editor", "moderator")),
) -> dict[str, Any]:
    """Read real catalog rows for authorized staff; Supabase RLS remains authoritative."""
    rows = await supabase_get(
        "products",
        {
            "select": "id,sku,slug,name,description,brand,part_number,category,condition,condition_grade,package_quantity,warranty_days,status,currency,retail_price,source_rights_evidence,fitment_summary,published_at,created_at,updated_at",
            "order": "created_at.desc",
            "limit": "100",
        },
        access_token=identity["_access_token"],
    )
    return {"items": rows, "count": len(rows), "limit": 100}


@app.get("/v1/supplier/profile", tags=["supplier"])
async def get_supplier_profile(
    identity: dict[str, Any] = Depends(require_active_profile),
) -> dict[str, Any]:
    user = identity.get("user")
    user_id = user.get("id") if isinstance(user, dict) else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Authenticated user required.")
    rows = await supabase_get(
        "suppliers",
        {
            "select": "id,owner_user_id,legal_name,display_name,supplier_type,status,contact_name,contact_email,contact_phone,address,business_registration_number,website_url,reviewed_at,review_note,created_at,updated_at",
            "owner_user_id": f"eq.{user_id}",
            "limit": "1",
        },
        access_token=identity["_access_token"],
    )
    return {"supplier": rows[0] if rows else None}


@app.post("/v1/supplier/onboarding", tags=["supplier"])
async def submit_supplier_onboarding(
    request: SupplierOnboarding = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_active_profile),
) -> dict[str, Any]:
    if identity.get("role") not in {"customer", "supplier"}:
        raise HTTPException(status_code=403, detail="Only customer or supplier accounts can submit supplier onboarding.")
    payload = request.model_dump(mode="json", exclude_none=True)
    if payload.get("contact_email") and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", payload["contact_email"]):
        raise HTTPException(status_code=422, detail="Supplier contact email is invalid.")
    result = await supabase_supplier_rpc(
        "oto_supplier_onboard",
        {"p_payload": payload, "p_request_id": idempotency_key},
        identity["_access_token"],
    )
    return {"result": result}


@app.get("/v1/supplier/documents", tags=["supplier"])
async def list_supplier_documents(
    identity: dict[str, Any] = Depends(require_active_profile),
) -> dict[str, Any]:
    supplier = await get_owned_supplier(identity)
    rows = await supabase_get(
        "supplier_documents",
        {
            "select": "id,supplier_id,document_type,storage_path,original_filename,content_type,file_size_bytes,sha256,expires_at,status,review_note,reviewed_at,created_at,updated_at",
            "supplier_id": f"eq.{supplier['id']}",
            "order": "created_at.desc",
            "limit": "100",
        },
        access_token=identity["_access_token"],
    )
    return {"items": rows, "count": len(rows)}


@app.post("/v1/supplier/documents", tags=["supplier"])
async def register_supplier_document(
    request: SupplierDocumentRegistration = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_active_profile),
) -> dict[str, Any]:
    supplier = await get_owned_supplier(identity)
    if request.expires_at is not None and request.expires_at.utcoffset() is None:
        raise HTTPException(status_code=422, detail="Document expiry must include a timezone.")
    user = identity.get("user")
    user_id = user.get("id") if isinstance(user, dict) else None
    expected_prefix = f"{user_id}/{supplier['id']}/"
    if not user_id or not request.storage_path.startswith(expected_prefix) or any(part in {".", "..", ""} for part in request.storage_path.split("/")):
        raise HTTPException(status_code=422, detail="Supplier document path must stay inside the caller's supplier folder.")
    actual_sha256 = await verify_supplier_document_upload(
        request.storage_path, request.content_type, request.file_size_bytes, request.sha256, identity["_access_token"]
    )
    payload = request.model_dump(mode="json", exclude_none=True)
    payload["sha256"] = actual_sha256
    result = await supabase_supplier_rpc(
        "oto_supplier_document_register",
        {"p_supplier_id": supplier["id"], "p_payload": payload, "p_request_id": idempotency_key},
        identity["_access_token"],
    )
    return {"result": result}


@app.get("/v1/supplier/offers", tags=["supplier"])
async def list_supplier_offers(
    identity: dict[str, Any] = Depends(require_active_profile),
) -> dict[str, Any]:
    supplier = await get_owned_supplier(identity)
    rows = await supabase_get(
        "supplier_offers",
        {
            "select": "id,supplier_id,product_id,supplier_sku,source_url,source_evidence,condition,unit_cost,asking_price,currency,stock_quantity,stock_checked_at,quote_expires_at,status,lead_time_days,minimum_order_quantity,warranty_days,last_verified_by,source_verified_at,created_at,updated_at",
            "supplier_id": f"eq.{supplier['id']}",
            "order": "updated_at.desc",
            "limit": "100",
        },
        access_token=identity["_access_token"],
    )
    return {"items": rows, "count": len(rows)}


@app.post("/v1/supplier/offers", tags=["supplier"])
async def submit_supplier_offer(
    request: SupplierOfferSubmission = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_active_profile),
) -> dict[str, Any]:
    supplier = await get_owned_supplier(identity)
    if request.quote_expires_at.utcoffset() is None:
        raise HTTPException(status_code=422, detail="Quote expiry must include a timezone.")
    payload = request.model_dump(mode="json", exclude_none=True)
    if not payload.get("source_evidence"):
        raise HTTPException(status_code=422, detail="Supplier source evidence is required.")
    if payload.get("condition") not in PRODUCT_CONDITIONS:
        raise HTTPException(status_code=422, detail="Supplier offer condition is invalid.")
    if payload.get("source_url") and not payload["source_url"].lower().startswith(("https://", "http://")):
        raise HTTPException(status_code=422, detail="Supplier source URL must use HTTP or HTTPS.")
    result = await supabase_supplier_rpc(
        "oto_supplier_offer_submit",
        {"p_supplier_id": supplier["id"], "p_payload": payload, "p_request_id": idempotency_key},
        identity["_access_token"],
    )
    return {"result": result}


@app.get("/v1/admin/suppliers", tags=["supplier"])
async def list_admin_suppliers(
    status: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    identity: dict[str, Any] = Depends(require_roles("admin", "moderator", "catalog_editor", "inventory_manager")),
) -> dict[str, Any]:
    allowed_statuses = {"pending_review", "active", "suspended", "rejected"}
    if status and status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Supplier status filter is invalid.")
    params = {
        "select": "id,owner_user_id,legal_name,display_name,supplier_type,status,contact_name,contact_email,contact_phone,address,business_registration_number,website_url,reviewed_by,reviewed_at,review_note,created_at,updated_at",
        "order": "created_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }
    if status:
        params["status"] = f"eq.{status}"
    rows = await supabase_get("suppliers", params, access_token=identity["_access_token"])
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset, "next_offset": offset + limit if len(rows) == limit else None}


@app.get("/v1/admin/supplier-offers", tags=["supplier"])
async def list_admin_supplier_offers(
    status: str | None = Query(default=None, max_length=32),
    supplier_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    identity: dict[str, Any] = Depends(require_roles("admin", "moderator", "catalog_editor", "inventory_manager")),
) -> dict[str, Any]:
    allowed_statuses = {"pending_review", "active", "unavailable", "rejected", "expired"}
    if status and status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Supplier offer status filter is invalid.")
    params = {
        "select": "id,supplier_id,product_id,supplier_sku,source_url,source_evidence,condition,unit_cost,asking_price,currency,stock_quantity,stock_checked_at,quote_expires_at,status,lead_time_days,minimum_order_quantity,warranty_days,last_verified_by,source_verified_at,created_at,updated_at,suppliers(id,legal_name,display_name,status),products(id,sku,name,part_number,condition,status)",
        "order": "updated_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }
    if status:
        params["status"] = f"eq.{status}"
    if supplier_id:
        params["supplier_id"] = f"eq.{supplier_id}"
    rows = await supabase_get("supplier_offers", params, access_token=identity["_access_token"])
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset, "next_offset": offset + limit if len(rows) == limit else None}


@app.get("/v1/admin/supplier-documents", tags=["supplier"])
async def list_admin_supplier_documents(
    status: str | None = Query(default=None, max_length=32),
    supplier_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    identity: dict[str, Any] = Depends(require_roles("admin", "moderator", "catalog_editor")),
) -> dict[str, Any]:
    allowed_statuses = {"pending_review", "verified", "rejected", "expired"}
    if status and status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Supplier document status filter is invalid.")
    params = {
        "select": "id,supplier_id,document_type,storage_path,original_filename,content_type,file_size_bytes,sha256,expires_at,status,review_note,reviewed_by,reviewed_at,created_by,created_at,updated_at,suppliers(id,legal_name,display_name,status)",
        "order": "created_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }
    if status:
        params["status"] = f"eq.{status}"
    if supplier_id:
        params["supplier_id"] = f"eq.{supplier_id}"
    rows = await supabase_get("supplier_documents", params, access_token=identity["_access_token"])
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset, "next_offset": offset + limit if len(rows) == limit else None}


@app.get("/v1/admin/supplier-offers/{offer_id}/candidates", tags=["supplier"])
async def match_supplier_offer_candidates(
    offer_id: UUID,
    identity: dict[str, Any] = Depends(require_roles("admin", "moderator", "catalog_editor", "inventory_manager")),
) -> dict[str, Any]:
    result = await supabase_supplier_rpc(
        "oto_supplier_offer_match_candidates",
        {"p_offer_id": str(offer_id)},
        identity["_access_token"],
    )
    return {"result": result}


@app.post("/v1/admin/supplier-mutations", tags=["supplier"])
async def mutate_supplier_operations(
    mutation: SupplierAdminMutation = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_roles("admin", "moderator", "catalog_editor", "inventory_manager")),
) -> dict[str, Any]:
    allowed = {
        "approve_supplier", "reject_supplier", "suspend_supplier",
        "review_supplier_document", "approve_offer", "reject_offer", "expire_offer", "match_offer_product",
    }
    if mutation.action not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported supplier action.")
    if len(str(mutation.payload)) > 20000:
        raise HTTPException(status_code=413, detail="Supplier payload is too large.")
    result = await supabase_supplier_rpc(
        "oto_supplier_admin_mutate",
        {
            "p_action": mutation.action,
            "p_supplier_id": str(mutation.supplier_id) if mutation.supplier_id else None,
            "p_offer_id": str(mutation.offer_id) if mutation.offer_id else None,
            "p_document_id": str(mutation.document_id) if mutation.document_id else None,
            "p_payload": mutation.payload,
            "p_request_id": idempotency_key,
        },
        identity["_access_token"],
    )
    return {"result": result}


@app.get("/v1/admin/supplier-audit", tags=["supplier"])
async def list_supplier_audit(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    identity: dict[str, Any] = Depends(require_roles("admin")),
) -> dict[str, Any]:
    rows = await supabase_get(
        "audit_logs",
        {
            "select": "id,actor_user_id,action,entity_type,entity_id,request_id,created_at",
            "entity_type": "in.(supplier,supplier_document,supplier_offer)",
            "order": "created_at.desc",
            "limit": str(limit),
            "offset": str(offset),
        },
        access_token=identity["_access_token"],
    )
    return {
        "items": rows,
        "count": len(rows),
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if len(rows) == limit else None,
    }



class AdminRoleMutation(BaseModel):
    role: str = Field(min_length=1, max_length=32)
    is_active: bool

    model_config = {"extra": "forbid"}


async def supabase_admin_role_rpc(
    target_user_id: UUID,
    role: str,
    is_active: bool,
    request_id: str,
    access_token: str,
) -> dict[str, Any]:
    supabase_url, anon_key = require_supabase_configuration()
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{supabase_url}/rest/v1/rpc/oto_admin_set_user_role",
                headers=headers,
                json={
                    "p_target_user_id": str(target_user_id),
                    "p_role": role,
                    "p_is_active": is_active,
                    "p_request_id": request_id,
                },
            )
        if response.status_code in (401, 403):
            raise HTTPException(status_code=403, detail="Role change is not permitted.")
        if response.status_code == 429 or response.status_code >= 500:
            raise HTTPException(status_code=503, detail="Role service is temporarily unavailable.")
        if response.status_code not in (200, 201):
            body = response.json() if response.content else {}
            message = str(body.get("message", "")) if isinstance(body, dict) else ""
            if "target_profile_not_found" in message:
                raise HTTPException(status_code=404, detail="Target profile was not found.")
            if "cannot_remove_last_active_admin" in message:
                raise HTTPException(status_code=409, detail="The last active administrator cannot be removed.")
            if "request_id_reused_for_different_operation" in message:
                raise HTTPException(status_code=409, detail="Idempotency key was already used for another request.")
            if "cannot_change_own_role_or_active_state" in message:
                raise HTTPException(status_code=422, detail="You cannot change your own role or active state.")
            if "request_id_invalid" in message or "role_change_payload_invalid" in message:
                raise HTTPException(status_code=422, detail="Role change request is invalid.")
            if "admin_role_required" in message or "authentication_required" in message:
                raise HTTPException(status_code=403, detail="An active administrator role is required.")
            raise HTTPException(status_code=422, detail="Role change was rejected by the database guard.")
        payload = response.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=503, detail="Role service returned an invalid response.")
        return payload
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=503, detail="Role service request timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Could not reach role service.") from exc


async def supabase_admin_user_directory_rpc(
    query: str | None,
    role: str | None,
    status: str,
    limit: int,
    offset: int,
    access_token: str,
) -> dict[str, Any]:
    supabase_url, anon_key = require_supabase_configuration()
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{supabase_url}/rest/v1/rpc/oto_admin_list_users",
                headers=headers,
                json={
                    "p_query": query,
                    "p_role": role,
                    "p_status": status,
                    "p_limit": limit,
                    "p_offset": offset,
                },
            )
        if response.status_code in (401, 403):
            raise HTTPException(status_code=403, detail="User directory access is not permitted.")
        if response.status_code == 429 or response.status_code >= 500:
            raise HTTPException(status_code=503, detail="User directory service is temporarily unavailable.")
        if response.status_code not in (200, 201):
            body = response.json() if response.content else {}
            message = str(body.get("message", "")) if isinstance(body, dict) else ""
            if "admin_role_required" in message or "authentication_required" in message:
                raise HTTPException(status_code=403, detail="An active administrator role is required.")
            if "user_directory_pagination_invalid" in message or "user_directory_status_invalid" in message:
                raise HTTPException(status_code=422, detail="User directory filters are invalid.")
            raise HTTPException(status_code=422, detail="User directory query was rejected.")
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise HTTPException(status_code=503, detail="User directory returned an invalid response.")
        return payload
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=503, detail="User directory request timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Could not reach user directory service.") from exc


async def supabase_admin_provision_user_profile_rpc(
    target_user_id: UUID,
    request_id: str,
    access_token: str,
) -> dict[str, Any]:
    supabase_url, anon_key = require_supabase_configuration()
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{supabase_url}/rest/v1/rpc/oto_admin_provision_user_profile",
                headers=headers,
                json={"p_target_user_id": str(target_user_id), "p_request_id": request_id},
            )
        if response.status_code in (401, 403):
            raise HTTPException(status_code=403, detail="Profile provisioning is not permitted.")
        if response.status_code == 429 or response.status_code >= 500:
            raise HTTPException(status_code=503, detail="Profile provisioning service is temporarily unavailable.")
        if response.status_code not in (200, 201):
            body = response.json() if response.content else {}
            message = str(body.get("message", "")) if isinstance(body, dict) else ""
            if "auth_identity_not_found" in message:
                raise HTTPException(status_code=404, detail="The Auth identity was not found.")
            if "profile_already_exists" in message:
                raise HTTPException(status_code=409, detail="This Auth identity already has a profile.")
            if "request_id_reused_for_different_operation" in message:
                raise HTTPException(status_code=409, detail="Idempotency key was already used for another request.")
            if "profile_provision_payload_invalid" in message:
                raise HTTPException(status_code=422, detail="Profile provisioning request is invalid.")
            if "admin_role_required" in message or "authentication_required" in message:
                raise HTTPException(status_code=403, detail="An active administrator role is required.")
            raise HTTPException(status_code=422, detail="Profile provisioning was rejected by the database guard.")
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("profile"), dict):
            raise HTTPException(status_code=503, detail="Profile provisioning returned an invalid response.")
        return payload
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=503, detail="Profile provisioning request timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Could not reach profile provisioning service.") from exc


@app.get("/v1/admin/overview", tags=["admin"])
async def admin_overview(
    identity: dict[str, Any] = Depends(require_roles(
        "admin", "catalog_editor", "inventory_manager", "order_manager", "moderator"
    )),
) -> dict[str, Any]:
    """Return role-scoped operational metrics; unavailable domains are explicitly null."""
    role = identity["role"]
    token = identity["_access_token"]
    metric_specs: dict[str, tuple[str, dict[str, str], set[str], str]] = {
        "products": ("products", {}, {"admin", "catalog_editor", "moderator"}, "id"),
        "products_review": ("products", {"status": "eq.review"}, {"admin", "catalog_editor", "moderator"}, "id"),
        "fitments": ("product_fitments", {}, {"admin", "catalog_editor", "moderator"}, "id"),
        "fitments_review": ("product_fitments", {"status": "eq.needs_review"}, {"admin", "catalog_editor", "moderator"}, "id"),
        "suppliers": ("suppliers", {}, {"admin", "catalog_editor", "inventory_manager", "moderator"}, "id"),
        "suppliers_review": ("suppliers", {"status": "eq.pending_review"}, {"admin", "catalog_editor", "inventory_manager", "moderator"}, "id"),
        "supplier_offers": ("supplier_offers", {}, {"admin", "catalog_editor", "inventory_manager", "moderator"}, "id"),
        "supplier_offers_review": ("supplier_offers", {"status": "eq.pending_review"}, {"admin", "catalog_editor", "inventory_manager", "moderator"}, "id"),
        "supplier_documents_review": ("supplier_documents", {"status": "eq.pending_review"}, {"admin", "catalog_editor", "moderator"}, "id"),
        "inventory_movements": ("inventory_ledger", {}, {"admin", "inventory_manager", "order_manager"}, "id"),
        "inventory_products": ("inventory_balances", {}, {"admin", "inventory_manager", "order_manager"}, "product_id"),
        "orders": ("oto_orders", {}, {"admin", "order_manager"}, "id"),
        "orders_open": ("oto_orders", {"status": "in.(pending_payment,payment_review,paid,processing,shipped)"}, {"admin", "order_manager"}, "id"),
        "payment_reviews": ("oto_payment_events", {"status": "eq.pending_review"}, {"admin", "order_manager"}, "id"),
        "returns_open": ("oto_returns", {"status": "in.(requested,approved,received,refund_pending)"}, {"admin", "order_manager"}, "id"),
        "audit_events": ("audit_logs", {}, {"admin"}, "id"),
        "user_profiles": ("user_profiles", {}, {"admin"}, "id"),
    }
    async def read_metric(spec: tuple[str, dict[str, str], set[str], str]) -> int | None:
        table, filters, roles, select_column = spec
        if role not in roles:
            return None
        return await supabase_count(table, filters, token, select_column)

    metric_keys = list(metric_specs)
    metric_values = await asyncio.gather(*(read_metric(metric_specs[key]) for key in metric_keys))
    metrics = {
        key: {"value": metric_values[index], "available": metric_values[index] is not None}
        for index, key in enumerate(metric_keys)
    }
    latest_products: list[dict[str, Any]] = []
    if role in {"admin", "catalog_editor", "moderator"}:
        latest_products = await supabase_get(
            "products",
            {
                "select": "id,sku,name,category,condition,status,retail_price,updated_at",
                "order": "updated_at.desc",
                "limit": "6",
            },
            access_token=token,
        )
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "role": role,
        "metrics": metrics,
        "latest_products": latest_products,
    }


@app.get("/v1/admin/users", tags=["admin"])
async def list_admin_users(
    q: str | None = Query(default=None, max_length=80),
    role: str | None = Query(default=None, max_length=32),
    status: str = Query(default="all", max_length=24),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    identity: dict[str, Any] = Depends(require_roles("admin")),
) -> dict[str, Any]:
    allowed_roles = {
        "customer", "supplier", "catalog_editor", "inventory_manager",
        "order_manager", "moderator", "admin",
    }
    if role is not None and role not in allowed_roles:
        raise HTTPException(status_code=422, detail="Role filter is not supported.")
    if status not in {"all", "active", "inactive", "missing_profile"}:
        raise HTTPException(status_code=422, detail="User status filter is not supported.")
    return await supabase_admin_user_directory_rpc(
        q.strip() if q and q.strip() else None,
        role,
        status,
        limit,
        offset,
        identity["_access_token"],
    )


@app.post("/v1/admin/users/{user_id}/provision", tags=["admin"])
async def provision_admin_user_profile(
    user_id: UUID,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_roles("admin")),
) -> dict[str, Any]:
    result = await supabase_admin_provision_user_profile_rpc(
        user_id, idempotency_key, identity["_access_token"]
    )
    return {"result": result}


@app.post("/v1/admin/users/{user_id}/role", tags=["admin"])
async def mutate_admin_user_role(
    user_id: UUID,
    mutation: AdminRoleMutation = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_roles("admin")),
) -> dict[str, Any]:
    allowed_roles = {
        "customer", "supplier", "catalog_editor", "inventory_manager",
        "order_manager", "moderator", "admin",
    }
    if mutation.role not in allowed_roles:
        raise HTTPException(status_code=422, detail="Role value is not supported.")
    result = await supabase_admin_role_rpc(
        user_id, mutation.role, mutation.is_active, idempotency_key, identity["_access_token"]
    )
    return {"result": result}


@app.get("/v1/admin/audit", tags=["admin"])
async def list_admin_audit(
    action: str | None = Query(default=None, max_length=80),
    entity_type: str | None = Query(default=None, max_length=80),
    q: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    identity: dict[str, Any] = Depends(require_roles("admin")),
) -> dict[str, Any]:
    params = {
        "select": "id,actor_user_id,action,entity_type,entity_id,request_id,created_at",
        "order": "created_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }
    if action:
        params["action"] = f"eq.{safe_search_term(action)}"
    if entity_type:
        params["entity_type"] = f"eq.{safe_search_term(entity_type)}"
    if q:
        term = safe_search_term(q)
        if term:
            params["or"] = f"(action.ilike.*{term}*,entity_type.ilike.*{term}*,request_id.ilike.*{term}*)"
    rows = await supabase_get("audit_logs", params, access_token=identity["_access_token"])
    return {
        "items": rows,
        "count": len(rows),
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if len(rows) == limit else None,
    }


# Phase 07 transaction endpoints are mounted after the shared auth/data helpers.
from app.phase07 import router as phase07_router
app.include_router(phase07_router)

from app.shipping import router as shipping_router
app.include_router(shipping_router)

from app.payments import router as payments_router
app.include_router(payments_router)

from app.integrations import router as integrations_router, start_integration_worker, stop_integration_worker
app.include_router(integrations_router)

@app.on_event("startup")
async def start_commerce_integration_worker() -> None:
    start_integration_worker()

@app.on_event("shutdown")
async def stop_commerce_integration_worker() -> None:
    await stop_integration_worker()

from app.integrations import router as integrations_router
app.include_router(integrations_router)


# Homepage merchandising: public read, role-protected admin write.
class HomepageSectionConfig(BaseModel):
    enabled: bool
    sort_order: int = Field(ge=0, le=100)
    limit: int = Field(ge=1, le=24)
    model_config = {"extra": "forbid"}

class HomepageSettingsUpdate(BaseModel):
    sections: dict[str, HomepageSectionConfig]
    model_config = {"extra": "forbid"}

class HomepageCampaignCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    kind: str = Field(pattern=r"^(promotion|advertisement)$")
    status: str = Field(default="draft", pattern=r"^(draft|scheduled|active|paused|ended)$")
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    product_ids: list[UUID] = Field(default_factory=list, max_length=100)
    target_url: str | None = Field(default=None, max_length=2048)
    priority: int = Field(default=100, ge=0, le=10000)
    model_config = {"extra": "forbid"}

HOMEPAGE_SECTION_KEYS = {"best_seller", "popular", "secondary", "new_products", "promotions", "advertisements"}
DEFAULT_HOMEPAGE_SECTIONS = {
    "best_seller": {"enabled": True, "sort_order": 1, "limit": 8},
    "popular": {"enabled": True, "sort_order": 2, "limit": 8},
    "secondary": {"enabled": True, "sort_order": 3, "limit": 8},
    "new_products": {"enabled": True, "sort_order": 4, "limit": 8},
    "promotions": {"enabled": True, "sort_order": 5, "limit": 8},
    "advertisements": {"enabled": False, "sort_order": 6, "limit": 4},
}

@app.get("/v1/storefront/homepage", tags=["storefront"])
async def get_storefront_homepage() -> dict[str, Any]:
    settings_rows = await supabase_get("oto_homepage_settings", {"select":"sections,updated_at","id":"eq.true","limit":"1"})
    sections = settings_rows[0].get("sections", DEFAULT_HOMEPAGE_SECTIONS) if settings_rows else DEFAULT_HOMEPAGE_SECTIONS
    if not isinstance(sections, dict): sections = DEFAULT_HOMEPAGE_SECTIONS
    now = datetime.now(timezone.utc).isoformat()
    products: dict[str, list[dict[str, Any]]] = {}
    for key in sorted(HOMEPAGE_SECTION_KEYS, key=lambda k: sections.get(k, {}).get("sort_order", 99) if isinstance(sections.get(k), dict) else 99):
        cfg = sections.get(key, DEFAULT_HOMEPAGE_SECTIONS[key])
        if not isinstance(cfg, dict) or not cfg.get("enabled", False): continue
        limit = max(1, min(int(cfg.get("limit", 8)), 24))
        if key == "new_products":
            rows = await supabase_get("products", {"select":"id,sku,slug,name,brand,part_number,category,condition,retail_price,published_at","status":"eq.published","order":"published_at.desc.nullslast","limit":str(limit)})
        elif key == "secondary":
            rows = await supabase_get("products", {"select":"id,sku,slug,name,brand,part_number,category,condition,retail_price,published_at","status":"eq.published","condition":"in.(used,refurbished,remanufactured,damaged_for_parts)","order":"published_at.desc.nullslast","limit":str(limit)})
        elif key == "best_seller":
            sales = await supabase_rpc("oto_public_homepage_best_sellers", {"p_limit": limit})
            ordered = [str(row.get("product_id")) for row in sales if row.get("product_id")]
            tally = {str(row.get("product_id")): int(row.get("units_sold") or 0) for row in sales if row.get("product_id")}
            rows = await supabase_get("products", {"select":"id,sku,slug,name,brand,part_number,category,condition,retail_price,published_at","status":"eq.published","id":"in.("+",".join(ordered)+")","limit":str(limit)}) if ordered else []
            rows.sort(key=lambda row: tally.get(str(row.get("id")),0), reverse=True)
            for row in rows: row["verified_units_sold"] = tally.get(str(row.get("id")),0)
        elif key == "popular":
            events = await supabase_rpc("oto_public_homepage_popular", {"p_since": datetime.now(timezone.utc).replace(day=1,hour=0,minute=0,second=0,microsecond=0).isoformat(), "p_limit": limit})
            ordered = [str(row.get("product_id")) for row in events if row.get("product_id")]
            tally = {str(row.get("product_id")): int(row.get("search_events") or 0) for row in events if row.get("product_id")}
            rows = await supabase_get("products", {"select":"id,sku,slug,name,brand,part_number,category,condition,retail_price,published_at","status":"eq.published","id":"in.("+",".join(ordered)+")","limit":str(limit)}) if ordered else []
            rows.sort(key=lambda row: tally.get(str(row.get("id")),0), reverse=True)
            for row in rows: row["verified_search_events"] = tally.get(str(row.get("id")),0)
        elif key in {"promotions","advertisements"}:
            kind = "promotion" if key == "promotions" else "advertisement"
            campaigns = await supabase_get("oto_homepage_promotions", {"select":"id,title,description,kind,status,starts_at,ends_at,product_ids,target_url,priority","kind":"eq."+kind,"status":"in.(active,scheduled)","or":"(starts_at.is.null,starts_at.lte."+now+")","order":"priority.asc,created_at.desc","limit":str(limit)})
            campaigns = [c for c in campaigns if (not c.get("starts_at") or c["starts_at"] <= now) and (not c.get("ends_at") or c["ends_at"] > now)]
            if key == "promotions":
                ids = list(dict.fromkeys(str(pid) for c in campaigns for pid in c.get("product_ids", [])))
                rows = await supabase_get("products", {"select":"id,sku,slug,name,brand,part_number,category,condition,retail_price,published_at","status":"eq.published","id":"in.("+",".join(ids)+")","limit":str(limit)}) if ids else []
            else:
                rows = campaigns
            products[key] = rows
            continue
        else:
            rows = []
        products[key] = rows
    return {"sections": sections, "items": products, "generated_at": now, "data_policy":"only published products, confirmed sales, recorded search events and active campaigns; no synthetic metrics"}

@app.get("/v1/admin/storefront/homepage", tags=["admin-storefront"])
async def admin_get_homepage_settings(identity: dict[str, Any] = Depends(require_roles("admin"))) -> dict[str, Any]:
    settings_rows = await supabase_get("oto_homepage_settings", {"select":"sections,updated_at,updated_by","id":"eq.true","limit":"1"}, access_token=identity["_access_token"])
    campaigns = await supabase_get("oto_homepage_promotions", {"select":"id,title,description,kind,status,starts_at,ends_at,product_ids,target_url,priority,created_at,updated_at","order":"created_at.desc","limit":"200"}, access_token=identity["_access_token"])
    return {"sections": settings_rows[0]["sections"] if settings_rows else DEFAULT_HOMEPAGE_SECTIONS, "updated_at": settings_rows[0].get("updated_at") if settings_rows else None, "campaigns": campaigns}

@app.put("/v1/admin/storefront/homepage", tags=["admin-storefront"])
async def admin_update_homepage_settings(request: HomepageSettingsUpdate = Body(...), identity: dict[str, Any] = Depends(require_roles("admin"))) -> dict[str, Any]:
    if set(request.sections) != HOMEPAGE_SECTION_KEYS:
        raise HTTPException(status_code=422, detail="Semua bagian katalog harus dikirim dengan key yang valid.")
    actor = (identity.get("user") or {}).get("id")
    sections = {key: cfg.model_dump() for key,cfg in request.sections.items()}
    rows = await supabase_write("POST", "oto_homepage_settings", identity["_access_token"], {"id":True,"sections":sections,"updated_by":actor,"updated_at":datetime.now(timezone.utc).isoformat()})
    if not rows:
        rows = await supabase_write("PATCH", "oto_homepage_settings", identity["_access_token"], {"sections":sections,"updated_by":actor,"updated_at":datetime.now(timezone.utc).isoformat()}, {"id":"eq.true"})
    return {"sections": sections, "saved": bool(rows)}

@app.post("/v1/admin/storefront/campaigns", tags=["admin-storefront"], status_code=201)
async def admin_create_homepage_campaign(request: HomepageCampaignCreate = Body(...), identity: dict[str, Any] = Depends(require_roles("admin"))) -> dict[str, Any]:
    if request.starts_at and request.ends_at and request.ends_at <= request.starts_at:
        raise HTTPException(status_code=422, detail="Tanggal akhir harus setelah tanggal mulai.")
    actor = (identity.get("user") or {}).get("id")
    payload = request.model_dump(mode="json", exclude_none=True)
    payload.update({"created_by":actor,"updated_by":actor})
    rows = await supabase_write("POST", "oto_homepage_promotions", identity["_access_token"], payload)
    if not rows: raise HTTPException(status_code=503, detail="Kampanye tidak dapat disimpan.")
    return {"campaign": rows[0]}

@app.patch("/v1/admin/storefront/campaigns/{campaign_id}", tags=["admin-storefront"])
async def admin_update_homepage_campaign(campaign_id: UUID, request: HomepageCampaignCreate = Body(...), identity: dict[str, Any] = Depends(require_roles("admin"))) -> dict[str, Any]:
    if request.starts_at and request.ends_at and request.ends_at <= request.starts_at:
        raise HTTPException(status_code=422, detail="Tanggal akhir harus setelah tanggal mulai.")
    payload = request.model_dump(mode="json", exclude_none=True)
    payload.update({"updated_by":(identity.get("user") or {}).get("id"),"updated_at":datetime.now(timezone.utc).isoformat()})
    rows = await supabase_write("PATCH", "oto_homepage_promotions", identity["_access_token"], payload, {"id":"eq."+str(campaign_id)})
    if not rows: raise HTTPException(status_code=404, detail="Kampanye tidak ditemukan.")
    return {"campaign": rows[0]}
