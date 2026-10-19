# Phase 08 — Super Admin Control Plane

Status: IMPLEMENTED IN SOURCE AND ADDITIVE ROLE-GOVERNANCE MIGRATION APPLIED TO THE EXISTING SUPABASE PROJECT. CI, latest Railway deployments, and production smoke checks are pending.

## Scope
- Replace the dashboard's direct browser-side table reads with GET /v1/admin/overview, a FastAPI endpoint that returns counts derived from the caller's JWT and database RLS.
- Metrics are explicitly role-scoped. A domain outside the current role's scope returns available=false and value=null rather than presenting a false zero.
- Dashboard consolidates real counts for catalog review, fitment review, supplier onboarding, offer/document review, inventory, open orders, payment review, returns/refunds, audit events, and provisioned profiles. Links lead to existing operational workspaces.
- GET /v1/admin/users provides a bounded/paginated profile list with only ID, display name, role, active flag, and timestamps. It does not fetch email or phone.
- POST /v1/admin/users/{user_id}/role invokes oto_admin_set_user_role through the caller JWT. The database function validates active admin, denies self-role/self-activation changes, serializes role updates, prevents removal of the last active administrator, binds idempotency keys to payload/target, and writes an audit event atomically.
- GET /v1/admin/audit provides bounded/paginated filtering by action, entity type, or safe search. The response intentionally excludes the free-form details payload to avoid leaking PII or sensitive operational payloads.
- Admin UI routes: /admin dashboard, /users role management, /audit audit explorer, and existing /catalog, /suppliers, /inventory-orders workspaces.
- UI uses existing OtoClinic design tokens and explicit loading, empty, error, role-denied, and confirmation states. No demo KPI or synthetic production rows are introduced.

## Database
- Additive migration: supabase/migrations/20261019010200_phase08_admin_role_management.sql.
- The migration was applied to Supabase project nunnugavnpaumqefmitn. It adds only the oto_admin_set_user_role function and its execute grants; no tables are dropped/recreated and no production profile is modified.
- Role enum is based on live oto_user_role values: customer, supplier, catalog_editor, inventory_manager, order_manager, moderator, admin.
- User profiles and audit logs are read/written through authenticated FastAPI/RPC with caller JWT; frontend never receives service-role credentials.

## Acceptance and release gates
- CI: Phase 08 API contract tests and disposable-PostgreSQL role mutation assertions are included in the workflow. They must pass before closure.
- Production: verify /v1/admin/overview, /v1/admin/users, and /v1/admin/audit reject unauthenticated requests; verify role mutation returns an auth guard without bearer token. Verify /admin, /users, and /audit show the safe login state and do not expose protected rows.
- Authenticated production role mutation is intentionally not executed without a dedicated approved test account; role/RLS/IDOR matrix remains part of Phase 12.
- Current live baseline observed before this phase: zero rows in user_profiles, products, fitments, suppliers/offers/documents, inventory ledger/balances, orders, payment events, returns, and audit logs. Empty states are therefore expected; this is not treated as proof that future records or roles work end-to-end.
- Supabase Security Advisor already reports SECURITY DEFINER warnings on privileged helper/RPC functions. This phase does not claim a zero-warning security audit.

## Rollback
- Revert application commits to the prior known-good deployment if a new build or smoke test fails.
- The migration is additive. If rollback is required, remove the role UI/API exposure first; do not drop the function or alter role assignments without a separate reviewed migration and audit of any existing use.
