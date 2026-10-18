from collections.abc import Callable
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
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
    version="0.2.0",
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


def require_supabase_configuration() -> tuple[str, str]:
    url = settings.supabase_url.rstrip("/")
    key = settings.supabase_anon_key
    if not url or not key:
        raise HTTPException(
            status_code=503,
            detail="Supabase Auth is not configured on the API service.",
        )
    return url, key


async def get_current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    """Verify a Supabase bearer token and resolve only the caller's own profile."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer access token required.")

    supabase_url, anon_key = require_supabase_configuration()
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {credentials.credentials}",
    }

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
                params={
                    "id": f"eq.{user_id}",
                    "select": "id,display_name,phone,role,is_active",
                    "limit": "1",
                },
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
                # A missing profile has no role and never grants elevated access.
                "role": profile.get("role") if profile else None,
            }
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=503, detail="Supabase request timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Could not reach Supabase.") from exc


def require_roles(*allowed_roles: str) -> Callable[..., Any]:
    """Build a reusable FastAPI dependency for active profiles with explicit roles."""
    normalized_roles = frozenset(role.strip().lower() for role in allowed_roles if role.strip())
    if not normalized_roles:
        raise ValueError("require_roles needs at least one non-empty role.")

    async def role_dependency(
        identity: dict[str, Any] = Depends(get_current_identity),
    ) -> dict[str, Any]:
        profile = identity.get("profile")
        if not isinstance(profile, dict):
            raise HTTPException(status_code=403, detail="An active user profile is required.")
        if profile.get("is_active") is not True:
            raise HTTPException(status_code=403, detail="This account is inactive or not provisioned.")
        role = profile.get("role")
        if not isinstance(role, str) or role.strip().lower() not in normalized_roles:
            raise HTTPException(status_code=403, detail="Your role is not allowed to perform this action.")
        return identity

    return role_dependency


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
    # This checks configuration only, not database connectivity or full business readiness.
    return {"status": "configured", "service": "otoclinic-api"}


@app.get("/v1/auth/me", tags=["auth"])
async def get_current_user(
    identity: dict[str, Any] = Depends(get_current_identity),
) -> dict[str, Any]:
    """Return the authenticated user's own identity/profile for any user category."""
    return identity
