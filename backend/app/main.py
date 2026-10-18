from collections.abc import Callable
import re
from typing import Any
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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


@app.get("/v1/admin/products", tags=["catalog"])
async def list_admin_products(
    identity: dict[str, Any] = Depends(require_roles("admin", "catalog_editor", "moderator")),
) -> dict[str, Any]:
    """Read real catalog rows for authorized staff; Supabase RLS remains authoritative."""
    rows = await supabase_get(
        "products",
        {
            "select": "id,sku,slug,name,description,brand,part_number,category,condition,status,currency,retail_price,created_at,updated_at",
            "order": "created_at.desc",
            "limit": "100",
        },
        access_token=identity["_access_token"],
    )
    return {"items": rows, "count": len(rows), "limit": 100}
