DO $$
DECLARE
  handoff_oid oid;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='oto_orders' AND column_name='sales_channel'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='oto_orders' AND column_name='whatsapp_handoff_status'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='oto_orders' AND column_name='whatsapp_handoff_expires_at'
  ) THEN
    RAISE EXCEPTION 'EC-03 order handoff columns missing';
  END IF;

  SELECT p.oid INTO handoff_oid
  FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='public' AND p.proname='oto_order_whatsapp_handoff'
    AND pg_get_function_identity_arguments(p.oid)='p_action text, p_order_id uuid, p_payload jsonb, p_request_id text';
  IF handoff_oid IS NULL THEN RAISE EXCEPTION 'EC-03 handoff RPC missing'; END IF;
  IF NOT has_function_privilege('authenticated', handoff_oid, 'EXECUTE') THEN
    RAISE EXCEPTION 'authenticated role cannot execute EC-03 handoff RPC';
  END IF;
  IF has_function_privilege('anon', handoff_oid, 'EXECUTE') THEN
    RAISE EXCEPTION 'anon role can execute EC-03 handoff RPC';
  END IF;
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid='public.oto_orders'::regclass) THEN
    RAISE EXCEPTION 'RLS must remain enabled on oto_orders';
  END IF;
END;
$$;
