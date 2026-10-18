# OtoClinic Foundation Schema Recovery

**Recovered:** 2026-10-18  
**Live ledger version:** `20261018135537_otoclinic_foundation_catalog_fitment`  
**Project:** `nunnugavnpaumqefmitn`  
**Purpose:** recover the observable schema contract because the original migration SQL is missing from `main`.

> This is a reconstructed schema snapshot, not the original migration text. It is documentation only and must never be applied as SQL or re-run against production. The catalog describes the current schema and cannot prove historical DDL order or rule out later manual changes.

## Existing tables

All ten tables below exist in `public`; RLS is enabled on all of them and two policies were observed per table. At audit time, queried row counts were zero. No seed data was added.

- `user_profiles`: `id uuid` PK/FK `auth.users(id)` ON DELETE CASCADE; `display_name text`, `phone text`, `role oto_user_role DEFAULT 'customer'`, `is_active boolean DEFAULT true`, `created_at timestamptz DEFAULT now()`, `updated_at timestamptz DEFAULT now()`.
- `vehicle_makes`: `id uuid DEFAULT gen_random_uuid()` PK; `name text UNIQUE NOT NULL`, `slug text UNIQUE NOT NULL`, `is_active boolean DEFAULT true`, `created_at timestamptz DEFAULT now()`.
- `vehicle_models`: `id uuid DEFAULT gen_random_uuid()` PK; `make_id uuid NOT NULL` FK `vehicle_makes` ON DELETE RESTRICT; `name text`, `slug text`, `vehicle_type text`, `is_active boolean DEFAULT true`, `created_at timestamptz DEFAULT now()`; unique `(make_id, slug)`; vehicle_type CHECK: motorcycle/car/commercial/other.
- `vehicle_variants`: `id uuid DEFAULT gen_random_uuid()` PK; `model_id uuid NOT NULL` FK `vehicle_models` ON DELETE RESTRICT; `name text`, `year_start smallint`, `year_end smallint`, `engine_code text`, `transmission text`, `notes text`, `is_active boolean DEFAULT true`, `created_at timestamptz DEFAULT now()`; year range CHECK 1900–2200 and end >= start when both supplied.
- `products`: `id uuid DEFAULT gen_random_uuid()` PK; `sku text UNIQUE`, `slug text UNIQUE`, `name text`, `description text`, `brand text`, `part_number text`, `category text`, `condition oto_product_condition`, `condition_grade text`, `package_quantity integer DEFAULT 1`, `warranty_days integer DEFAULT 0`, `status oto_product_status DEFAULT 'draft'`, `currency char(3) DEFAULT 'IDR'`, `retail_price numeric`, `fitment_summary text`, `published_at timestamptz`, `created_by uuid`, `updated_by uuid`, `created_at timestamptz DEFAULT now()`, `updated_at timestamptz DEFAULT now()`. User FKs use `auth.users` ON DELETE SET NULL. Checks: package_quantity > 0, warranty_days >= 0, currency = IDR, retail_price >= 0 when present.
- `product_fitments`: `id uuid DEFAULT gen_random_uuid()` PK; `product_id uuid` FK products ON DELETE CASCADE; `variant_id uuid` FK vehicle_variants ON DELETE RESTRICT; `status oto_fitment_status DEFAULT 'unverified'`, `evidence_url text`, `evidence_note text`, `verified_by uuid` FK auth.users ON DELETE SET NULL, `verified_at timestamptz`, `created_at timestamptz DEFAULT now()`; unique `(product_id, variant_id)`; verified status requires verifier and timestamp.
- `suppliers`: `id uuid DEFAULT gen_random_uuid()` PK; `owner_user_id uuid` FK auth.users ON DELETE SET NULL; `legal_name text`, `display_name text`, `supplier_type text DEFAULT 'supplier'`, `status text DEFAULT 'pending_review'`, `contact_name text`, `contact_email text`, `contact_phone text`, `address jsonb DEFAULT '{}'`, `created_at timestamptz DEFAULT now()`, `updated_at timestamptz DEFAULT now()`. Type CHECK: oem_distributor/aftermarket_distributor/supplier/workshop/reconditioner/dismantler/individual. Status CHECK: pending_review/active/suspended/rejected.
- `supplier_offers`: `id uuid DEFAULT gen_random_uuid()` PK; `supplier_id uuid NOT NULL` FK suppliers ON DELETE RESTRICT; `product_id uuid` FK products ON DELETE SET NULL; `supplier_sku text`, `source_url text`, `source_evidence jsonb DEFAULT '{}'`, `condition oto_product_condition`, `unit_cost numeric`, `asking_price numeric`, `currency char(3) DEFAULT 'IDR'`, `stock_quantity integer DEFAULT 0`, `stock_checked_at timestamptz`, `quote_expires_at timestamptz`, `status text DEFAULT 'pending_review'`, `created_at timestamptz DEFAULT now()`, `updated_at timestamptz DEFAULT now()`. Checks: prices >= 0 when present, currency IDR, stock >= 0, status pending_review/active/unavailable/rejected/expired.
- `inventory_ledger`: `id uuid DEFAULT gen_random_uuid()` PK; `product_id uuid NOT NULL` FK products ON DELETE RESTRICT; `supplier_id uuid` FK suppliers ON DELETE SET NULL; `movement oto_inventory_movement`, `quantity_delta integer CHECK <> 0`, `reference_type text`, `reference_id uuid`, `reason text`, `actor_user_id uuid` FK auth.users ON DELETE SET NULL, `created_at timestamptz DEFAULT now()`.
- `audit_logs`: `id uuid DEFAULT gen_random_uuid()` PK; `actor_user_id uuid` FK auth.users ON DELETE SET NULL; `action text`, `entity_type text`, `entity_id uuid`, `request_id text`, `details jsonb DEFAULT '{}'`, `created_at timestamptz DEFAULT now()`.

## Enum values

- `oto_user_role`: customer, supplier, catalog_editor, inventory_manager, order_manager, moderator, admin.
- `oto_product_status`: draft, review, approved, published, rejected, archived.
- `oto_product_condition`: new_oem, new_aftermarket, used, refurbished, remanufactured, damaged_for_parts.
- `oto_fitment_status`: unverified, needs_review, verified, rejected.
- `oto_inventory_movement`: receipt, sale, reservation, release, adjustment_increase, adjustment_decrease, return, write_off.

## Indexes observed

- vehicle_makes: PK, unique name, unique slug.
- vehicle_models: PK, unique (make_id, slug).
- vehicle_variants: PK.
- products: PK, unique SKU and slug, part_number, (status, category), GIN full-text index over name + brand + part_number.
- product_fitments: PK, unique (product_id, variant_id), (variant_id, status).
- suppliers: PK.
- supplier_offers: PK, (product_id, status).
- inventory_ledger: PK, (product_id, created_at DESC).
- audit_logs: PK, (entity_type, entity_id, created_at DESC).

## Trigger functions, triggers and grants observed

- `oto_set_updated_at()` sets `NEW.updated_at = now()`; fixed search path `pg_catalog`.
- Exact triggers: `products_updated_at BEFORE UPDATE ON public.products`; `supplier_offers_updated_at BEFORE UPDATE ON public.supplier_offers`; `suppliers_updated_at BEFORE UPDATE ON public.suppliers`; `user_profiles_updated_at BEFORE UPDATE ON public.user_profiles`. All execute `oto_set_updated_at()`.
- Event trigger `ensure_rls` runs on `ddl_command_end`, owned by postgres, enabled state `O`, and calls `rls_auto_enable()`.
- Observed routine EXECUTE grants: `oto_has_staff_role(oto_user_role[])` to authenticated, postgres, service_role; `oto_set_updated_at()` to postgres and service_role; `rls_auto_enable()` to postgres and service_role. The second migration explicitly revokes `rls_auto_enable()` from public, anon and authenticated.
- `oto_has_staff_role(oto_user_role[])` is SECURITY DEFINER with fixed search path `pg_catalog, public` and checks the caller's active profile/role. Existing RLS policies rely on it; do not revoke or change without a policy-safe replacement.

## RLS policies observed

All ten tables have RLS enabled. The following policy names, commands and expressions were read from `pg_policies`:

- `user_profiles`: SELECT authenticated where `id = auth.uid()` (`profile owner reads own profile`); SELECT authenticated where `oto_has_staff_role(ARRAY['admin'::oto_user_role])` (`staff reads profiles`).
- `vehicle_makes`: SELECT anon/authenticated where `is_active` (`active vehicles readable`); ALL authenticated with both USING and WITH CHECK `oto_has_staff_role(ARRAY['admin'::oto_user_role, 'catalog_editor'::oto_user_role])` (`staff manages vehicle makes`).
- `vehicle_models`: SELECT anon/authenticated where `is_active` (`active models readable`); ALL authenticated with the same admin/catalog_editor role check (`staff manages vehicle models`).
- `vehicle_variants`: SELECT anon/authenticated where `is_active` (`active variants readable`); ALL authenticated with the same admin/catalog_editor role check (`staff manages vehicle variants`).
- `products`: SELECT anon/authenticated where `status = 'published'::oto_product_status` (`public reads published products`); ALL authenticated with USING and WITH CHECK for admin/catalog_editor/moderator (`staff manages products`).
- `product_fitments`: SELECT anon/authenticated where status is verified and an associated product is published (`public reads verified published fitments`); ALL authenticated with USING and WITH CHECK for admin/catalog_editor/moderator (`staff manages fitments`).
- `suppliers`: SELECT authenticated where `owner_user_id = auth.uid()` (`supplier owner reads own supplier`); ALL authenticated with USING and WITH CHECK for admin/catalog_editor/inventory_manager (`staff manages suppliers`).
- `supplier_offers`: SELECT authenticated when an associated supplier has `owner_user_id = auth.uid()` (`supplier owner reads own offers`); ALL authenticated with USING and WITH CHECK for admin/catalog_editor/inventory_manager (`staff manages offers`).
- `inventory_ledger`: SELECT authenticated for admin/inventory_manager/order_manager (`inventory staff reads ledger`); INSERT authenticated for admin/inventory_manager (`inventory staff writes ledger`).
- `audit_logs`: SELECT authenticated for admin (`admin reads audit logs`); INSERT authenticated for admin/catalog_editor/inventory_manager/order_manager/moderator (`staff inserts audit logs`).

## Reconciliation decision

The original migration SQL remains unrecovered as a historical file. This baseline now records the live schema contract, including trigger attachments, the event trigger, observed routine grants and policy expressions. It can guide future review but cannot prove the original migration's exact source or historical order. Do not apply this file, do not duplicate the foundation migration, and make future schema changes only through reviewed additive migrations after comparing against the live catalog.
