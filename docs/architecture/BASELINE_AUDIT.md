# OtoClinic — Baseline Audit

Date: 2026-10-18. Repository: `appmuvon36-cyber/Allpha-oto`; Supabase ref: `nunnugavnpaumqefmitn`.

## GitHub
The `main` tree was observed to contain only `README.md` before application scaffolding. No package manifest, build scripts, application source, deployment configuration, or migration files were visible in that tree. The repo name remains unchanged to avoid breaking existing URLs; product branding is OtoClinic.

## Supabase
Project metadata: name `otomarket-allpha`, region `ap-southeast-2`, PostgreSQL 17, status healthy.
Live public tables were subsequently found, including:
- `user_profiles`
- `vehicle_makes`, `vehicle_models`, `vehicle_variants`
- `products`, `product_fitments`
- `suppliers`, `supplier_offers`
- `inventory_ledger`, `audit_logs`

All observed tables had RLS enabled and zero rows at inspection. Existing enums include product condition/status, fitment status, inventory movement, and user role. Therefore do not create duplicate `products`, `suppliers`, `vehicle_*`, `product_fitments`, `audit_logs`, or inventory tables. Inspect their exact columns before any schema change.

The migration listing tool returned no entries even though live business tables exist; this discrepancy is unresolved. Treat live catalog/schema introspection as authoritative for current state and reconcile migration history before any further DDL.

## Security finding and remediation
Supabase security advisor reported `public.rls_auto_enable()` as SECURITY DEFINER and executable by anon/authenticated. The function definition was inspected. A production migration `otoclinic_revoke_public_rls_helper` successfully revoked EXECUTE from PUBLIC, anon and authenticated. Re-run the security advisor and verify the function remains attached to its intended event trigger.

## Deployment
No deployment provider, domain, production URL, CI workflow, or environment contract was observed in the initial repository tree. No claim of production application deployment is made.

## Rules
- Direct-to-main implementation was requested by project owner.
- Keep changes additive; never drop/recreate live tables.
- No fake catalog, stock, pricing, supplier or KPI data.
- Keep privileged credentials out of frontend.
- Verify RLS and API authorization before enabling write actions.
