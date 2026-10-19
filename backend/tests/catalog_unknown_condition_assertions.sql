DO $$
DECLARE
  v_product_id uuid;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type t
    JOIN pg_enum e ON e.enumtypid = t.oid
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public'
      AND t.typname = 'oto_product_condition'
      AND e.enumlabel = 'unknown'
  ) THEN
    RAISE EXCEPTION 'unknown_condition_enum_missing';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'products_condition_known_before_review'
      AND conrelid = 'public.products'::regclass
      AND convalidated
  ) THEN
    RAISE EXCEPTION 'unknown_condition_review_gate_missing_or_unvalidated';
  END IF;

  INSERT INTO public.products (
    sku, slug, name, category, condition, package_quantity, warranty_days,
    currency, retail_price, status
  ) VALUES (
    'OTO-TEST-UNKNOWN-CONDITION', 'test-unknown-condition-gate',
    'Test draft with unknown condition', 'Sistem Rem', 'unknown', 1, 0,
    'IDR', 0, 'draft'
  ) RETURNING id INTO v_product_id;

  BEGIN
    UPDATE public.products SET status = 'review' WHERE id = v_product_id;
    RAISE EXCEPTION 'unknown_condition_was_allowed_into_review';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;

  DELETE FROM public.products WHERE id = v_product_id;
END $$;
