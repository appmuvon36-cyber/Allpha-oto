# Phase 04 — Auth/RBAC Focused Review

**Date:** 2026-10-18  
**Branch:** `main`  
**Scope:** inspect existing identity and role checks before changing authorization code. No database schema changes were made.

## Current implementation

### Backend — `backend/app/main.py`

- `GET /v1/auth/me` requires a Bearer token.
- The API sends the token to Supabase Auth `/auth/v1/user`; it does not trust a user ID supplied by the browser.
- It uses the verified Auth user ID to fetch only that user's `user_profiles` row using the publishable/anon key and existing RLS.
- It returns the verified identity and profile role. An inactive profile is rejected with 403; missing profile returns no role and does not grant access.
- It has health/readiness routes, but no business routes or role-protected mutation routes yet.
- The current-user route verifies identity and exposes the caller's role; it is not itself an admin authorization gate.

### Admin — `apps/admin/src/app/login/page.tsx` and `apps/admin/src/app/admin/page.tsx`

- Login uses Supabase Auth `signInWithPassword`.
- The operations page calls `supabase.auth.getUser()` to retrieve the current authenticated identity, then queries the user's own `user_profiles` row for `role,is_active`.
- The client allows the operations dashboard for active profiles with role admin, catalog_editor, inventory_manager, order_manager or moderator.
- The current dashboard only reads product, supplier, fitment and inventory counts/recent products; it does not implement mutation operations.
- The browser role check is a UI gate, not a security boundary by itself. Existing database RLS policies are the actual boundary for these direct browser reads. Future privileged actions must be authorized by the backend and must not rely on a client-supplied role.

## Findings

1. **Identity verification exists** in the API and Admin uses Supabase Auth's `getUser()`, not only a locally decoded JWT.
2. **Admin role gating is currently client-side.** RLS policies restrict the queried rows, but a future admin write route must independently verify the bearer token, load the caller's active profile and enforce the required role on the server.
3. **The existing helper `oto_has_staff_role(...)` is security-sensitive and is used by live RLS policies.** Do not revoke it, change its signature or weaken its policies as part of this phase.
4. **No schema migration is required for the next authorization foundation step.** Reuse the existing `user_profiles` table and roles; do not create a replacement roles table or reapply the foundation migration.
5. The old `docs/phase-plan-design-system` branch does not contain the missing foundation migration file. Its three branch-only commits are documentation files, and it is substantially behind `main`; do not merge it wholesale.

## Next implementation boundary

The next code change should add a reusable server-side authorization dependency to FastAPI that:
- resolves identity through Supabase Auth from the bearer token;
- loads the active profile using the verified user ID and existing RLS;
- denies missing/inactive profiles and checks explicit allowlisted roles;
- returns 401 for missing/invalid credentials, 403 for authenticated but unauthorized callers, and 503 for upstream/configuration failures;
- is used by the first actual protected business endpoint rather than adding a fake/demo admin endpoint.

Keep the existing `GET /v1/auth/me` available to customers and suppliers as well as staff. Do not use a staff-only dependency on that route. The first protected endpoint should be selected with the feature it protects; no business mutation route is invented by this review.

## Verification policy

No broad tests were run for this review. When the authorization dependency is implemented, use only focused checks for missing token, invalid token, missing/inactive profile, disallowed role and allowed role, plus the relevant API build/deployment check. Never test by weakening production RLS or inserting fake production users/data.
