# OtoClinic — E-Commerce Completion Plan

**Status:** Owner-prioritized implementation blueprint; implementation work must be tracked against EC-01–EC-09.
**Date:** 19 October 2026
**Canonical repository:** `appmuvon36-cyber/Allpha-oto` (`main`)
**Production backend:** existing FastAPI + Supabase project `nunnugavnpaumqefmitn`
**Production apps:** Customer PWA, Super Admin, FastAPI on the existing Railway project.

## 1. Decision

Complete and verify a coherent end-to-end automotive e-commerce workflow before Phase 10 AI/search. Do not rebuild the application, introduce another database/backend, fabricate product/order data, weaken RLS, or enable provider integrations without their real credentials and verified contracts.

## 2. Baseline inspected

- Existing schema includes `products`, `product_categories`, `product_fitments`, `product_media`, `vehicle_makes/models/variants`, `suppliers`, `supplier_offers`, `inventory_ledger`, `inventory_balances`, `shopping_carts/items`, `oto_orders/items`, `inventory_reservations`, `oto_payment_events`, `oto_returns/return_items`, `oto_idempotency_records`, and `audit_logs`. All inspected public tables had RLS enabled.
- At inspection, product/vehicle/transaction/supplier tables were empty; one user profile and 26 product categories existed. Empty data is not permission to insert sample production products or orders.
- Phase 07 already supplies persistent authenticated cart, server-side checkout, price/SKU/condition snapshots, stock reservation and expiry, payment-evidence review, fulfillment, returns and refund-state primitives.
- Current cart UI creates an order through `POST /v1/checkout`, then requires the payment/order flow. It has no WhatsApp handoff in the cart source. Shipping is server-constrained to zero until a real provider is configured. Payment provider, logistics provider and WhatsApp Cloud API credentials/webhooks are not confirmed in the live Railway service variable names.
- Phase 09 and UI/UX QA documents are inconsistent about closure; the most recent production browser workflow must be treated as the source of current QA evidence. Phase 10 is explicitly not implemented.

## 3. Reference findings

1. **Astra Otoparts:** spare-part classification and filters for brand, vehicle application, and product classification. Apply this to OtoClinic's product taxonomy and vehicle fitment rather than one flat category string.
2. **Garuda Motor:** WhatsApp-assisted discovery asks customers for vehicle details and part number when fitment is uncertain. OtoClinic should keep this as a sourcing/assistance path linked to a product or request.
3. **WooCommerce WhatsApp order patterns:** cart contents and order references can be prefilled in a WhatsApp handoff, while an order remains recorded in the store/admin. The order can be initiated from product/cart/checkout and the admin can manage status.
4. **WhatsApp Business Platform:** real messaging needs server-side API credentials and webhook processing. Message handoff/opening, delivery status, customer order message and payment are distinct events.

Links:
- https://international.astraotoshop.com/product?category=Spare+Parts
- https://www.garudamotor.com/
- https://woocommerce.com/document/quick-whatsapp-chat-and-orders-for-woocommerce/
- https://woocommerce.com/products/order-on-whatsapp-for-woocommerce/
- https://github.com/fbsamples/whatsapp-api-examples

## 4. Target customer journey

Browse/filter → choose vehicle → inspect fitment evidence and condition → select product/quantity → cart → server revalidates price/stock → enter contact/address → choose delivery and payment method → server creates an order with immutable item snapshots and reservation → either:
- **Online/standard checkout:** payment intent and verified provider callback, or explicitly enabled manual payment path; or
- **WhatsApp-assisted checkout:** open a prefilled message for the already-created order reference, then await staff confirmation in the order queue.

Then: payment confirmed → picking/packing → shipment/tracking → delivery → return/refund if eligible → customer order history and audit timeline.

WhatsApp must never become the system of record. Opening WhatsApp does not prove the customer sent the message; a screenshot/message is not proof of payment; a client-submitted total never overrides the server-calculated order.

## 5. Implementation waves

- **EC-01 Storefront/product trust:** taxonomy, filters, product detail/media, fitment, conditions, stock freshness, warranty, sourcing request.
- **EC-02 Cart/checkout:** guest/auth cart merge, address/contact, price and stock revalidation, coupon validation, shipping choice/quote, order snapshot, idempotency and reservation.
- **EC-03 WhatsApp order channel:** order reference, prefilled message, channel/timeline state, staff confirmation/decline, safe expiry. Optional Cloud API/outbox/webhooks only with configured credentials.
- **EC-04 Payment lifecycle:** manual review or configured provider, payment intent/events, signature-verified webhook, replay protection, reconciliation, refunds.
- **EC-05 Delivery/fulfillment:** shipping address book, serviceability, quotes, courier/service, shipment/tracking events, failed delivery and return paths.
- **EC-06 Commercial/customer lifecycle:** coupons, campaigns, price rules, wishlist, saved vehicles, reorder, notifications and sourcing.
- **EC-07 Admin operations:** unified order queue, channel/timeline, payment, inventory reservation, fulfillment, exception handling, returns/refunds, audit and real metrics.
- **EC-08 Integration reliability:** outbox, retries/dead letters, WhatsApp/payment/logistics adapters, provider status logs and reconciliation.
- **EC-09 Acceptance/release gate:** CI, migration/RLS inspection, transaction/security tests, responsive browser QA, exact-commit deployment and rollback evidence.

Acceptance details and sequencing are maintained in `docs/implementation/PHASES.md`.

## 6. Non-negotiable implementation contracts

- FastAPI is the write authority; browser clients must not write privileged commerce tables directly.
- Existing Supabase project and tables are canonical. Additive, reviewed migrations only; inspect live constraints, functions, triggers, grants, RLS and migration ledger before DDL.
- Product SKU, price, fitment, stock, shipping and totals are validated server-side. Inventory uses atomic ledger/reservation transitions and idempotency.
- Payment is paid only after verified provider confirmation or authorized reconciliation; uploaded evidence stays pending review.
- WhatsApp handoff and true Cloud API messaging are separate capability levels; do not advertise delivery or automated notification unless it is configured and verified.
- Do not present a shipping fee of zero as a real carrier quote. Use a clearly labeled pending/manual quote until a provider or approved policy exists.
- No production test order or fake product is created for QA. Authenticated role/session E2E requires approved test identities and remains part of Phase 12.
- Each wave reports changed files, migrations/RLS, API contracts, tests, commit SHA, CI runs, Railway deployment IDs, health/smoke evidence, blockers and next wave.

## 7. Provider activation gates

Before enabling real integrations, confirm the provider account, production credentials, callback URLs, signature verification, retry/idempotency contract, data retention, operator workflow and reconciliation procedure. Secrets remain in server-side Railway variables only. Until these conditions are met, expose a safe disabled/unavailable state rather than fake success.

## 8. Immediate implementation order

Start with EC-01/EC-02 gap analysis and customer/admin workflow mapping; then implement EC-03 WhatsApp handoff as a recorded order channel, while payment and logistics adapter contracts are prepared. Close EC-09 before starting Phase 10 AI/search.
## 10. EC-01 implementation log — 19 October 2026

**State: Core implementation deployed to production; read-only responsive browser QA passed for layout and catalog states. EC-01 remains OPEN for authenticated sourcing integration and real inventory/product detail acceptance.**

- Storefront: responsive navy/orange hero and CTA; mobile-first catalog search controls for name/brand, part number, condition, vehicle fitment and category.
- Hierarchical categories: the customer UI shows active root categories and child navigation; selecting a parent filters products in that category and all active descendants. The backend resolves descendants from the active category master and filters published products by their category names. Existing product schema stores category as text, so a future additive category-ID migration may be considered only after compatibility mapping is proven.
- Public stock status: additive migration adds public.oto_public_stock_status(uuid[]), returning only status and timestamp for published products, never raw inventory quantities. States are in stock, low stock, out of stock, stale (older than 24 hours), or unverified. The public function is granted to anon/authenticated; inventory table RLS and grants remain unchanged.
- Sourcing requests: additive public.sourcing_requests table with customer ownership, idempotency key, part/vehicle details, quantity, optional contact phone, status and timestamps. RLS is enabled; customers can insert/read their own requests, while authorized staff roles can read the operational queue. FastAPI validates the active customer identity and Idempotency-Key; no guest or anonymous mutation is exposed.
- Product detail: approved media gallery, SKU, condition, package quantity, warranty, part number, verified fitments/evidence, inventory-backed status and sourcing CTA. Cart action is offered only when stock status is in-stock or low-stock; otherwise the UI explains the status and directs customers to sourcing.
- Automated tests: backend contract tests cover descendant category filtering through the restricted public category RPC, unknown stock remaining unverified, sourcing idempotency header, customer identity forwarding, and rejection of non-customer roles. GitHub Actions run 39209722545 on commit b7e42e50854b6f3af73a2094d751b9319df8cbfb completed the backend contract job SUCCESS and Web typecheck/build SUCCESS; the overall workflow still had an unrelated admin-build job in progress at the last check. This is not a substitute for authenticated sourcing/RLS integration testing.
- Live Supabase verification: sourcing_requests exists with RLS enabled and three policies; oto_public_stock_status(uuid[]) exists. Live product, fitment, inventory-balance, and inventory-ledger counts at inspection were 0; no product or request rows were fabricated.
- Production deployment: existing Web service is live on deployment 98bc190b-be33-446c-950f-231557198d80, commit 68d9f6d4464454caf998ef2d69d5dd917bb0b648. Existing API service is live on deployment d06ac371-2145-4c5b-92c8-930d580f7fcd, commit b7e42e50854b6f3af73a2094d751b9319df8cbfb. The unrelated Admin service was not redeployed.
- Browser QA used the live browser connector at 360×800, 390×844, 820×1000, and 1440×1000. At all four sizes, document width equaled client width (no horizontal overflow), the hero/category/sourcing sections were present, eight sourcing inputs were rendered, and no browser page errors were observed. The live catalog correctly displays its real empty state and no loading skeleton after load.
- The live browser initially found that public category reads failed under the existing REST/RLS path (503), which blocked the category tree. An additive restricted SECURITY DEFINER RPC, public.oto_public_product_categories(), now returns only active category metadata; the public category endpoint returns HTTP 200. Parent category selection was verified to send category_id to the live catalog API and return HTTP 200 after the descendant query was switched to the same RPC. No order/payment/request was submitted.
- Live catalog still contains zero published products and the 26 active category rows currently all have parent_id = null. Therefore the hierarchy/filter implementation is present, but no child relationship exists in production data to validate a parent-with-subcategories view. Product gallery, stock badge, condition, warranty and verified fitment cannot be acceptance-tested against a real published product until the catalog contains an approved real product. Do not create fake products or fake inventory to fill this gap.
- The public sourcing GET route now exists and returns HTTP 401 without a bearer token, as expected. No approved authenticated test identity was available for creating and reading a request, so ownership/insert behavior remains unverified end-to-end. Anonymous inventory table reads remain denied; the public stock RPC exists and exposes status/timestamp only.
- No new Railway service/database was created, no destructive deployment action was run, and no real customer transaction was performed.

### EC-01 acceptance remaining

1. Create/verify approved real child categories through the existing admin taxonomy workflow; do not invent category/product rows. Then validate parent/child navigation and descendant filtering against that live hierarchy.
2. Provision an explicitly approved non-production customer test identity and verify sourcing create/read/ownership/idempotent replay through authenticated API calls. Do not create a real customer request or order.
3. Publish at least one legitimately reviewed product with approved media, condition, warranty, part number, verified fitment evidence, and authoritative inventory; then repeat read-only product detail and stock-state QA. Until that data exists, these product-state acceptance criteria remain blocked by empty production data.
4. Extend the browser QA to validate search/filter response and keyboard/navigation states, and capture the product-detail route after a real product is available.
5. Mark EC-01 closed only when the remaining data-dependent and authenticated acceptance checks have evidence. Then proceed to EC-02 (cart and checkout); keep Phase 10 AI deferred.


## 11. EC-02 implementation log — 19 October 2026

**State: implementation started; no real customer transaction or production checkout was executed.**

- Checkout now derives its item list exclusively from the authenticated customer's persisted `shopping_carts` and `shopping_cart_items` records. Client-supplied `items` are rejected by request validation, so a caller cannot substitute arbitrary product IDs or quantities through the checkout body.
- The API normalizes the persisted cart item IDs and quantities and rejects duplicate IDs or invalid quantity bounds before calling the existing transactional `oto_order_mutate` RPC. The RPC remains responsible for canonical price/stock revalidation, order-item snapshots, inventory reservation, cart clearing, idempotency, and audit writes.
- Added a contract test for rejecting client-supplied checkout items and updated the unauthenticated checkout contract to use the supported request shape.
- No schema migration was needed for this change. Existing tables, RLS, the transactional RPC and production data were preserved.
- No real checkout, payment, inventory mutation, or test order was executed. CI evidence must be recorded only after the workflow for the resulting commit completes.
- Known remaining EC-02 scope: a real shipping quote/policy and coupon rules are not configured. The UI must not imply that `Rp0` is a carrier quote; checkout should remain explicit that the displayed total excludes an authoritative shipping quote. Guest-to-authenticated cart merge is also not implemented yet.
