# Phase 00 — Audit & Reconcile Record

**Status:** VERIFIED — live baseline captured; recovery artifact committed; original migration text remains unavailable  
**Date:** 2026-10-18  
**Canonical repository:** `appmuvon36-cyber/Allpha-oto`, branch `main`  
**Supabase project:** `nunnugavnpaumqefmitn`  
**Railway project:** `OtoClinic`, production environment

## Scope and method

Inspected the current repository, service configuration, live Supabase tables, migration ledger, enums, indexes, constraints, triggers, RLS policies, helper function definitions and a small set of production health routes. This is a targeted baseline review, not a broad regression suite.

## Canonical services and deployment state

| Service | Production endpoint | Observed state |
|---|---|---|
| `otoclinic-web` | https://otoclinic-web-production.up.railway.app | Online; deployment `547d96dc-d0da-4f0e-a413-9e75ab15c4b3` SUCCESS |
| `otoclinic-admin` | https://otoclinic-admin-production.up.railway.app | Online; deployment `99dcdb13-3042-4f16-8c6a-429f55ff5678` SUCCESS |
| `otoclinic-api` | https://otoclinic-api-production.up.railway.app | Online; deployment `87b842d5-91da-470e-9cba-a4add7b30e03` SUCCESS |

At audit time, Web homepage, manifest, service worker, Admin login, API `/health` and `/ready` returned HTTP 200. `GET /v1/auth/me` returned HTTP 401 without a bearer token, as expected. These are focused smoke observations only.

## Live database inventory

Ten public tables were found, all with RLS enabled and two policies each: `user_profiles`, `vehicle_makes`, `vehicle_models`, `vehicle_variants`, `products`, `product_fitments`, `suppliers`, `supplier_offers`, `inventory_ledger`, and `audit_logs`. The queried row count was zero for each at audit time; no production seed data was added.

Enums: `oto_user_role`, `oto_product_status`, `oto_product_condition`, `oto_fitment_status`, `oto_inventory_movement`. Existing indexes support product SKU/slug, part number and full-text search, product status/category, fitment uniqueness/status, inventory history and audit history. Update triggers call `oto_set_updated_at()` for products, supplier_offers, suppliers and user_profiles. RLS permits public reads of active vehicle taxonomy, published products, and verified fitments attached to published products; staff and supplier-owner access is policy-bound. Do not weaken policies to make a UI flow appear functional.

No Storage buckets were returned by the live bucket inventory query; uploads remain unconfigured/unverified.

## Migration/source reconciliation

The live migration ledger contains:
- `20261018135537_otoclinic_foundation_catalog_fitment`
- `20261018135625_otoclinic_revoke_public_rls_helper`

The second migration source exists in the repository. The original SQL source for the first version is absent. To close the immediate baseline gap, the current live catalog was inspected and a documented reconstruction committed at [FOUNDATION_SCHEMA_RECOVERY.md](./FOUNDATION_SCHEMA_RECOVERY.md) (commit `4c2db1a9bf0b18f3ddb6a32272399635b253a2d8`). It records observed tables, columns, enums, constraints, indexes, helper functions and the high-level RLS contract.

**Important:** the recovery artifact is not the original migration and is not executable SQL. It cannot prove historical DDL order or every grant/policy detail. The original migration text remains unavailable; do not claim byte-for-byte migration parity and never reapply a duplicate foundation migration to production. Before future schema DDL, capture the remaining exact policy expressions, grants, trigger attachments and event-trigger registration, then compare proposed additive changes against the live catalog.

## Security findings

1. `public.rls_auto_enable()` EXECUTE is revoked from `public`, `anon` and `authenticated` by the second migration.
2. Supabase advisor flags `public.oto_has_staff_role(allowed_roles oto_user_role[])` as SECURITY DEFINER and executable by authenticated users. Its fixed search path and caller-bound active-profile/role check were inspected; existing RLS policies depend on it. Do not revoke or alter blindly.
3. No service-role secret is configured in the frontend. API uses the Supabase URL and publishable/anon key for Auth verification and profile lookup.
4. API currently provides health/readiness and current-user identity only. Business API routes for checkout, supplier operations, inventory mutation, orders, payments and webhooks are not yet verified.
5. Admin login UI exists, but server-side role enforcement across Admin/business operations has not been proven. Authentication remains a separate implementation phase.

## Repository and deployment alignment

- Web, Admin and API use the canonical repository and existing production services.
- Service roots: Web `/apps/web`; Admin `/apps/admin`; API `/backend`.
- Root compatibility app remains intact; there is no migration parity or rollback evidence to justify deleting it.
- Latest API commit observed: `d57fc28314d3d3f22781f180b9bf2bbd2b880c20`.
- Latest Web commit observed: `869d2462920543498dc1eeab6451b1e8bd06f5d9`.

## Phase 00 outcome

Audit and schema-baseline recovery are recorded. No production DDL, seed data, RLS weakening, destructive operation, new database or service was performed. The missing original migration source is now bounded by a committed catalog-derived recovery artifact, but exact historical migration parity is still unproven. Keep the next step focused on the earliest dependency; do not rerun completed smoke checks without a concrete reason.

## Carry-forward items

1. Before the next schema change, capture remaining exact policy expressions, grants, trigger attachments and event-trigger registration from the live catalog.
2. Then continue the earliest implementation dependency in Auth/RBAC; do not begin unrelated features.
3. Configure Storage only when an actual documented upload flow requires it.
4. Keep early-phase verification limited to focused checks for the code being changed.
