-- Cancelled/expired orders release coupon capacity while retaining redemption audit history.
do $migration$
declare d text; old_total text; new_total text; old_customer text; new_customer text;
begin
 old_total:='select count(*) into coupon_total_count from public.oto_coupon_redemptions where coupon_id=coupon.id;';
 new_total:='select count(*) into coupon_total_count from public.oto_coupon_redemptions cr join public.oto_orders co on co.id=cr.order_id where cr.coupon_id=coupon.id and co.status not in (''cancelled'',''expired'',''payment_expired'');';
 old_customer:='select count(*) into coupon_customer_count from public.oto_coupon_redemptions where coupon_id=coupon.id and customer_user_id=a;';
 new_customer:='select count(*) into coupon_customer_count from public.oto_coupon_redemptions cr join public.oto_orders co on co.id=cr.order_id where cr.coupon_id=coupon.id and cr.customer_user_id=a and co.status not in (''cancelled'',''expired'',''payment_expired'');';
 select pg_get_functiondef(p.oid) into d from pg_proc p join pg_namespace n on n.oid=p.pronamespace
 where n.nspname='public' and p.proname='oto_order_mutate'
 and pg_get_function_identity_arguments(p.oid)='p_action text, p_order_id uuid, p_payload jsonb, p_request_id text';
 if d is null then raise exception 'Expected order transaction RPC not found'; end if;
 if position(new_total in d)=0 then
  if position(old_total in d)=0 or position(old_customer in d)=0 then raise exception 'Coupon redemption count statements did not match baseline'; end if;
  d:=replace(d,old_total,new_total); d:=replace(d,old_customer,new_customer); execute d;
 end if;
 d:=null;
 select pg_get_functiondef(p.oid) into d from pg_proc p join pg_namespace n on n.oid=p.pronamespace
 where n.nspname='public' and p.proname='oto_coupon_preview'
 and pg_get_function_identity_arguments(p.oid)='p_code text, p_subtotal numeric';
 if d is null then raise exception 'Expected coupon preview RPC not found'; end if;
 old_total:='select count(*) into used_total from public.oto_coupon_redemptions where coupon_id=c.id;';
 new_total:='select count(*) into used_total from public.oto_coupon_redemptions cr join public.oto_orders co on co.id=cr.order_id where cr.coupon_id=c.id and co.status not in (''cancelled'',''expired'',''payment_expired'');';
 old_customer:='select count(*) into used_customer from public.oto_coupon_redemptions where coupon_id=c.id and customer_user_id=a;';
 new_customer:='select count(*) into used_customer from public.oto_coupon_redemptions cr join public.oto_orders co on co.id=cr.order_id where cr.coupon_id=c.id and cr.customer_user_id=a and co.status not in (''cancelled'',''expired'',''payment_expired'');';
 if position(new_total in d)=0 then
  if position(old_total in d)=0 or position(old_customer in d)=0 then raise exception 'Coupon preview count statements did not match baseline'; end if;
  d:=replace(d,old_total,new_total); d:=replace(d,old_customer,new_customer); execute d;
 end if;
end;$migration$;
