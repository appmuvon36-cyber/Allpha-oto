# Phase 07 — Inventory & Order Lifecycle

Status: implemented in the canonical source and additive migration applied to the existing Supabase project; CI and deployment gates are pending.

## Existing baseline and migration

- Reuses the existing public.inventory_ledger; does not drop, rename, reset or recreate existing business tables.
- Migration: supabase/migrations/20261019002354_phase07_inventory_order_lifecycle.sql.
- New tables: inventory_balances, shopping_carts, shopping_cart_items, oto_orders, oto_order_items, inventory_reservations, oto_payment_events, oto_returns, oto_return_items, and oto_idempotency_records.
- Prices and product details are snapshotted to oto_order_items at checkout. Currency is constrained to IDR.
- RLS is enabled for every new table. Direct client writes to the transactional tables are revoked; mutations must use the authenticated FastAPI → PostgreSQL RPC path.

## Transaction invariants

1. Available stock is on_hand - reserved; it cannot be negative.
2. Checkout locks inventory balance rows in product-id order and reserves stock in the same database transaction as the order, item snapshots, ledger entries and audit event.
3. A failed checkout rolls back the order and all reservations.
4. A retry with the same actor, idempotency key and payload replays the original result; a conflicting payload is rejected.
5. Cancellation before fulfillment releases reserved stock and writes ledger entries.
6. Shipment consumes both on-hand and reserved quantities atomically; the inventory ledger records the sale.
7. Payment evidence is pending_review. It never marks an order paid by itself. Authorized order_manager/admin must verify the payment with a provider/bank reference or verification note.
8. Returned items are not automatically restocked. The operator selects inspected items for restock when recording physical receipt.
9. Refund state is recorded only when a refund provider reference is supplied. This RPC does not itself move money or call a payment provider.

## API contract

### Customer
- GET /v1/cart
- POST /v1/cart/mutations (cart_add, cart_set_quantity, cart_remove, cart_clear)
- POST /v1/checkout
- GET /v1/orders, GET /v1/orders/{order_id}
- POST /v1/orders/{order_id}/payment-evidence
- POST /v1/orders/{order_id}/cancel
- POST /v1/orders/{order_id}/returns

### Inventory operations
- GET /v1/admin/inventory
- GET /v1/admin/inventory/ledger
- POST /v1/admin/inventory/mutations (receipt, adjustment_increase, adjustment_decrease, write_off)

### Order operations
- GET /v1/admin/orders
- GET /v1/admin/payments
- GET /v1/admin/returns
- POST /v1/admin/orders/{order_id}/mutations (verify_payment, reject_payment, cancel_order, start_fulfillment, mark_shipped, mark_delivered, approve_return, reject_return, receive_return, record_refund)

All mutating endpoints require Idempotency-Key, an active authenticated profile and role-specific authorization. PostgreSQL validates the role again inside the RPC.

## UI surfaces

- Customer: /cart, login for an existing active customer account, product add-to-cart, quantity/remove controls, checkout address, order history, payment-evidence submission and cancellation.
- Super Admin: /inventory-orders, inventory balances and ledger, stock adjustment form, order lifecycle controls, pending payment review and requested returns.
- UI does not use demo products, fake balances or fabricated orders; empty states remain empty when the database has no approved records.

## Verification gates

- backend/tests/test_phase07_contracts.py: API route presence and unauthenticated request rejection.
- backend/tests/phase07_db_assertions.sql: disposable PostgreSQL end-to-end transaction checks for receipt, checkout, idempotent replay, oversell rejection, payment review/verification, fulfillment, inspected return restock, refund record and audit.
- .github/workflows/ci.yml applies Phase 07 migration only to the disposable CI database and runs the assertions.
- Production migration was applied to the canonical Supabase project; current production data is not used as test fixtures.
- Final closure still requires CI success, successful Railway deployment of API/Web/Admin, public HTTP smoke, and authenticated user/role/RLS/IDOR tests in Phase 12.

## Known scope boundary

Provider-backed payment initiation/webhooks and actual refund execution, shipment-provider labels/tracking webhooks, shipping-price calculation, reservation-expiry worker, and production user-session matrix are not claimed as complete. They require Phase 11 provider configuration and Phase 12 release verification.
