from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "OtoClinic API"
    environment: str = "production"
    allowed_origins: str = "http://localhost:3000"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
app = FastAPI(title=settings.app_name, version="0.1.0", docs_url=None if settings.environment == "production" else "/docs", redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "otoclinic-api", "environment": settings.environment}


@app.get("/ready", tags=["system"])
async def readiness() -> dict[str, str]:
    # Database/auth readiness is intentionally not claimed until server credentials and
    # a server-side JWT verifier are configured for the deployment environment.
    return {"status": "configuration-required", "service": "otoclinic-api"}
