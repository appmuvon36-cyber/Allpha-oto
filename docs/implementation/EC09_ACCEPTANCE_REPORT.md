# EC-09 — Commerce Acceptance Gate Report

**Scope:** OtoClinic commerce transaction integrity and security acceptance.  
**Repository:** `appmuvon36-cyber/Allpha-oto`, branch `main`.  
**Database:** Existing Supabase project only; synthetic test identities/rows are created exclusively by the disposable CI PostgreSQL fixture.  
**Status:** CI acceptance coverage passed on source commit `e257b779b3c0be58560dc25e7cc587749bda7418` (run 39533480729); the additive payment replay guard is applied to the existing Supabase production project. The three Railway services remain online, but API production is still running the earlier EC-08 commit `573088ae2d4211348550d32f4b1de87def17bc55`; Railway rejected the source refresh with “Deploys have been paused temporarily.” The database-side replay/conflict guard is live through the applied Supabase migration; the API-side pre-validation for provider-order/event key length is not yet deployed. Database-level key bounds remain enforced. External-provider checks are explicitly configuration-gated.

## Acceptance matrix

| Area | Evidence in repository/CI | Acceptance condition | Status interpretation |
|---|---|---|---|
| Payment webhook authenticity | `backend/tests/test_ec09_acceptance.py` | Invalid HMAC returns 401 and never calls the payment mutation; oversized payload returns 413; missing secret returns 503 | CI-verifiable without provider credentials |
| Payment event replay | `backend/tests/ec09_acceptance_assertions.sql` | Same key + same digest/status returns replay; same key with a different digest/status is rejected | Disposable-DB transaction test |
| Payment amount and status | EC-09 SQL assertions + API contracts | Amount mismatch is rejected; unknown status and paid-without-amount are rejected | CI-verifiable; real provider remains separate |
| Monotonic payment state | EC-09 SQL assertions | Late pending callback cannot downgrade settlement/order-paid state | Disposable-DB transaction test |
| Checkout replay and oversell | `backend/tests/phase07_db_assertions.sql` | Same request does not duplicate order; insufficient stock creates no order | Existing disposable-DB test |
| Concurrent stock reservation | `backend/tests/ec09_concurrent_checkout_a.sql`, `_b.sql`, `ec09_concurrency_assertions.sql` | Two concurrent checkouts compete for five units; exactly one four-unit reservation/order succeeds | CI concurrency test |
| Shipping quote integrity/expiry | `backend/tests/ec02_shipping_quote_assertions.sql` | Tampered signature, expired quote, or quote replay by another customer is rejected | Existing disposable-DB test |
| Return/refund guard | `backend/tests/phase07_db_assertions.sql` | Return is approved/received before refund recording; inventory and audit trail remain consistent | Existing disposable-DB transaction test |
| Retry/dead-letter and delivery replay | `backend/tests/ec08_db_assertions.sql` | Retry exhaustion dead-letters; duplicate WhatsApp delivery callback is idempotent; worker RPC is service-role-only | Existing disposable-DB test |
| RBAC and grants | EC-09 API tests + EC-08/Phase 07 SQL assertions | Unauthenticated API requests return 401; wrong role returns 403; mutation/worker RPCs are not executable by anon | CI-verifiable |
| RLS | EC-09/EC-08 SQL assertions | RLS remains enabled on commerce/payment/integration tables; privileged operations use guarded RPCs | Disposable-DB assertions |
| WhatsApp provider delivery | Railway configuration inventory | Cloud API token, phone-number ID, Graph API version, approved template, webhook verify token, Meta app secret and worker secret are required | **BLOCKED** until configured |
| Authenticated production customer/staff journey | Approved test accounts and safe test order/payment path | Run customer checkout and authorized staff workflows without production test contamination | **DEFERRED** to Phase 12 / approved test identity |
| Production release | [OtoClinic CI run 39533480729](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39533480729) on `e257b779b3c0be58560dc25e7cc587749bda7418`; fresh API health smoke returned HTTP 200 before the source refresh attempt | Isolated API/DB acceptance and web lint/typecheck/build passed; production API source refresh was attempted but Railway paused deployments | **Code/DB checks passed; API deployment pending.** Current Railway API deployment `c395881e-3eb6-4f12-92df-681cd69f2fee` still reports commit `573088ae2d4211348550d32f4b1de87def17bc55`. |

## Change and rollback notes

- Additive migration: `supabase/migrations/20261021022911_ec09_payment_webhook_replay_guards.sql`.
- The migration replaces the existing `oto_payment_webhook_apply` function, preserves service-role-only execution, and does not delete, truncate, or rewrite existing commerce rows.
- Rollback must be a reviewed forward migration restoring the previous function definition if needed; do not drop payment webhook events or roll back the migration ledger. The prior definition is preserved in Git history at the parent commit.
- Live Supabase verification after applying the migration: `payment_webhook_event_payload_conflict` guard is present; `service_role` can execute the RPC; `authenticated` cannot. Production counts remained `oto_orders=0`, `oto_payment_intents=0`, `oto_payment_webhook_events=0`, and `oto_returns=0`.
- Production data was not seeded with acceptance orders, payment intents, refunds, webhook events, or fake catalog rows.
- CI passing proves only the listed isolated checks. It does not prove external provider delivery or an authenticated live production transaction.
