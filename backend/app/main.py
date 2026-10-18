from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
import hashlib
import re
from typing import Any
from urllib.parse import quote
from uuid import UUID

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


def safe_search_term(value: str) -> str:
    """Keep user search input from altering PostgREST filter grammar."""
    return re.sub(r"[^\w .\-]", " ", value, flags=re.UNICODE).strip()


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


@app.get("/v1/catalog/products", tags=["catalog"])
async def list_public_products(
    q: str | None = Query(default=None, min_length=1, max_length=100),
    category: str | None = Query(default=None, min_length=1, max_length=80),
    condition: str | None = Query(default=None, min_length=1, max_length=40),
    part_number: str | None = Query(default=None, min_length=1, max_length=100),
    variant_id: UUID | None = None,
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
) -> dict[str, Any]:
    """Public catalog search. Supabase RLS limits results to published products."""
    params = {
        "select": "id,sku,slug,name,description,brand,part_number,category,condition,condition_grade,package_quantity,warranty_days,currency,retail_price,fitment_summary,published_at",
        "status": "eq.published",
        "order": "name.asc",
        "limit": str(limit),
        "offset": str(offset),
    }
    if category:
        term = safe_search_term(category)
        if term:
            params["category"] = f"ilike.*{term}*"
    if condition:
        normalized = condition.strip().lower()
        if normalized not in PRODUCT_CONDITIONS:
            raise HTTPException(status_code=422, detail="Unsupported product condition.")
        params["condition"] = f"eq.{normalized}"
    if part_number:
        term = safe_search_term(part_number)
        if term:
            params["part_number"] = f"ilike.*{term}*"
    if q:
        term = safe_search_term(q)
        if term:
            params["or"] = f"(name.ilike.*{term}*,sku.ilike.*{term}*,brand.ilike.*{term}*,part_number.ilike.*{term}*)"
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
            if code == "P0002" or "not_found" in message:
                raise HTTPException(status_code=404, detail="Catalog record was not found.")
            if code == "42501":
                raise HTTPException(status_code=403, detail="Catalog operation is not permitted for this role.")
            if code in ("22023", "22P02", "23505", "23514", "23502"):
                raise HTTPException(status_code=422, detail="Catalog operation failed validation.")
            raise HTTPException(status_code=503, detail="Catalog operation could not be completed.")
        return response.json()
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=503, detail="Catalog service timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Could not reach catalog service.") from exc


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
