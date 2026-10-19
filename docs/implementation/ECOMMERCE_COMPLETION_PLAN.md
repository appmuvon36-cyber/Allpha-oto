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
