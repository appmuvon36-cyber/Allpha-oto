# OtoClinic — Implementation Phases

Brand: OtoClinic. Production database already contains a preliminary business schema. Reconcile with that live schema; do not recreate it.

## Phase 00 — Audit and reconcile (VERIFIED: baseline recovered; historical source gap documented)
- Repository, Railway services, Supabase tables, migration ledger, enums, constraints, indexes, RLS and security findings are recorded in [PHASE_00_AUDIT.md](./PHASE_00_AUDIT.md).
- Ten public business tables exist and RLS is enabled on all ten. Queried table row counts were zero at audit time; no mock/seed data was added.
- The applied foundation migration's original SQL is missing. A catalog-derived recovery artifact is committed at [FOUNDATION_SCHEMA_RECOVERY.md](./FOUNDATION_SCHEMA_RECOVERY.md). It is documentation, not executable SQL, and does not claim byte-for-byte recovery or full migration parity.
- \`public.rls_auto_enable()\` EXECUTE remains revoked from public/anon/authenticated. \`public.oto_has_staff_role(...)\` is used by existing RLS policies; do not revoke or convert without a policy-safe replacement.
- No destructive schema change, new DB/service, RLS weakening, or compatibility-app deletion was performed.

## Phase 01 — Brand, product flows and acceptance (SPECIFIED; implementation ongoing)
- OtoClinic brand system; Indonesian UI and IDR.
- Customer flow: vehicle selector → part search → fitment evidence → condition/warranty → cart/checkout → payment evidence → tracking.
- Operations flow: moderation → sourcing → catalog → inventory ledger → order/payment/fulfillment.
- Supplier flow: onboarding → document review → offers/stock freshness → performance.

## Phase 02 — Design system (BASELINE EXISTS; screen coverage ongoing)
- Shared tokens, responsive grid, accessible controls, product condition and fitment states.
- Every screen includes loading, empty, error, success, offline, and permission-denied states.
- No demo metrics or unverified listings represented as live.

## Phase 03 — Application foundation (BASELINE EXISTS; release hardening deferred)
- Next.js + TypeScript PWA client/admin shell; FastAPI backend scaffold.
- Typecheck, lint, tests, environment validation, CI and error handling.
- Deployment provider and production URL must be confirmed from actual configuration, not guessed.

## Phase 04 — Authentication and authorization (IMPLEMENTED FOUNDATION; FINAL SESSION QA DEFERRED)
- Supabase Auth server verification, reusable \`get_current_identity\` and \`require_roles(...)\`.
- \`/v1/auth/me\` remains available to all authenticated user categories; \`GET /v1/admin/products\` requires admin/catalog_editor/moderator and forwards the caller JWT so Supabase RLS remains authoritative.
- Focused local checks cover missing/invalid token, inactive profile, allowed/disallowed roles and the protected catalog route.
- Real active-user role tests, end-to-end session/RLS checks and final production authorization matrix are explicitly deferred to Phase 12 when real test accounts and valid sessions are available.
- Privileged operations stay in backend; no service-role key in client. Do not weaken existing RLS.

## Phase 05 — Catalog and fitment (READ API + ADMIN REVIEW WORKSPACE BASELINE; MUTATION LIFECYCLE REMAINS)
- \`GET /v1/catalog/products\`: published-only search, category, condition, part-number, limit and offset filters.
- \`GET /v1/vehicles/makes\`, \`/v1/vehicles/models\`, \`/v1/vehicles/variants\`: active vehicle taxonomy reads.
- \`GET /v1/catalog/products/{product_id}/fitments\`: verified fitments only, joined to vehicle variant/model/make; current RLS remains the source of access control.
- \`GET /v1/admin/products\`: role-gated staff catalog read.
- Remaining: staff create/edit/review/approve/publish/reject/archive lifecycle; fitment evidence capture and reviewer workflow; product image ownership/licence evidence; wire the web/admin screens to these APIs. Add only additive schema changes if required after checking the live schema. No unverified fitment may be presented as verified.

## Phase 06 — Supplier and sourcing (NOT IMPLEMENTED)
- Supplier verification, source evidence, quote validity, stock timestamp, acquisition cost and lead time.
- Candidate matching and deduplication; insufficient evidence is NOT_READY.

## Phase 07 — Inventory and order lifecycle (NOT IMPLEMENTED)
- Preserve current \`inventory_ledger\`; implement atomic stock mutations and idempotency.
- Cart/checkout, payment verification, fulfillment, returns/refunds and audit events.
- Never equate uploaded transfer receipt with verified payment.

## Phase 08 — Super Admin (READ-ONLY BASELINE EXISTS; OPERATIONS INCOMPLETE)
- Dashboard, catalog, supplier, inventory, orders, moderation, role controls and audit log.
- No fake KPI. Count actual rows only when authorized and backed by real data.
- Mutations require backend authorization, confirmation, and audit.

## Phase 09 — Customer PWA (PARTIAL STOREFRONT EXISTS)
- Mobile-first search, vehicle fitment, product detail, condition, warranty, cart, checkout, order tracking.
- Cache app shell only; never publicly cache user orders or payment data.
- Existing storefront is a real published-product listing/search baseline, not a completed checkout journey.

## Phase 10 — AI and search (NOT IMPLEMENTED)
- Part number normalization, evidence-backed candidate search, confidence/uncertainty.
- AI cannot independently publish uncertain fitment, price, or product data.

## Phase 11 — Integrations (NOT IMPLEMENTED; PROVIDERS/SECRETS UNCONFIRMED)
- WhatsApp/outbox, supplier feed, payment and logistics adapters when credentials/providers are configured.
- Verify webhook signatures and make retries idempotent.

## Phase 12 — QA and release (DEFERRED UNTIL FEATURE COMPLETE)
- Unit/integration/E2E, RLS, accessibility, mobile/desktop, performance, security advisor, backup/restore, production smoke test.
- Final active-user production role/session tests belong here; do not block feature development on unavailable test accounts.
- A green build is not the same as verified production deployment.

## Execution order
1. Finish Phase 05 catalog lifecycle and fitment review APIs plus connect real Web/Admin UI flows.
2. Build Phase 06 supplier onboarding and offer/source evidence.
3. Build Phase 07 inventory ledger mutations, order lifecycle and payment verification.
4. Expand Phase 08 operational console and audit trail using the business APIs.
5. Complete Phase 09 customer vehicle selection, product detail, cart, checkout and tracking.
6. Add Phase 10 evidence-based AI/search.
7. Add Phase 11 provider integrations only when the real provider and credentials are configured.
8. Run the full Phase 12 release gate, including real active-user authorization sessions.

## Working policy
- Implementation commits go directly to \`main\` as requested.
- Early phases use focused checks only; broad test suites are reserved for Phase 12.
- Production changes remain additive and evidence-based; do not drop/recreate existing tables, weaken RLS, fabricate production data, or claim deployment success without verification.
- Keep the root compatibility app intact until parity and rollback are verified.
