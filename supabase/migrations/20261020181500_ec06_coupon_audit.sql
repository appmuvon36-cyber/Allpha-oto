-- Audit coupon administration without storing secrets or unnecessary customer data.
create or replace function public.oto_coupon_audit_event()
returns trigger language plpgsql security definer set search_path=pg_catalog,public,pg_temp as $function$
declare actor uuid:=auth.uid();
begin
 insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,details)
 values(
   actor,
   case when tg_op='INSERT' then 'coupon.created' else 'coupon.updated' end,
   'oto_coupon',
   new.id,
   jsonb_build_object(
     'code',new.code,
     'discount_type',new.discount_type,
     'discount_value',new.discount_value,
     'minimum_subtotal',new.minimum_subtotal,
     'is_active',new.is_active,
     'is_public',new.is_public,
     'starts_at',new.starts_at,
     'ends_at',new.ends_at,
     'usage_limit',new.usage_limit,
     'per_customer_limit',new.per_customer_limit
   )
 );
 return new;
end;$function$;
drop trigger if exists oto_coupon_audit_event_trigger on public.oto_coupons;
create trigger oto_coupon_audit_event_trigger after insert or update on public.oto_coupons
for each row execute function public.oto_coupon_audit_event();
revoke all on function public.oto_coupon_audit_event() from public,anon,authenticated;
