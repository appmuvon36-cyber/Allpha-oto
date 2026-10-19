-- EC-02 shipping quote/order-item weight binding assertions.
-- Runs only against the disposable CI PostgreSQL database after the signed-quote migration.
DO $$
DECLARE
  customer_id uuid := '07000000-0000-4000-8000-000000000001';
  product_id uuid := '07000000-0000-4000-8000-000000000004';
  valid_order_id uuid;
  invalid_order_id uuid;
  caught_mismatch boolean := false;
BEGIN
  INSERT INTO auth.users(id, email)
  VALUES (customer_id, 'phase07-customer@example.invalid')
  ON CONFLICT (id) DO NOTHING;
  INSERT INTO public.user_profiles(id, role, is_active)
  VALUES (customer_id, 'customer', true)
  ON CONFLICT (id) DO UPDATE SET role = EXCLUDED.role, is_active = true;

  INSERT INTO public.products(
    id, sku, slug, name, category, condition, package_quantity, warranty_days,
    status, currency, retail_price, weight_grams, source_rights_evidence
  )
  VALUES (
    product_id, 'EC02-CI-WEIGHT-001', 'ec02-ci-weight-001', 'EC-02 Weight Fixture',
    'CI', 'new_aftermarket', 1, 0, 'published', 'IDR', 1000, 250,
    'CI-only synthetic fixture'
  )
  ON CONFLICT (id) DO UPDATE SET
    status = 'published', retail_price = 1000, weight_grams = 250;

  SET CONSTRAINTS ALL DEFERRED;
  INSERT INTO public.oto_orders(
    customer_user_id, status, subtotal, shipping_fee, total_amount, shipping_address
  )
  VALUES (
    customer_id, 'pending_payment', 2000, 12000, 14000,
    '{"recipient_name":"CI Customer","phone":"081234567890","address":"Jalan Fixture 1","city":"Bogor","province":"Jawa Barat","postal_code":"16120","shipping_quote":{"weight_grams":500}}'::jsonb
  )
  RETURNING id INTO valid_order_id;

  INSERT INTO public.oto_order_items(
    order_id, product_id, sku_snapshot, name_snapshot, condition_snapshot,
    unit_price, quantity, line_total
  )
  VALUES (
    valid_order_id, product_id, 'EC02-CI-WEIGHT-001', 'EC-02 Weight Fixture',
    'new_aftermarket', 1000, 2, 2000
  );
  SET CONSTRAINTS oto_order_item_shipping_weight_guard IMMEDIATE;
  SET CONSTRAINTS oto_order_item_shipping_weight_guard DEFERRED;

  BEGIN
    INSERT INTO public.oto_orders(
      customer_user_id, status, subtotal, shipping_fee, total_amount, shipping_address
    )
    VALUES (
      customer_id, 'pending_payment', 2000, 12000, 14000,
      '{"recipient_name":"CI Customer","phone":"081234567890","address":"Jalan Fixture 1","city":"Bogor","province":"Jawa Barat","postal_code":"16120","shipping_quote":{"weight_grams":501}}'::jsonb
    )
    RETURNING id INTO invalid_order_id;

    INSERT INTO public.oto_order_items(
      order_id, product_id, sku_snapshot, name_snapshot, condition_snapshot,
      unit_price, quantity, line_total
    )
    VALUES (
      invalid_order_id, product_id, 'EC02-CI-WEIGHT-001', 'EC-02 Weight Fixture',
      'new_aftermarket', 1000, 2, 2000
    );
    SET CONSTRAINTS oto_order_item_shipping_weight_guard IMMEDIATE;
    RAISE EXCEPTION 'EC-02 mismatched shipping weight unexpectedly succeeded';
  EXCEPTION WHEN check_violation THEN
    IF position('shipping_quote_weight_mismatch' IN SQLERRM) = 0 THEN
      RAISE;
    END IF;
    caught_mismatch := true;
  END;

  IF NOT caught_mismatch THEN
    RAISE EXCEPTION 'EC-02 mismatch was not rejected by the database constraint trigger';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM public.oto_orders
    WHERE id = valid_order_id
      AND (shipping_address->'shipping_quote'->>'weight_grams')::integer = 500
  ) THEN
    RAISE EXCEPTION 'EC-02 valid signed quote snapshot was not retained on the order';
  END IF;

  IF EXISTS (SELECT 1 FROM public.oto_orders WHERE id = invalid_order_id) THEN
    RAISE EXCEPTION 'EC-02 invalid order was not rolled back';
  END IF;
END $$;
