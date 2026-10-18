# OtoClinic — Implementation Phases

Brand: OtoClinic. Production database already contains a preliminary business schema. The implementation must reconcile with that live schema, not recreate it.

## Phase 00 — Audit and reconcile (VERIFIED: baseline recorded)
- Live repository, Railway services, Supabase schema, migration ledger, enums, indexes, triggers, RLS policies, function grants and security advisor findings are recorded in [PHASE_00_AUDIT.md](./PHASE_00_AUDIT.md).
- Ten existing public business tables were observed; RLS is enabled on all ten. Queried business-table row counts were zero at audit time. No mock/seed production data was added.
- Both live migration versions are recorded. The source file for the applied foundation migration is missing from the repository; this is explicitly documented and must be recovered from live catalog metadata before any future schema DDL. Do not reapply the foundation migration to production.
- `public.rls_auto_enable()` EXECUTE remains revoked from public/anon/authenticated. `public.oto_has_staff_role(...)` is a reviewed advisor warning used by existing RLS policies; do not revoke/convert it without a policy-safe replacement.
- No destructive schema changes, new database, RLS weakening, or compatibility-app deletion was performed.
- Early-stage verification policy: focused configuration/schema inspection and relevant smoke checks only; defer broad unit/integration/E2E suites until the corresponding features exist.

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
