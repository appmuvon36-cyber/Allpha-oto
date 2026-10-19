-- EC-03: persist the WhatsApp-assisted handoff on the canonical OtoClinic order.
-- No separate order system, mock orders, or client-owned totals are introduced.
ALTER TABLE public.oto_orders
  ADD COLUMN IF NOT EXISTS sales_channel text NOT NULL DEFAULT 'web',
  ADD COLUMN IF NOT EXISTS whatsapp_handoff_status text NOT NULL DEFAULT 'not_started',
  ADD COLUMN IF NOT EXISTS whatsapp_handoff_prepared_at timestamptz,
  ADD COLUMN IF NOT EXISTS whatsapp_handoff_expires_at timestamptz,
  ADD COLUMN IF NOT EXISTS whatsapp_handoff_reviewed_by uuid REFERENCES auth.users(id),
  ADD COLUMN IF NOT EXISTS whatsapp_handoff_reviewed_at timestamptz,
  ADD COLUMN IF NOT EXISTS whatsapp_handoff_review_note text;

DO $constraints$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.oto_orders'::regclass AND conname='oto_orders_sales_channel_check') THEN
    ALTER TABLE public.oto_orders ADD CONSTRAINT oto_orders_sales_channel_check
      CHECK (sales_channel IN ('web','whatsapp')) NOT VALID;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.oto_orders'::regclass AND conname='oto_orders_whatsapp_handoff_status_check') THEN
    ALTER TABLE public.oto_orders ADD CONSTRAINT oto_orders_whatsapp_handoff_status_check
      CHECK (whatsapp_handoff_status IN ('not_started','prepared','confirmed','declined','expired')) NOT VALID;
  END IF;
END;
$constraints$;

ALTER TABLE public.oto_orders VALIDATE CONSTRAINT oto_orders_sales_channel_check;
ALTER TABLE public.oto_orders VALIDATE CONSTRAINT oto_orders_whatsapp_handoff_status_check;

CREATE INDEX IF NOT EXISTS oto_orders_whatsapp_handoff_queue_idx
  ON public.oto_orders (whatsapp_handoff_status, whatsapp_handoff_prepared_at DESC)
  WHERE whatsapp_handoff_status IN ('prepared','confirmed','declined','expired');

CREATE OR REPLACE FUNCTION public.oto_order_whatsapp_handoff(
  p_action text,
  p_order_id uuid,
  p_payload jsonb,
  p_request_id text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
  actor uuid := auth.uid();
  actor_role public.oto_user_role;
  active boolean;
  order_row public.oto_orders%rowtype;
  old public.oto_idempotency_records%rowtype;
  result jsonb;
  action_name text;
  fingerprint text := md5(coalesce(p_action,'') || ':' || coalesce(p_order_id::text,'') || ':' || coalesce(p_payload,'{}'::jsonb)::text);
  note text := nullif(btrim(coalesce(p_payload->>'note','')), '');
BEGIN
  IF actor IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='authentication_required';
  END IF;
  SELECT role,is_active INTO actor_role,active FROM public.user_profiles WHERE id=actor;
  IF NOT FOUND OR active IS DISTINCT FROM true THEN
    RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='active_profile_required';
  END IF;
  IF p_action NOT IN ('prepare','confirm','decline') THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='whatsapp_handoff_action_invalid';
  END IF;
  IF p_order_id IS NULL OR p_request_id IS NULL OR length(btrim(p_request_id)) < 8 OR length(p_request_id) > 128 THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='whatsapp_handoff_request_invalid';
  END IF;
  IF p_action='prepare' AND actor_role <> 'customer'::public.oto_user_role THEN
    RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='customer_role_required';
  END IF;
  IF p_action IN ('confirm','decline') AND actor_role NOT IN ('admin'::public.oto_user_role,'order_manager'::public.oto_user_role) THEN
    RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='order_management_role_required';
  END IF;

  action_name := 'whatsapp_handoff_' || p_action;
  PERFORM pg_advisory_xact_lock(hashtextextended(actor::text || ':' || p_request_id,0));
  SELECT * INTO old FROM public.oto_idempotency_records WHERE actor_user_id=actor AND request_id=p_request_id FOR UPDATE;
  IF FOUND THEN
    IF old.action IS DISTINCT FROM action_name OR old.target_id IS DISTINCT FROM p_order_id OR old.payload_fingerprint IS DISTINCT FROM fingerprint THEN
      RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='request_id_reused_for_different_operation';
    END IF;
    RETURN jsonb_set(old.result,'{replayed}','true'::jsonb,true);
  END IF;

  SELECT * INTO order_row FROM public.oto_orders WHERE id=p_order_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE='P0002', MESSAGE='order_not_found';
  END IF;
  IF actor_role='customer'::public.oto_user_role AND order_row.customer_user_id <> actor THEN
    RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='order_ownership_required';
  END IF;

  IF p_action='prepare' THEN
    IF order_row.status IN ('cancelled','delivered','returned','partially_returned') THEN
      RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='order_not_eligible_for_whatsapp_handoff';
    END IF;
    UPDATE public.oto_orders
       SET sales_channel='whatsapp',
           whatsapp_handoff_status='prepared',
           whatsapp_handoff_prepared_at=now(),
           whatsapp_handoff_expires_at=now()+interval '24 hours',
           whatsapp_handoff_reviewed_by=NULL,
           whatsapp_handoff_reviewed_at=NULL,
           whatsapp_handoff_review_note=NULL,
           updated_at=now()
     WHERE id=p_order_id
     RETURNING * INTO order_row;
  ELSE
    IF order_row.whatsapp_handoff_status <> 'prepared' THEN
      RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='prepared_whatsapp_handoff_required';
    END IF;
    IF order_row.whatsapp_handoff_expires_at IS NULL OR order_row.whatsapp_handoff_expires_at <= now() THEN
      UPDATE public.oto_orders
         SET whatsapp_handoff_status='expired',
             whatsapp_handoff_reviewed_by=actor,
             whatsapp_handoff_reviewed_at=now(),
             whatsapp_handoff_review_note='Handoff expired before staff review',
             updated_at=now()
       WHERE id=p_order_id
       RETURNING * INTO order_row;
    ELSE
      UPDATE public.oto_orders
         SET whatsapp_handoff_status=CASE WHEN p_action='confirm' THEN 'confirmed' ELSE 'declined' END,
             whatsapp_handoff_reviewed_by=actor,
             whatsapp_handoff_reviewed_at=now(),
             whatsapp_handoff_review_note=CASE WHEN p_action='decline' THEN note ELSE NULL END,
             updated_at=now()
       WHERE id=p_order_id
       RETURNING * INTO order_row;
    END IF;
  END IF;

  result := jsonb_build_object('order',to_jsonb(order_row),'replayed',false);
  INSERT INTO public.oto_idempotency_records(actor_user_id,request_id,action,target_id,payload_fingerprint,result)
  VALUES(actor,p_request_id,action_name,p_order_id,fingerprint,result);
  INSERT INTO public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
  VALUES(actor,action_name,'order',p_order_id,p_request_id,
    jsonb_build_object('action',action_name,'target_id',p_order_id,'result_status',order_row.whatsapp_handoff_status,
      'sales_channel',order_row.sales_channel,'handoff_expires_at',order_row.whatsapp_handoff_expires_at));
  RETURN result;
END;
$function$;

REVOKE ALL ON FUNCTION public.oto_order_whatsapp_handoff(text,uuid,jsonb,text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.oto_order_whatsapp_handoff(text,uuid,jsonb,text) TO authenticated;
