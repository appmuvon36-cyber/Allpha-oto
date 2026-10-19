# Phase 09 — Customer PWA

Status: CLOSED FOR FEATURE PROGRESSION — CI, API/Web deployment, and public smoke checks verified. Authenticated session/RLS/IDOR E2E remains Phase 12.

## Scope delivered
- Public product detail endpoint `GET /v1/catalog/products/{product_id}`. It selects only published products and returns 404 for missing/unpublished records; Supabase public-read RLS remains the database boundary.
- Product detail page at `/products/{productId}`: published catalog fields, IDR price when available, product condition/grade, package quantity, warranty, fitment summary, and only verified fitment evidence from the existing fitment endpoint. No stock quantity is invented; availability is explicitly reconfirmed at checkout.
- Storefront product cards link to product details and use `NEXT_PUBLIC_API_BASE_URL` with the canonical API as a fallback.
- Customer account page at `/account`: existing-account sign-in only, verifies the session/profile through FastAPI, lists the caller's orders, and links to order tracking. No public admin/supplier registration was added.
- Order detail page at `/orders/{orderId}`: calls the owner-scoped customer order API, shows item snapshots, totals, shipping address, payment review state, tracking timestamps/code, cancellation where permitted, and return request where the server allows it. Payment evidence remains pending review until an authorized workflow verifies it.
- Existing cart/checkout implementation remains wired to Phase 07 APIs; price, shipping address bounds, stock reservation, payment evidence, cancellation and return mutations remain server/database controlled.
- PWA service worker caches only the app shell and same-origin static assets; API responses and private order/payment data are not cached.

## Security and data integrity
- No schema migration was required; Phase 07 transaction tables and RPCs are reused.
- Browser code uses Supabase public/anon configuration only and sends caller access tokens to FastAPI. It never receives service-role credentials.
- No fake catalog rows, prices, stock, users, orders or payment states were added.
- Missing/unpublished products return not-found; empty fitments are presented as unverified, not as confirmed compatibility.
- Authenticated RLS/IDOR/session E2E remains in Phase 12 and was not represented as completed here.

## Verification plan
- API contract tests for product detail success, missing/unpublished product, and invalid UUID.
- Web lint, TypeScript, build, backend contract suite, and existing Phase 05–08 database assertions in CI.
- After CI passes, deploy the existing API and Customer Web services from canonical `main`, then smoke-test product detail route contract, unauthenticated private order access, PWA home/account/order routes, and confirm the live data baseline is unchanged.

## Verified evidence — 19 October 2026

- OtoClinic CI [#39185097017](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39185097017) completed successfully. Web lint/typecheck/build and API contract plus disposable PostgreSQL Phase 05–08 transactional assertions passed.
- Phase 05 contract/build workflow [#39185067815](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39185067815) passed Web/Admin build/typecheck and the backend contract suite, including Phase 09 product-detail contracts.
- Runtime commit: `609b4eaf848871640b0b6eb8571b0502b4901674`.
- Railway API deployment `71ab3e3d-42af-4cdb-9700-106ff197f516` SUCCESS; Customer Web deployment `26218509-0f97-4280-b03f-2c48b2a4e919` SUCCESS. Existing service IDs and root directories were preserved; both services use the canonical repository and `main`.
- Public HTTP smoke: `/`, `/account`, `/cart`, `/products/{id}`, and `/orders/{id}` returned HTTP 200. A non-existent product detail API returned 404; malformed product UUID returned 422; private `GET /v1/orders?limit=1` without bearer token returned 401; API `/health` returned 200.
- Service worker `/sw.js` returned HTTP 200 and contains the `otoclinic-shell-v2` cache with explicit private-route exclusions.
- Live row counts at verification: `products=0`, `product_fitments=0`, `vehicle_makes=0`, `vehicle_models=0`, `vehicle_variants=0`, `inventory_balances=0`, `shopping_carts=0`, `shopping_cart_items=0`, `oto_orders=0`, `oto_order_items=0`, `oto_payment_events=0`, `oto_returns=0`. No production test rows were inserted.
- No database migration was needed. Real authenticated customer sessions and ownership/IDOR matrix remain reserved for Phase 12; this phase does not claim those tests passed.
