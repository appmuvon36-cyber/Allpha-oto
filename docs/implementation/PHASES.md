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

## Phase 05 — Catalog and fitment (CLOSED: CI transactional gate and production Admin smoke verified)
- `GET /v1/catalog/products`: published-only search, category, condition, part-number, variant fitment, limit and offset filters.
- `GET /v1/vehicles/makes`, `/v1/vehicles/models`, `/v1/vehicles/variants`: active vehicle taxonomy reads.
- `GET /v1/catalog/products/{product_id}/fitments`: verified fitments only; `GET /v1/admin/catalog/fitments` exposes staff fitment review data under staff RBAC.
- `GET /v1/admin/products`: role-gated staff catalog read.
- `POST /v1/admin/catalog/mutations`: caller JWT, allowlisted lifecycle actions, required `Idempotency-Key`, safe error mapping, and one Supabase RPC for mutation plus audit in a transaction.
- `public.oto_catalog_mutate` enforces active staff profile/role, role-specific lifecycle transitions, fitment evidence for verification, and publication requirements. The audit index is unique per actor/request ID; transaction-scoped advisory locking serializes concurrent retries and replay responses mark `replayed=true`.
- Web search and vehicle selectors call FastAPI; Admin workspace includes product lifecycle and fitment action controls. Admin deployment `e4dec1a0`, Web deployment `3f25e326`, and API deployment `3f25e326` were observed SUCCESS. Public HTTP smoke checks pass; unauthenticated staff endpoints return 401 and Web-origin CORS preflight returns 200.
- Focused backend contract suite: 15 tests passed in an isolated runtime. Live schema introspection confirms mutation/audit columns, enum labels, fitment uniqueness constraint, RLS policies, and RPC execute grants. Products, fitments, audit logs, profiles and active staff profiles were all observed at zero rows.
- Additional Phase 05 remediation: fixed the Admin `update_product` payload branch; added migration source `supabase/migrations/20261018163123_phase05_idempotency_payload_binding.sql`; applied live migration `20261018163123 phase05_idempotency_payload_binding` to reject missing/invalid request IDs and bind replay to action, target ID, and JSON payload. Live introspection confirmed the guards.
- **Verified CI evidence:** OtoClinic CI run [#96](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39147327362) passed on commit `989bd92cb546613c5f659b537556281324bf6ec0`: lint, typecheck, root build, API contract checks, ephemeral PostgreSQL mutation+audit atomicity, forced audit-failure rollback, identical replay, conflicting payload rejection, missing-key rejection, and two concurrent same-key requests. The isolated Phase 05 contract/build workflow [#14](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39147327363) also passed: backend contract suite and Web/Admin typecheck+build.
- **Verified Admin deployment and HTTP smoke:** Railway deployment `96163369-988c-44a6-9e25-bf085c5350c5` SUCCESS, commit `989bd92cb546613c5f659b537556281324bf6ec0`. Production `/login`, `/admin`, and `/catalog` returned HTTP 200 (protected views showed the unauthenticated login/guard state); API `/v1/admin/products` returned 401 without a bearer token; API `/health` returned 200. No authenticated production session or production test data was used.
- Phase 05 is closed for feature progression. Real active-user role/session, RLS/IDOR, and full authenticated E2E matrix remain explicitly scheduled for Phase 12; supplier image/document rights evidence remains a Phase 06 operational workflow requirement.
- **Re-verified on latest source:** [OtoClinic CI #167](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39149787454) passed lint/typecheck/build plus the ephemeral PostgreSQL Phase 05 and Phase 06 transaction assertions on commit `e6a7b7ea5c66a7ff13ab2e40d196d9bfc8624cb1`; [contract/build #51](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39149787413) passed backend contracts and Admin/Web builds.

## Phase 06 — Supplier and sourcing (CLOSED FOR FEATURE PROGRESSION; DEPLOYMENT + PUBLIC SMOKE VERIFIED)
- Additive live migrations: `20261018170151_phase06_supplier_sourcing`, `20261018170351_phase06_supplier_rpc_actor_guards`, `20261018170609_phase06_supplier_review_read_policies`, `20261018170904_phase06_active_owner_rls_hardening`, `20261018170953_phase06_supplier_mutation_rpc_only`, `20261018171044_phase06_supplier_document_expiry_guards`, `20261018171304_phase06_offer_candidate_matching`, and `20261018171341_phase06_offer_candidate_link_mutation`. Source filenames are reconciled with the live migration ledger.
- Reuses existing `suppliers` and `supplier_offers`; adds supplier registration/verification metadata, `supplier_documents`, lead time/MOQ/warranty/source-verification fields, dedupe indexes, and a private `supplier-verification-documents` Storage bucket (PDF/JPG/PNG, 10 MB limit).
- FastAPI routes: `/v1/supplier/profile`, `/v1/supplier/onboarding`, `/v1/supplier/documents`, `/v1/supplier/offers`, `/v1/admin/suppliers`, `/v1/admin/supplier-documents`, `/v1/admin/supplier-offers`, `/v1/admin/supplier-offers/{offer_id}/candidates`, and `/v1/admin/supplier-mutations`. Admin supplier, offer, document, and audit queues use bounded limit/offset pagination; `/v1/admin/supplier-audit` exposes only safe audit metadata (no payload/PII details) and is admin-only.
- Supplier PWA route `/supplier` supports existing-account login, onboarding, private document upload, and offer submission. The API downloads each uploaded object through the caller's RLS token and verifies byte size, content type, and SHA-256 before registering document metadata. Admin route `/suppliers` supports supplier/document/offer review, signed document access, expiry/stock freshness indicators, confirmation prompts for sensitive actions, manual candidate linking, and admin-only audit metadata.
- Exact normalized SKU/part-number candidate matching is advisory only; it never links automatically and does not claim fitment. Manual linking returns the offer to `pending_review`. Supplier SKU/source URL deduplication updates an existing pending/active offer rather than creating a duplicate.
- Security: SECURITY DEFINER RPCs validate active profiles, actor/owner or staff role, idempotency key/payload, and status transitions; anon/PUBLIC execution is revoked. Direct staff table mutation policies are replaced with read-only policies; owner RLS requires an active profile. Expired documents cannot be verified or used to approve a supplier.
- **CI evidence:** [OtoClinic CI #167](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39149787454) passed on commit `e6a7b7ea5c66a7ff13ab2e40d196d9bfc8624cb1`: lint/typecheck/build, API contracts, ephemeral PostgreSQL Phase 05 atomic audit/idempotency/concurrent retry assertions, and Phase 06 onboarding/replay/conflict, document registration/review/expiry, supplier approval, offer stock timestamp/quote expiry, SKU deduplication, exact candidate matching, audited manual linking, and RPC grants. [Contract/build #51](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39149787413) also passed backend contracts and Admin/Web builds.
- **Closure evidence (19 Oct 2026):** Railway production API/Admin/Web deployments `d11daabd-0470-4e3e-8952-629767536f64`, `a8f4ce5f-9e1e-4399-a0c1-07ea9da0cb12`, and `c295d220-538d-40c7-8aab-2b89ddd4708b` are SUCCESS. API `/health` returns 200; `/v1/admin/supplier-audit` and `/v1/admin/suppliers` return 401 without a bearer token (expected); Admin `/suppliers` and Web `/supplier` return 200 and show authentication state. No production test data was inserted. Real authenticated supplier/admin session and upload tests remain in Phase 12.

## Phase 07 — Inventory and order lifecycle (CLOSED FOR FEATURE PROGRESSION; CI + RAILWAY SMOKE VERIFIED)
- Additive migrations: 20261019002354_phase07_inventory_order_lifecycle.sql, 20261019003036_phase07_reservation_expiry.sql, 20261019003253_phase07_transaction_fk_indexes.sql, 20261019003323_phase07_idempotency_rls_guard.sql, 20261019003442_phase07_checkout_address_bounds.sql, 20261019003521_phase07_shipping_fee_guard.sql, and 20261019003958_phase07_cancel_pending_payment_cleanup.sql. Existing inventory_ledger and production records were preserved.
- Atomic inventory mutations and stock balances; checkout uses row locks and stock reservations; cancellation/expiry releases reservations; shipment consumes on-hand and reserved stock in one transaction.
- Persistent cart and checkout snapshot product price, SKU, condition and quantity. Shipping fee remains server-owned and constrained to zero until a real shipping-rate provider is configured.
- Payment evidence stays pending_review until authorized verification. Cancellation of a payment-review order closes its pending payment event. Returns require review; only inspected return items selected by an operator are restocked; refund status requires an external provider reference.
- FastAPI exposes customer cart/checkout/order/payment-evidence/return routes and authorized inventory/order/payment/return operations. Customer PWA includes /cart and add-to-cart. Admin workspace includes /inventory-orders and expired-reservation release.
- CI evidence: [Phase 07 transaction gate #39182061824](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39182061824) passed the disposable PostgreSQL migration chain and transaction assertions, including rollback on audit failure, checkout replay, oversell rejection, payment review, fulfillment, return/restock, refund, and reservation expiry. [Contract/build #39182061912](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39182061912) passed API contracts and Web/Admin builds.
- Railway API/Admin/Web deployments succeeded on commit beb9cbc1648237e23a07449af175cd7209fb2ddd. Public smoke verified API health 200, protected endpoints 401 without bearer token, Web /cart 200, and Admin /inventory-orders redirect to /login for unauthenticated access. Production transaction tables remain empty; no production test data was inserted.
- Deferred gates: authenticated user-session/RLS/IDOR E2E remains Phase 12. A scheduled reservation-expiry job and actual payment/logistics provider execution are not claimed as configured. Supabase Security Advisor still reports SECURITY DEFINER warnings for privileged RPC/helper functions; no zero-warning security audit is claimed.

## Phase 08 — Super Admin (CLOSED FOR FEATURE PROGRESSION; CI + PRODUCTION SMOKE VERIFIED)
- See [Phase 08 implementation record](./PHASE_08_SUPER_ADMIN.md). Dashboard reads role-scoped metrics from FastAPI rather than querying protected tables directly from the browser; unavailable domains are null, not fake zero.
- Dashboard consolidates catalog/fitment review, supplier/offer/document review, inventory, open orders, payment review, returns/refunds, audit, and role-scoped navigation.
- Admin-only user/profile list and role/active-state controls use FastAPI and additive RPC oto_admin_set_user_role; mutation is idempotent, prevents self-change and last-active-admin removal, and atomically records audit.
- Admin-only audit explorer has safe metadata filters and bounded pagination; free-form details payload is not exposed.
- Verified: [CI #39183795427](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39183795427) and [contract/build #39183795349](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39183795349) passed; API/Admin/Web Railway deployments succeeded on commit be99226a50bc9923c37396e660195acd642e7d23. Public API auth guards and Admin login guards passed smoke checks.
- No mock production rows or invented KPI. Authenticated role changes are not executed against production without a dedicated approved test identity. Authenticated RLS/IDOR/session matrix remains Phase 12.

## Phase 09 — Customer PWA (CLOSED FOR FEATURE PROGRESSION; CI + API/WEB DEPLOYMENT + PUBLIC SMOKE VERIFIED)
- Added public `GET /v1/catalog/products/{product_id}`, restricted to published product records and returning not-found for unpublished/missing IDs.
- Added customer product detail at `/products/{productId}`, including condition, SKU/part number, package quantity, warranty, IDR price, and verified-only fitment evidence. Unknown stock is not represented as available.
- Storefront product cards link to detail; API base URL respects `NEXT_PUBLIC_API_BASE_URL`.
- Added `/account` for existing-customer sign-in, active customer profile verification, order history, and sign-out; added `/orders/{orderId}` for item snapshots, totals, shipping/tracking, payment reference review, permitted cancellation, and return request flow.
- Existing cart and checkout UI reuses Phase 07 customer APIs; all writes still go through FastAPI and the existing transactional RPC/idempotency guards.
- Service worker cache version advanced and excludes private `/account`, `/cart`, `/checkout`, `/login`, `/orders`, and `/supplier` navigations from cache. It caches only the app shell and same-origin static assets.
- No schema migration or production data mutation was required. No mock products, stock, prices, users, or orders were added.
- Focused API tests cover published detail, missing/unpublished detail, and invalid UUID. Authenticated RLS/IDOR/session E2E remains Phase 12.
- Verified CI: [OtoClinic CI #39185097017](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39185097017) and [Phase 05 contract/build #39185067815](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39185067815) passed. API deployment `71ab3e3d-42af-4cdb-9700-106ff197f516` and Web deployment `26218509-0f97-4280-b03f-2c48b2a4e919` succeeded on commit `609b4eaf848871640b0b6eb8571b0502b4901674`. Public route smoke and unauthenticated order 401 guard passed; live catalog/transaction tables remained empty.\n- Implementation and verification record: [PHASE_09_CUSTOMER_PWA.md](./PHASE_09_CUSTOMER_PWA.md).

## UI/UX Refactor — MagicPath Integration (IMPLEMENTED IN SOURCE; DEPLOYMENT/QA VERIFICATION IN PROGRESS)
- Applied the accepted MagicPath design direction to the existing Customer PWA homepage without replacing its live API behavior: category-first discovery actions submit real search terms, vehicle taxonomy remains loaded from FastAPI, product cards remain published-catalog API results, and existing cart mutations still use authenticated FastAPI calls with idempotency keys.
- Added a responsive operations navigation row to the existing Super Admin dashboard, linking to existing catalog, supplier, inventory/order, user, and audit routes; dashboard metrics and product rows remain sourced from the authorized overview API.
- Refined shared web/admin styling for mobile touch targets, scroll anchors, reduced-motion behavior, card and catalog responsiveness, and the existing OtoClinic design tokens. No new dependencies, schema migrations, production seed data, or replacement app/database were introduced.
- Source commits: `a36e4971bc97c26e28ae9d7ccb89a058c1fec46b` (customer homepage), `602326903cca57c1392f124aeab71b9bbee29d6e` (customer styles), `7ef2ef139e2b5ab8e1680cacb17f11cbb1c462da` (admin navigation), `425d031d2ac00db801087656843887e0b999e5d6` (admin styles).
- Remaining release gate: confirm CI/build for the exact source commits, deploy the web and admin services from the updated `main`, smoke-test public routes, and manually verify mobile/desktop visual behavior. Do not mark the refactor fully complete until this evidence is collected.

## UI/UX Refactor QA Gate (PARTIAL — NOT CLOSED)
- QA evidence and blockers are recorded in [UI_UX_REFACTOR_QA.md](./UI_UX_REFACTOR_QA.md).
- Production screenshots were collected for Customer Web and Admin login at 360, 390, 820, and 1440px requested viewport widths. Public route smoke confirmed customer empty states and unauthenticated Admin redirects; this is not equivalent to full interactive or authenticated E2E.
- The `/checkout` route returned 404 during smoke testing. An additive Next.js redirect was added so direct navigation routes into the existing authenticated cart/checkout flow; verify the exact deployment before considering this finding closed.
- Vehicle taxonomy and public catalog APIs return empty arrays. No production seed data was inserted, so positive-path vehicle selection and cart/checkout cannot be fully exercised with live records.
- Remaining: real browser interaction/overflow/keyboard checks at the four viewports, post-deploy checkout redirect smoke, authorized staff-role flows, approved test-customer checkout/order path, exact-commit CI/build confirmation. Phase 10 remains deferred until this gate is closed.

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
1. Phase 05 catalog lifecycle and fitment review APIs closed with verified CI and Admin smoke evidence; full active-user E2E remains Phase 12.
2. Phase 06 supplier onboarding, private document verification, sourcing offers, exact candidate matching, deduplication, and audit are closed for feature progression; authenticated session/upload E2E remains Phase 12.
3. Phase 07 inventory ledger mutations, order lifecycle, payment review, fulfillment, returns/refunds and expiry-release operation are closed for feature progression; authenticated session E2E remains Phase 12.
4. Phase 08 Super Admin Control Plane is closed for feature progression; authenticated role/RLS/IDOR E2E remains Phase 12.
5. Complete Phase 09 customer vehicle selection, product detail, cart, checkout and tracking.
6. Add Phase 10 evidence-based AI/search.
7. Add Phase 11 provider integrations only when the real provider and credentials are configured.
8. Run the full Phase 12 release gate, including real active-user authorization sessions.

## Working policy
- Implementation commits go directly to \`main\` as requested.
- Early phases use focused checks only; broad test suites are reserved for Phase 12.
- Production changes remain additive and evidence-based; do not drop/recreate existing tables, weaken RLS, fabricate production data, or claim deployment success without verification.
- Keep the root compatibility app intact until parity and rollback are verified.
