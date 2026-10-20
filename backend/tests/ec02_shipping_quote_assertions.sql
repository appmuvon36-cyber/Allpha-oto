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


-- Signature/expiry/idempotency assertions run only in the disposable CI database.
-- This local Vault-compatible fixture is synthetic and must never be applied to production.
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;
CREATE SCHEMA IF NOT EXISTS vault;
CREATE TABLE IF NOT EXISTS vault.decrypted_secrets (
  name text PRIMARY KEY,
  decrypted_secret text NOT NULL
);
INSERT INTO vault.decrypted_secrets(name, decrypted_secret)
VALUES ('otoclinic_rajaongkir_quote_signing_secret', 'ec02-ci-secret-not-production')
ON CONFLICT (name) DO UPDATE SET decrypted_secret = EXCLUDED.decrypted_secret;

DO $$
DECLARE
  customer_id uuid := '07000000-0000-4000-8000-000000000001';
  other_customer_id uuid := '07000000-0000-4000-8000-000000000005';
  product_id uuid := '07000000-0000-4000-8000-000000000004';
  quote_secret text := 'ec02-ci-secret-not-production';
  quoted_at text;
  quote_json jsonb;
  payload jsonb;
  result jsonb;
  order_id uuid;
  quote_message text;
  quote_signature text;
  order_count_before integer;
  caught_invalid_signature boolean := false;
  caught_expired_quote boolean := false;
  caught_wrong_actor boolean := false;
BEGIN
  INSERT INTO auth.users(id, email)
  VALUES (other_customer_id, 'phase07-customer-other@example.invalid')
  ON CONFLICT (id) DO NOTHING;
  INSERT INTO public.user_profiles(id, role, is_active)
  VALUES (other_customer_id, 'customer', true)
  ON CONFLICT (id) DO UPDATE SET role = EXCLUDED.role, is_active = true;

  UPDATE public.products
     SET status = 'published', retail_price = 1000, weight_grams = 250
   WHERE id = product_id;
  INSERT INTO public.inventory_balances(product_id, on_hand)
  VALUES (product_id, 10)
  ON CONFLICT (product_id) DO UPDATE SET on_hand = greatest(public.inventory_balances.on_hand, 10);

  quoted_at := to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"');
  quote_json := jsonb_build_object(
    'origin_id', 'ci-origin',
    'destination_id', 'ci-destination',
    'courier', 'jne',
    'service', 'REG',
    'description', 'CI-only quote fixture',
    'cost', 12000,
    'weight_grams', 500,
    'quoted_at', quoted_at,
    'expires_in_seconds', 900,
    'currency', 'IDR'
  );
  quote_message := customer_id::text || '|' ||
    (quote_json->>'origin_id') || '|' || (quote_json->>'destination_id') || '|' ||
    (quote_json->>'courier') || '|' || (quote_json->>'service') || '|' ||
    (quote_json->>'cost') || '|' || (quote_json->>'weight_grams') || '|' ||
    (quote_json->>'quoted_at') || '|' || (quote_json->>'expires_in_seconds');
  quote_signature := encode(
    extensions.hmac(convert_to(quote_message, 'UTF8'), convert_to(quote_secret, 'UTF8'), 'sha256'),
    'hex'
  );
  payload := jsonb_build_object(
    'items', jsonb_build_array(jsonb_build_object('product_id', product_id::text, 'quantity', 2)),
    'shipping_fee', 12000,
    'shipping_quote', quote_json || jsonb_build_object('signature', quote_signature),
    'shipping_address', jsonb_build_object(
      'recipient_name', 'CI Customer',
      'phone', '081234567890',
      'address', 'Jalan Fixture 1',
      'city', 'Bogor',
      'province', 'Jawa Barat',
      'postal_code', '16120',
      'shipping_quote', quote_json
    )
  );

  PERFORM set_config('request.jwt.claim.sub', customer_id::text, true);
  SELECT count(*) INTO order_count_before FROM public.oto_orders;
  result := public.oto_order_mutate('checkout', NULL, payload, 'ec02-valid-checkout-0001');
  order_id := (result#>>'{order,id}')::uuid;
  IF order_id IS NULL OR result#>>'{order,status}' <> 'pending_payment' THEN
    RAISE EXCEPTION 'EC-02 valid signed quote did not create a pending order';
  END IF;
  IF (result#>>'{order,shipping_fee}')::numeric <> 12000
     OR (result#>>'{order,total_amount}')::numeric <> 14000 THEN
    RAISE EXCEPTION 'EC-02 checkout did not retain server-validated shipping fee and total';
  END IF;

  result := public.oto_order_mutate('checkout', NULL, payload, 'ec02-valid-checkout-0001');
  IF result->>'replayed' <> 'true' THEN
    RAISE EXCEPTION 'EC-02 valid checkout retry was not idempotent';
  END IF;
  IF (SELECT count(*) FROM public.oto_orders) <> order_count_before + 1 THEN
    RAISE EXCEPTION 'EC-02 idempotent retry duplicated an order';
  END IF;

  -- Tampering with the signature must fail without creating another order.
  BEGIN
    PERFORM public.oto_order_mutate(
      'checkout', NULL,
      jsonb_set(payload, '{shipping_quote,signature}', to_jsonb('tampered-signature'::text)),
      'ec02-tampered-checkout-0001'
    );
    RAISE EXCEPTION 'EC-02 tampered signature unexpectedly succeeded';
  EXCEPTION WHEN SQLSTATE '42501' THEN
    IF position('shipping_quote_signature_invalid' IN SQLERRM) = 0 THEN RAISE; END IF;
    caught_invalid_signature := true;
  END;
  IF NOT caught_invalid_signature THEN
    RAISE EXCEPTION 'EC-02 tampered signature was not rejected';
  END IF;

  -- An otherwise correctly signed quote outside its TTL must be rejected.
  quote_json := jsonb_set(
    quote_json, '{quoted_at}',
    to_jsonb(to_char((clock_timestamp() - interval '901 seconds') AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"'))
  );
  quote_message := customer_id::text || '|' ||
    (quote_json->>'origin_id') || '|' || (quote_json->>'destination_id') || '|' ||
    (quote_json->>'courier') || '|' || (quote_json->>'service') || '|' ||
    (quote_json->>'cost') || '|' || (quote_json->>'weight_grams') || '|' ||
    (quote_json->>'quoted_at') || '|' || (quote_json->>'expires_in_seconds');
  quote_signature := encode(
    extensions.hmac(convert_to(quote_message, 'UTF8'), convert_to(quote_secret, 'UTF8'), 'sha256'),
    'hex'
  );
  payload := jsonb_set(payload, '{shipping_quote}', quote_json || jsonb_build_object('signature', quote_signature));
  payload := jsonb_set(payload, '{shipping_address,shipping_quote}', quote_json);
  BEGIN
    PERFORM public.oto_order_mutate('checkout', NULL, payload, 'ec02-expired-checkout-0001');
    RAISE EXCEPTION 'EC-02 expired quote unexpectedly succeeded';
  EXCEPTION WHEN SQLSTATE '22023' THEN
    IF position('shipping_quote_snapshot_invalid_or_expired' IN SQLERRM) = 0 THEN RAISE; END IF;
    caught_expired_quote := true;
  END;
  IF NOT caught_expired_quote THEN
    RAISE EXCEPTION 'EC-02 expired quote was not rejected';
  END IF;

  -- A signature issued for one customer cannot be replayed by another customer.
  quote_json := jsonb_set(
    quote_json, '{quoted_at}',
    to_jsonb(to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"'))
  );
  quote_message := customer_id::text || '|' ||
    (quote_json->>'origin_id') || '|' || (quote_json->>'destination_id') || '|' ||
    (quote_json->>'courier') || '|' || (quote_json->>'service') || '|' ||
    (quote_json->>'cost') || '|' || (quote_json->>'weight_grams') || '|' ||
    (quote_json->>'quoted_at') || '|' || (quote_json->>'expires_in_seconds');
  quote_signature := encode(
    extensions.hmac(convert_to(quote_message, 'UTF8'), convert_to(quote_secret, 'UTF8'), 'sha256'),
    'hex'
  );
  payload := jsonb_set(payload, '{shipping_quote}', quote_json || jsonb_build_object('signature', quote_signature));
  payload := jsonb_set(payload, '{shipping_address,shipping_quote}', quote_json);
  PERFORM set_config('request.jwt.claim.sub', other_customer_id::text, true);
  BEGIN
    PERFORM public.oto_order_mutate('checkout', NULL, payload, 'ec02-wrong-actor-0001');
    RAISE EXCEPTION 'EC-02 quote replay by a different customer unexpectedly succeeded';
  EXCEPTION WHEN SQLSTATE '42501' THEN
    IF position('shipping_quote_signature_invalid' IN SQLERRM) = 0 THEN RAISE; END IF;
    caught_wrong_actor := true;
  END;
  IF NOT caught_wrong_actor THEN
    RAISE EXCEPTION 'EC-02 quote replay by a different customer was not rejected';
  END IF;

  IF (SELECT count(*) FROM public.oto_orders) <> order_count_before + 1 THEN
    RAISE EXCEPTION 'EC-02 invalid quote attempts created unexpected orders';
  END IF;
END $$;
