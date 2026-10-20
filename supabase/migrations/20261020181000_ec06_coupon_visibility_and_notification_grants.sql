-- Tighten customer notification mutation to read acknowledgement only and keep private coupons out of public checkout.
revoke update on public.oto_notifications from authenticated;
grant update(read_at) on public.oto_notifications to authenticated;

do $migration$
declare d text; old text:='where code=coupon_code_value and is_active for update'; new text:='where code=coupon_code_value and is_active and is_public for update';
begin
 select pg_get_functiondef(p.oid) into d from pg_proc p join pg_namespace n on n.oid=p.pronamespace
 where n.nspname='public' and p.proname='oto_order_mutate'
 and pg_get_function_identity_arguments(p.oid)='p_action text, p_order_id uuid, p_payload jsonb, p_request_id text';
 if d is null then raise exception 'Expected order transaction RPC not found'; end if;
 if position(new in d)>0 then return; end if;
 if position(old in d)=0 then raise exception 'Expected coupon checkout guard was not found; refusing unsafe replacement'; end if;
 execute replace(d,old,new);
end;$migration$;
