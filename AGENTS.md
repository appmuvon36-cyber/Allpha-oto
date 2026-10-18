# AGENTS.md — OtoClinic Repository Rules

## Mandatory first step: read the Master PRD
Before planning, editing, generating UI, changing schemas, writing API routes, or modifying deployment configuration, every AI agent MUST read:
1. `docs/prd/MASTER_PRD.md` — canonical product, architecture, security, UI/UX, and acceptance requirements.
2. `docs/implementation/PHASES.md` — implementation sequence and phase status.
3. `docs/architecture/BASELINE_AUDIT.md` — known live baseline and audit constraints.
4. `docs/design-system/FOUNDATIONS.md` and `docs/design-system/MAGICPATH_UI_UX.md` — design tokens and the previously created UI plugin artifacts.
5. The relevant source code and current production configuration before making changes.

If the PRD conflicts with observed production state, do not blindly overwrite production. Document the discrepancy, preserve existing data, and reconcile with additive changes. Never claim an audit or test passed without evidence.

## Canonical resources
- GitHub repository (single source of code): https://github.com/appmuvon36-cyber/Allpha-oto
- Default branch: `main`
- Supabase project: https://supabase.com/dashboard/project/nunnugavnpaumqefmitn
- Supabase API URL: `https://nunnugavnpaumqefmitn.supabase.co`
- Railway project: https://railway.com/project/ff2625be-254a-4243-bf00-ed99080fd537
- Railway production environment ID: `3b5a32c8-4f16-453e-b20f-91dd5669e4f4`
- Customer PWA: https://otoclinic-web-production.up.railway.app
- Super Admin: https://otoclinic-admin-production.up.railway.app
- FastAPI: https://otoclinic-api-production.up.railway.app
- MagicPath UI/UX project: https://www.magicpath.ai/ (project ID `462564795376340992`, name “Allpha Oto — Premium Spare Parts UI/UX”)

## Monorepo layout
```text
Allpha-oto/
├── apps/
│   ├── web/                 # Customer Next.js PWA
│   └── admin/               # Super Admin Next.js workspace
├── backend/                 # FastAPI; business rules and privileged operations
├── supabase/                # Existing project config, migrations, seed/test assets
├── docs/
│   ├── prd/MASTER_PRD.md
│   ├── architecture/
│   ├── design-system/
│   └── implementation/
├── .github/workflows/
├── AGENTS.md
└── [root app compatibility files retained until migration is verified]
```

The three Railway services must deploy from this SAME repository and branch with root directories `/apps/web`, `/apps/admin`, and `/backend`. Do not create a second repository, Supabase project, or production database. Do not delete the root compatibility app until route parity and rollback are proven.

## Required implementation order
For a feature, follow this sequence and report evidence at every stage:
1. **Read & inspect:** read Master PRD, relevant docs, source files, GitHub history, current Railway service config/logs, and live Supabase schema/policies.
2. **Map requirement:** define acceptance criteria, affected tables/RLS, API contracts, UI routes, roles, and rollback strategy.
3. **Supabase first:** use the existing project only. Inspect tables, enums, indexes, grants, RLS, functions, triggers, Storage, and migration history. Add an idempotent, reviewed migration under `supabase/migrations/`; never reset/drop/recreate live schema to simplify work. Verify policies for anon, customer, supplier, staff and admin roles. Use synthetic test identities only in non-production or explicit test fixtures.
4. **Backend API second:** implement/validate FastAPI schemas, authentication, authorization, input validation, business logic, transaction boundaries, idempotency, audit events, error handling, and tests. Verify JWTs server-side. Privileged database/service-role credentials may only be used server-side; never expose them to a browser or logs.
5. **Customer frontend third:** implement `apps/web` against documented API/data contracts. Browser Supabase keys must be publishable/anon only; never trust client-side role checks as the security boundary. Real data only; no fabricated products, prices, stock, metrics, fitment, or success states.
6. **Super Admin frontend fourth:** implement `apps/admin` with sign-in, session recovery, server/API authorization, role-denied state, loading/empty/error/offline states, confirmation for sensitive actions, and audit visibility. A hidden button or client-side guard is not authorization.
7. **QA & release:** lint/typecheck/unit/integration tests; RLS and IDOR tests; direct HTTP route checks; authenticated/unauthenticated E2E; mobile/desktop checks; security review; deploy; check health, logs, and rollback path.

## Security rules
- Never put Supabase service-role keys, database passwords, Railway tokens, private API keys, or payment secrets in source, client bundles, documentation, issues, or logs.
- Public `NEXT_PUBLIC_*` variables may contain only the project URL and publishable/anon key.
- All protected data access must be enforced by RLS and/or backend authorization, not just React state.
- Admin role is read from the trusted profile/authorization source and validated on every privileged API request.
- Never trust a user ID, role, price, inventory quantity, payment state, fitment state, or supplier status supplied by the client.
- Mutations need validation, permission checks, transactions where appropriate, idempotency for retried requests, and audit records.
- Do not weaken RLS or grant broad privileges to make UI queries work. Fix the specific policy and test it.
- Do not log passwords, access tokens, session cookies, or sensitive personal data.

## UI/UX and plugin artifacts
Use the previously created MagicPath artifacts as the design reference, not as a source of production data:
- Customer homepage / Smart Parts Finder: `friendly-ocean-4932`
- Super Admin Operations Dashboard: `bold-air-1063`
- Design System Foundations: `dreamily-park-9006`
Project ID: `462564795376340992`. See `docs/design-system/MAGICPATH_UI_UX.md`.
Keep the OtoClinic brand; preserve the minimal light UI, navy `#101B2B`, action orange `#EF5B2A`, canvas `#F5F6F8`, clear typography, responsive layout, visible focus, and semantic states. The MagicPath customer prototype includes sample product cards: those are illustrative only and MUST NOT be presented as live catalog data. Use existing UI assets/components only after dependency, accessibility, and behavior review.

## Production verification gates
- `/` customer page: live HTTP 2xx, responsive, and no unverified sample data represented as actual listings.
- `/login`: live HTTP 2xx; login errors do not disclose account existence; no public admin registration.
- `/admin`: unauthenticated users see no protected data; invalid/non-operational roles are denied; authenticated permitted roles can query only authorized records.
- `/health`: API returns 2xx with a minimal health response and no secrets.
- Test API endpoints and database/RLS behavior separately; a successful build or root-page health check does not prove login, role enforcement, or data access.
- Inspect actual HTTP response codes/body, deployment logs, and live config. Railway request metrics with zero requests are not proof that routes work.
- Record commit SHA, deployment ID, check time, route/status, and result. If a gate fails, fix and rerun before marking complete.

## Change management
- Keep one repository and existing Supabase project.
- Follow the current direct-to-`main` operating preference; make focused commits and avoid unrelated refactors.
- Do not create fake/mocked production data or mark a feature complete based on a scaffold.
- Do not claim a service, test, integration, or security control is verified without direct evidence.
- Preserve backwards compatibility and use rollback-safe deployments. Never remove a working production deployment before its replacement passes health and smoke tests.
