# Phase 00 — Audit & Reconcile Record

**Status:** VERIFIED — audit baseline captured; no destructive production changes made  
**Date:** 2026-10-18  
**Canonical repository:** `appmuvon36-cyber/Allpha-oto`, branch `main`  
**Supabase project:** `nunnugavnpaumqefmitn`  
**Railway project:** `OtoClinic`, production environment

## Scope and method

Read the Master PRD, repository agent rules and implementation phases; inspected current backend entrypoint, customer/Admin entrypoints, CI workflow, repository migration files, live Supabase tables, migration ledger, enums, indexes, triggers, RLS policies, function privileges and security advisor; checked Railway service configuration/status and a small set of production health routes. This was a targeted baseline review, not a full regression suite.

## Canonical services and deployment state

| Service | Production endpoint | Observed state |
|---|---|---|
| `otoclinic-web` | https://otoclinic-web-production.up.railway.app | Online; deployment `547d96dc-d0da-4f0e-a413-9e75ab15c4b3` SUCCESS |
| `otoclinic-admin` | https://otoclinic-admin-production.up.railway.app | Online; deployment `99dcdb13-3042-4f16-8c6a-429f55ff5678` SUCCESS |
| `otoclinic-api` | https://otoclinic-api-production.up.railway.app | Online; deployment `87b842d5-91da-470e-9cba-a4add7b30e03` SUCCESS |

Web homepage, manifest, service worker, Admin login, API `/health` and API `/ready` returned HTTP 200 at audit time. `GET /v1/auth/me` returned HTTP 401 without a bearer token, as expected. These are smoke observations only; they do not prove all user journeys.

## Live database inventory

Ten public business tables were found, all with RLS enabled and two policies per table:

- `user_profiles`
- `vehicle_makes`
- `vehicle_models`
- `vehicle_variants`
- `products`
- `product_fitments`
- `suppliers`
- `supplier_offers`
- `inventory_ledger`
- `audit_logs`

The queried row count was zero for each of these ten tables at audit time. No production/catalog seed data was added. This does not mean the schema is absent.

Business enums present: `oto_user_role`, `oto_product_status`, `oto_product_condition`, `oto_fitment_status`, `oto_inventory_movement`. Existing indexes cover product SKU/slug, part number, full-text name/brand/part-number search, product status/category, fitment uniqueness and status, inventory history, and audit history.

Observed triggers call `oto_set_updated_at()` for `products`, `supplier_offers`, `suppliers` and `user_profiles`. RLS includes public reads of published products and verified fitments, staff-gated product/fitment/supplier/inventory/audit operations, supplier-owner reads for offers, and profile-specific rules. Exact policies remain the authority; do not weaken them to make UI flows appear functional.

No Storage buckets were returned by the live bucket inventory query. Image uploads therefore remain unconfigured/unverified.

## Migration and source reconciliation

The live migration ledger contains:

- `20261018135537_otoclinic_foundation_catalog_fitment`
- `20261018135625_otoclinic_revoke_public_rls_helper`

The repository contains the second migration file, but the source file for `20261018135537_otoclinic_foundation_catalog_fitment` could not be found at its expected path. This is a repository/live migration-source drift. The live schema was **not** recreated or modified to hide this discrepancy. Before any future schema migration, recover a reviewed baseline from the actual live schema and commit it as historical/source documentation without reapplying it to production. Do not run a duplicate foundation migration against the current database.

## Security findings and decisions

1. `public.rls_auto_enable()` has EXECUTE revoked from `public`, `anon` and `authenticated`; the second migration records this change.
2. Supabase advisor flags `public.oto_has_staff_role(allowed_roles oto_user_role[])` because it is SECURITY DEFINER and executable by authenticated users. Its current definition uses a fixed `search_path` and checks only the caller's `auth.uid()`, active profile and supplied role list. Existing RLS policies depend on this helper. Do **not** revoke it blindly or convert it without evaluating policy execution; record it as a reviewed warning and revisit with a policy-safe replacement if needed.
3. No service-role secret is configured in the frontend. API uses the Supabase URL and publishable/anon key for Auth verification and profile lookup.
4. API currently provides health/readiness and current-user identity only. There are no verified business API routes for checkout, supplier operations, inventory mutation, orders, payments or webhooks yet.
5. Admin login UI exists, but server-side role enforcement across Admin/business operations has not been proven. Authentication phase remains separate.

## Repository and deployment alignment

- Web, Admin and API use the same canonical repository and existing production services.
- Web service root: `/apps/web`; Admin service root: `/apps/admin`; API service root: `/backend`.
- The root compatibility application remains intact; no migration parity or rollback proof supports deleting it.
- Latest API commit: `d57fc28314d3d3f22781f180b9bf2bbd2b880c20`.
- Latest Web commit: `869d2462920543498dc1eeab6451b1e8bd06f5d9`.

## Phase 00 outcome

The audit and reconciliation baseline is recorded and the existing production schema/services are preserved. No schema DDL, seed data, RLS weakening, or destructive operation was performed. The missing historical foundation migration source is an explicit, documented source-control gap and must be resolved before future schema changes; it is not silently treated as complete migration parity.

## Carry-forward items (do not expand into broad test suites yet)

1. Recover the missing foundation migration source from live catalog metadata before making schema changes.
2. Continue Phase 04 Auth/RBAC and the earliest dependencies after Phase 00.
3. Configure Storage only when a documented upload feature requires it.
4. Keep early-stage verification small and focused: configuration, relevant endpoint smoke checks, and focused tests only when implementing the corresponding feature.
