# MASTER PRD — OtoClinic
## AI Automotive Spare Parts Commerce Indonesia

**Versi:** 1.1 · **Tanggal:** 18 Oktober 2026 · **Status:** Canonical implementation blueprint  
**Brand:** OtoClinic · **Pasar awal:** Indonesia · **Bahasa:** Bahasa Indonesia · **Mata uang:** IDR

> Dokumen ini adalah sumber kebutuhan produk dan penerimaan. Ia bukan klaim bahwa semua fitur telah diimplementasikan. Seluruh status harus dibuktikan melalui source, schema live, API, UI, dan pengujian produksi.

## 1. Visi dan nilai
OtoClinic membantu pelanggan, bengkel, pemasok, dan tim operasional menemukan, memverifikasi, membeli, dan memenuhi kebutuhan suku cadang mobil/motor. Platform mengutamakan kecocokan kendaraan yang dapat dibuktikan, kondisi barang yang transparan, ketersediaan yang memiliki timestamp, dan alur sourcing untuk part yang belum tersedia.

**Pelanggan:** pencarian berdasarkan nama/nomor part/kendaraan/foto, informasi kondisi dan garansi, permintaan sourcing, checkout, pembayaran, dan pelacakan.  
**Operasional:** pengelolaan katalog, fitment, supplier, penawaran, inventori, pesanan, pembayaran, moderasi, dan audit.  
**Pemasok:** verifikasi, penawaran, bukti sumber, stok bertanggal, masa berlaku penawaran, dan performa.

## 2. Prinsip non-negotiable
1. PostgreSQL/Supabase dan API adalah sumber kebenaran; UI bukan otoritas transaksi.
2. Tidak ada data mock yang ditampilkan sebagai data produksi.
3. AI memberi saran, bukan keputusan final untuk fitment, harga, stok, pembayaran, atau akses.
4. Setiap klaim fitment perlu bukti, status, dan proses review.
5. Kondisi produk harus jelas: baru OEM, baru aftermarket, bekas/copotan, refurbished/rekondisi, remanufactured, atau rusak untuk part.
6. Stok dan penawaran memiliki asal dan waktu verifikasi.
7. Operasi sensitif membutuhkan otorisasi server-side, idempotensi bila relevan, dan audit trail.
8. Perubahan schema live bersifat additive dan dapat di-rollback; tidak ada reset database.
9. UI harus menyampaikan loading, empty, error, success, offline, dan permission-denied secara eksplisit.
10. Build hijau bukan bukti integrasi atau keamanan sudah lulus.

## 3. Arsitektur kanonis dan lingkungan
Repository: https://github.com/appmuvon36-cyber/Allpha-oto  
Supabase project: https://supabase.com/dashboard/project/nunnugavnpaumqefmitn  
Supabase URL: `https://nunnugavnpaumqefmitn.supabase.co`  
Railway project: https://railway.com/project/ff2625be-254a-4243-bf00-ed99080fd537  
Customer: https://otoclinic-web-production.up.railway.app  
Admin: https://otoclinic-admin-production.up.railway.app  
API: https://otoclinic-api-production.up.railway.app

```text
Allpha-oto/
├── apps/web/        # Next.js + TypeScript + Tailwind, customer PWA
├── apps/admin/      # Next.js + TypeScript + Tailwind, Super Admin
├── backend/         # Python FastAPI, authz and business rules
├── supabase/        # migrations/config for existing Supabase project
├── docs/prd/MASTER_PRD.md
├── docs/design-system/
├── docs/architecture/
├── docs/implementation/
├── .github/workflows/
└── AGENTS.md
```

Railway deploys one repo/branch to three services using root directories `/apps/web`, `/apps/admin`, `/backend`. Keep the existing root app as compatibility fallback until migration parity is proven. Do not create new repositories, projects, or databases.

## 4. Roles and authorization
Roles in current database enum `oto_user_role`: `customer`, `supplier`, `catalog_editor`, `inventory_manager`, `order_manager`, `moderator`, `admin`. Roles must be assigned through a trusted process. A browser-side profile check is a UX guard only; every protected API request and every database query must be protected by verified JWT, backend authorization, and/or RLS.

- Customer: public published catalog and own account/orders.
- Supplier: own profile/offers and only explicitly authorized supplier workflows.
- Catalog editor: draft/review/catalog edits according to permission.
- Inventory manager: inventory workflows only.
- Order manager: orders/fulfillment/payment workflows only.
- Moderator: moderation queues and permitted review actions.
- Admin: full authorized operations and governance.
- Anonymous: only explicitly public read operations, never private data or mutations.

Never create a public admin signup. Login errors should not disclose whether an email exists. Admin pages must show a safe denial state when the role is missing/inactive.

## 5. Current live data baseline
The existing Supabase project already has the following public tables, all observed with RLS enabled:
- `user_profiles` — profile linked to `auth.users`, role and active flag.
- `vehicle_makes`, `vehicle_models`, `vehicle_variants` — vehicle taxonomy.
- `products` — SKU, name, condition, lifecycle status, IDR retail price and metadata.
- `product_fitments` — product-to-vehicle compatibility and evidence/review status.
- `suppliers`, `supplier_offers` — suppliers and sourced offers.
- `inventory_ledger` — immutable-style inventory movement records.
- `audit_logs` — actor/action/entity audit data.

Observed migrations: `20261018135537_otoclinic_foundation_catalog_fitment` and `20261018135625_otoclinic_revoke_public_rls_helper`. Existing rows observed were zero in the listed tables at the time of audit; this is not permission to seed fake production data. Before any schema changes, re-inspect current schema, RLS, grants, functions, triggers, Storage and advisor findings.

## 6. Required product modules
### Customer PWA
- Homepage with exact/partial part search, vehicle selector, category navigation.
- Search by name, SKU/OEM/part number, brand, synonym, and vehicle.
- Fitment detail with compatible make/model/variant/year/engine, evidence, status and confidence.
- Product detail: part number, condition, package quantity, warranty, seller/source, stock freshness, price, shipping and returns.
- Sourcing request for unavailable/rare parts, with vehicle and part details and optional user-owned photos.
- Cart, checkout, payment instructions/evidence, order status, cancellation/return flow.
- Customer profile, addresses and order history.
- Installable mobile-first PWA; cache app shell only, not private orders/payment content.

### Super Admin
- Secure sign-in, session recovery, logout, role/permission-denied screens.
- Operational overview derived from real authorized queries; no fabricated KPI.
- Catalog lifecycle: draft → review → approved → published → archived/rejected.
- Vehicle taxonomy and fitment evidence/review.
- Supplier onboarding, document review, offers, stock freshness and quote expiry.
- Inventory ledger, stock adjustments with reason and audit.
- Order, payment verification, fulfillment, return/refund, and exception queues.
- User/role administration through authorized workflows.
- Audit log, search/filter, pagination, clear action confirmation.
- All privileged mutations must use FastAPI or strictly authorized database RPCs; no client-side service role.

### Backend API
- Versioned FastAPI routes, Pydantic request/response models, typed errors.
- Server-side Supabase/JWT verification and role authorization.
- Central business rules, transactional operations, idempotency keys where retries can duplicate actions.
- Audit actor, action, entity, request/correlation ID, timestamp.
- Rate limits and request-size limits on sensitive/public endpoints.
- OpenAPI docs, structured logs without credentials/PII leakage, readiness/health endpoints.
- Provider adapters (payments, logistics, WhatsApp, AI/search) remain disabled until credentials and webhook verification are configured.

## 7. Data and business rules
- Product SKU and slug are unique; prices/quantities cannot be negative.
- Currency is IDR for the initial market.
- Product cannot be published before required metadata, source rights, price, condition, and review gates pass.
- Fitment must have a supported status; unverified fitment cannot be worded as confirmed.
- Supplier offer needs source evidence, price/condition, stock quantity and checked timestamp; expired/unknown offers are not presented as current stock.
- Inventory mutations are recorded in ledger and executed atomically. Never overwrite inventory history to correct it; append a correcting movement.
- A payment screenshot is evidence, not proof of payment. Payment status changes only after authorized verification/provider confirmation.
- AI-generated candidate matching must include uncertainty/evidence and cannot auto-publish high-risk claims.
- Customer PII is purpose-limited, protected by access control, and never placed in public logs.

## 8. API contract principles
- Keep business logic in `backend/`; frontend cannot bypass it for privileged actions.
- Public catalog endpoints return only published, policy-allowed fields.
- Admin endpoints require valid authentication plus role/permission on every request.
- Mutations validate IDs, enums, ranges, state transitions, ownership and concurrency.
- Use consistent error envelope with machine code, safe message, request ID.
- CORS allowlist must contain only known production/dev origins.
- Never expose Supabase service-role key or database password to `apps/web` or `apps/admin`.
- Health response is minimal; no environment values, stack traces or secret details.

## 9. UI/UX system — plugin artifacts and design rules
MagicPath project: **Allpha Oto — Premium Spare Parts UI/UX**, project ID `462564795376340992`. Components:
- Customer Homepage & Smart Parts Finder — `friendly-ocean-4932`
- Super Admin Operations Dashboard — `bold-air-1063`
- Design System Foundations — `dreamily-park-9006`
See `docs/design-system/MAGICPATH_UI_UX.md` and `docs/design-system/FOUNDATIONS.md`.

Design language: minimal, professional, mobile-first, high readability, low visual noise, no decorative heavy gradients. Brand colors: navy `#101B2B`, action orange `#EF5B2A`, canvas `#F5F6F8`, white surfaces, border `#E2E8F0`, success `#047857`, warning `#B45309`, danger `#B91C1C`. Base spacing 4px, body 14–16px, page titles 28–36px, interactive target 40–44px. Keep keyboard focus visible and semantic status labels visible without relying on color alone.

Customer design should prioritize vehicle selection, search, fitment evidence, condition, warranty, freshness, and sourcing. Admin design should prioritize scanning, filters, review queues, data tables, clear permission states, and auditability. The MagicPath customer component currently contains illustrative product examples; they MUST be replaced with real API/database data or explicitly labelled prototype-only before public launch. Do not copy generated UI code blindly: review dependencies, accessibility, responsive behavior, data binding and security.

## 10. Non-functional requirements
- Performance: optimized images, paginated queries, bounded response payloads, avoid N+1 access.
- Accessibility: keyboard, labels, semantic HTML, contrast, reduced motion and clear validation.
- Reliability: idempotent retries, bounded timeouts, actionable errors, backups and tested recovery.
- Observability: request IDs, API latency/error rate, deployment logs, security alerts and audit trail.
- Privacy/security: least privilege, RLS, secure cookies/session handling where applicable, secret management and dependency review.
- Maintainability: type checking, lint, unit/integration/E2E tests, migration review and documented API contracts.

## 11. Implementation sequence
1. **Baseline audit:** read PRD, inspect repository and live production; map differences.
2. **Supabase:** additive migrations, indexes/constraints, RLS/grants, functions and Storage policies; verify anon/user/role test matrix.
3. **FastAPI:** auth/JWT validation, authorization, schemas, catalog/fitment/supplier/inventory/order workflows, idempotency and audit.
4. **Customer PWA:** connect UI to real API, search/vehicle/fitment/product/sourcing/cart/order and customer auth.
5. **Super Admin:** auth gate, role verification, real operational queries, workflow actions through API, audit visibility.
6. **Integrations:** payment, logistics, WhatsApp, AI only after secrets, callbacks and tests are ready.
7. **Production QA:** direct route HTTP checks, unauthenticated and authenticated tests, RLS/IDOR tests, accessibility, mobile/desktop, logs, rollback and health.
8. **Release:** deploy one service at a time; verify the new deployment before retiring any previous deployment.

## 12. Acceptance criteria / Definition of Done
A feature is done only when all applicable conditions pass:
- Requirement traced to this PRD and an implementation phase.
- Migration is additive, reviewed and applied to the existing project; schema and RLS re-inspected.
- API contract, authz, error handling and tests are complete.
- UI uses real API data, with loading/empty/error/permission states.
- Admin data is never returned to anonymous/unauthorized users.
- No service-role secret is in client code/build output.
- Lint/typecheck/unit/integration/E2E and accessibility checks pass.
- Direct HTTP checks include `/`, `/login`, `/admin`, and `/health`; include unauthenticated and authorized flows where applicable.
- Deployment ID/commit, health checks, logs, and rollback path are recorded.
- No fake data, unsupported success claims, or unexplained production schema changes.

## 13. Open blockers / decisions
- Confirm Supabase RLS policy coverage and user_profiles self-read/role administration.
- Ensure all production apps have required environment variables; only publishable keys in browser builds.
- Implement server-side FastAPI JWT/role enforcement before enabling privileged write operations.
- Validate live direct HTTP responses and E2E auth flows after the environment-triggered deployments.
- Replace prototype product cards with real catalog queries and truthful empty states.
- Confirm CORS origins and any future payment/logistics/WhatsApp credentials before activating those integrations.

## Appendix — current production routes
- Customer: `/` — https://otoclinic-web-production.up.railway.app/
- Admin login: `/login` — https://otoclinic-admin-production.up.railway.app/login
- Admin dashboard: `/admin` — https://otoclinic-admin-production.up.railway.app/admin
- API health: `/health` — https://otoclinic-api-production.up.railway.app/health
- API docs: `/docs` — https://otoclinic-api-production.up.railway.app/docs
