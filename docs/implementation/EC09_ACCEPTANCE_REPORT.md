# EC-09 — Commerce Acceptance Gate Report

**Scope:** OtoClinic commerce transaction integrity and security acceptance.  
**Repository:** `appmuvon36-cyber/Allpha-oto`, branch `main`.  
**Database:** Existing Supabase project only; synthetic test identities/rows are created exclusively by the disposable CI PostgreSQL fixture.  
**Status:** EC-09 is **CLOSED FOR PHASE PROGRESSION BY EXPLICIT OWNER WAIVER (21 Oct 2026)**. CI run [39533480729](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39533480729) passed on code commit `e257b779b3c0be58560dc25e7cc587749bda7418`; the additive payment replay guard is applied to the existing Supabase project with service-role-only execution. Railway API deployment `7639d819-b995-4b33-88cc-4a82ed624beb` reached `SUCCESS` on `main`, commit `df888d72955d8d629afabc24b2c6554cdbb9b61d`, root `/backend`. Post-deploy read-only HTTP smoke returned `/health` 200, `/ready` 200, public catalog 200, and unauthenticated admin/orders 401.

**Owner waiver and remaining boundary:** The owner explicitly instructed that further real production testing be skipped so work can proceed to Phase 10. Authenticated production checkout/payment/return/refund journeys are **deferred to Phase 12**, not marked as passed. This phase exit is an administrative acceptance for progression, not a claim that live financial transactions or provider delivery were verified. No production test orders, payment intents, webhook events, returns, refunds, or fake catalog rows were created.

**WhatsApp scope clarification:** EC-03 checkout handoff is a prefilled `wa.me/` link that opens the customer's WhatsApp app. This does not require WhatsApp Cloud API credentials, templates, webhook secrets, or an integration worker. Cloud API/outbox functionality in the repository is an optional future capability for automated server-to-customer notifications; its configuration is **not a blocker** for the current `wa.me` checkout handoff or the EC-09 commerce acceptance gate. Actual opening/continuation in a customer device has not been claimed as production E2E evidence.

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
| Retry/dead-letter and delivery replay | `backend/tests/ec08_db_assertions.sql` | Retry exhaustion dead-letters; duplicate WhatsApp Cloud API delivery callback is idempotent; worker RPC is service-role-only | CI-verifiable optional Cloud API capability; not required for `wa.me` checkout |
| RBAC and grants | EC-09 API tests + EC-08/Phase 07 SQL assertions | Unauthenticated API requests return 401; wrong role returns 403; mutation/worker RPCs are not executable by anon | CI-verifiable |
| RLS | EC-09/EC-08 SQL assertions | RLS remains enabled on commerce/payment/integration tables; privileged operations use guarded RPCs | Disposable-DB assertions |
| WhatsApp checkout handoff | EC-03 migration and application handoff flow | Server-created canonical order; server-prepared message; configured official business number; safe customer-owned handoff and expiry | Uses `wa.me/`; Cloud API credentials are not required. Authenticated production E2E remains deferred to Phase 12 |
| WhatsApp Cloud API notifications | Optional `backend/app/integrations.py` outbox/template/webhook routes | Cloud API token, phone-number ID, Graph API version, approved template, webhook verify token, Meta app secret and worker secret | **Optional future capability; not an EC-09 blocker** |
| Authenticated production customer/staff journey | Approved test accounts and safe test order/payment path | Run customer checkout and authorized staff workflows without production test contamination | **DEFERRED** to Phase 12 / approved test identity |
| Production release | [OtoClinic CI run 39533480729](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39533480729) on `e257b779b3c0be58560dc25e7cc587749bda7418`; Railway deployment `7639d819-b995-4b33-88cc-4a82ed624beb` on `df888d72955d8d629afabc24b2c6554cdbb9b61d` | CI acceptance passed; production build/deploy succeeded; post-deploy read-only HTTP smoke passed for health/readiness, public catalog, and unauthenticated authorization guards | **Closed for phase progression by owner waiver; authenticated live transaction/provider tests deferred to Phase 12.** |

## Change and rollback notes

- Additive migration: `supabase/migrations/20261021022911_ec09_payment_webhook_replay_guards.sql`.
- The migration replaces the existing `oto_payment_webhook_apply` function, preserves service-role-only execution, and does not delete, truncate, or rewrite existing commerce rows.
- Rollback must be a reviewed forward migration restoring the previous function definition if needed; do not drop payment webhook events or roll back the migration ledger. The prior definition is preserved in Git history at the parent commit.
- Live Supabase verification after applying the migration: `payment_webhook_event_payload_conflict` guard is present; `service_role` can execute the RPC; `authenticated` cannot. Production counts remained `oto_orders=0`, `oto_payment_intents=0`, `oto_payment_webhook_events=0`, and `oto_returns=0`.
- Production data was not seeded with acceptance orders, payment intents, refunds, webhook events, or fake catalog rows. Read-only count query after the deployment found `oto_orders=0`, `oto_payment_intents=0`, `oto_payment_webhook_events=0`, `oto_returns=0`, `products(status=draft)=82`, `products(status=published)=1`, and zero verified fitments for published products.
- The single published product `OTO-BAT-000008` has a description that explicitly says it remains a draft candidate and lists unverified condition, fitment, stock, estimated shipping weight, and unresolved photo rights. Do not use it as an acceptance checkout item until an authorized catalog workflow reviews/corrects its publication status and evidence. No production data was changed during this gate run.
- CI passing proves only the listed isolated checks. It does not prove external payment-provider delivery or an authenticated live production transaction. An approved production test identity/session has not been provided or independently verified in this run; do not create a replacement account or perform financial mutations without it.
