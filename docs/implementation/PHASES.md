# OtoClinic — Implementation Phases

Brand: OtoClinic. Production database already contains a preliminary business schema. The implementation must reconcile with that live schema, not recreate it.

## Phase 00 — Audit and reconcile (in progress)
- Inspect repository, deployment, Supabase schemas, tables, enums, functions, triggers, grants, RLS, Storage, migrations, and advisors.
- Keep a schema inventory and identify discrepancies between live DB and repository.
- Never treat an empty migration listing as proof that the database has no schema.
- Current observed tables include user_profiles, vehicle_makes, vehicle_models, vehicle_variants, products, product_fitments, suppliers, supplier_offers, inventory_ledger, audit_logs.
- Security remediation applied: revoke EXECUTE on public.rls_auto_enable() from public, anon, authenticated. Re-run advisor and inspect function/trigger behavior before changing it further.

## Phase 01 — Brand, product flows and acceptance
- OtoClinic brand system; Indonesian UI and IDR.
- Customer flow: vehicle selector → part search → fitment evidence → condition/warranty → cart/checkout → payment evidence → tracking.
- Operations flow: moderation → sourcing → catalog → inventory ledger → order/payment/fulfillment.
- Supplier flow: onboarding → document review → offers/stock freshness → performance.

## Phase 02 — Design system
- Shared tokens, responsive grid, accessible controls, product condition and fitment states.
- Every screen includes loading, empty, error, success, offline, and permission-denied states.
- No demo metrics or unverified listings represented as live.

## Phase 03 — Application foundation
- Next.js + TypeScript PWA client/admin shell; FastAPI backend scaffold.
- Typecheck, lint, tests, environment validation, CI and error handling.
- Deployment provider and production URL must be confirmed from actual configuration, not guessed.

## Phase 04 — Authentication and authorization
- Supabase Auth, server-verified identity, role/permission checks, session handling.
- RLS and grants tested for anon, customer, supplier, staff, admin.
- Privileged operations stay in backend; no service-role key in client.

## Phase 05 — Catalog and fitment
- Reconcile and extend current product/vehicle tables via additive migration only.
- Catalog lifecycle draft → review → approved → published → archived/rejected.
- Fitment requires evidence, vehicle variant, reviewer, and verification status.
- Product photos require ownership/license evidence.

## Phase 06 — Supplier and sourcing
- Supplier verification, source evidence, quote validity, stock timestamp, acquisition cost and lead time.
- Candidate matching and deduplication; insufficient evidence is NOT_READY.

## Phase 07 — Inventory and order lifecycle
- Preserve current inventory_ledger; implement atomic stock mutations and idempotency.
- Cart/checkout, payment verification, fulfillment, returns/refunds and audit events.
- Never equate uploaded transfer receipt with verified payment.

## Phase 08 — Super Admin
- Dashboard, catalog, supplier, inventory, orders, moderation, role controls and audit log.
- No fake KPI. Count actual rows only when authorized and backed by real data.
- Mutations require backend authorization, confirmation, and audit.

## Phase 09 — Customer PWA
- Mobile-first search, vehicle fitment, product detail, condition, warranty, cart, checkout, order tracking.
- Cache app shell only; never publicly cache user orders or payment data.

## Phase 10 — AI and search
- Part number normalization, evidence-backed candidate search, confidence/uncertainty.
- AI cannot independently publish uncertain fitment, price, or product data.

## Phase 11 — Integrations
- WhatsApp/outbox, supplier feed, payment and logistics adapters when credentials/providers are configured.
- Verify webhook signatures and make retries idempotent.

## Phase 12 — QA and release
- Unit/integration/E2E, RLS, accessibility, mobile/desktop, performance, security advisor, backup/restore, production smoke test.
- A green build is not the same as verified production deployment.

## Working policy
Implementation commits go directly to `main` as requested. Production changes remain additive and evidence-based; do not drop/recreate existing tables, weaken RLS, fabricate data, or claim deployment success without verification.
