# Phase 09 — Customer PWA

Status: IMPLEMENTED IN SOURCE; CI, deployment, and production smoke verification pending.

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
