# OtoClinic API

FastAPI service bootstrap. Current endpoints are operational health checks only; business endpoints must not be added until Supabase JWT verification, role checks, request validation, and audit behavior are implemented.

## Local
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Environment:
- `APP_NAME`
- `ENVIRONMENT` (set to `development` for local docs)
- `ALLOWED_ORIGINS` (comma-separated exact origins)

Do not put Supabase service-role credentials in the client app. Production readiness requires a verified JWT/auth dependency, rate limiting, structured logs, tests, and configured deployment.
