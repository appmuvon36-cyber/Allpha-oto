-- Ensure legacy order RPC cannot bypass the EC-05 carrier/service and payment gates.
do $migration$
declare
  v_definition text;
  v_old text := $old$if p_action not in ('cart_add','cart_set_quantity','cart_remove','cart_clear','checkout','submit_payment_evidence','verify_payment','reject_payment','cancel_order','start_fulfillment','mark_shipped','mark_delivered','request_return','approve_return','reject_return','receive_return','record_refund') then raise exception using errcode='22023',message='unsupported_order_action'; end if;$old$;
  v_new text := $new$if p_action not in ('cart_add','cart_set_quantity','cart_remove','cart_clear','checkout','submit_payment_evidence','verify_payment','reject_payment','cancel_order','request_return','approve_return','reject_return','receive_return','record_refund') then raise exception using errcode='22023',message='unsupported_order_action'; end if;$new$;
begin
  select pg_get_functiondef(p.oid) into v_definition
  from pg_proc p join pg_namespace n on n.oid=p.pronamespace
  where n.nspname='public' and p.proname='oto_order_mutate'
    and pg_get_function_identity_arguments(p.oid)='p_action text, p_order_id uuid, p_payload jsonb, p_request_id text';
  if v_definition is null then raise exception 'Expected public.oto_order_mutate signature was not found'; end if;
  if position(v_new in v_definition)>0 then return; end if;
  if position(v_old in v_definition)=0 then raise exception 'Legacy fulfillment allowlist did not match; refusing to rewrite function'; end if;
  execute replace(v_definition,v_old,v_new);
end;
$migration$;
