-- Preserve provider instructions for retries/reloads without storing secrets.
alter table public.oto_payment_intents
 add column if not exists payment_type text,
 add column if not exists channel_code text,
 add column if not exists payment_details jsonb not null default '{}'::jsonb;
alter table public.oto_payment_intents drop constraint if exists oto_payment_intents_payment_type_check;
alter table public.oto_payment_intents add constraint oto_payment_intents_payment_type_check
 check (payment_type is null or payment_type in ('bank_transfer','qris'));
create or replace function public.oto_payment_intent_create(
 p_order_id uuid,p_provider text,p_provider_order_id text,p_amount numeric,
 p_redirect_url text,p_token text,p_expires_at timestamptz,p_payment_type text,p_channel_code text,p_payment_details jsonb
) returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public' as $function$
declare a uuid:=auth.uid(); o public.oto_orders%rowtype; pi public.oto_payment_intents%rowtype;
begin
 if a is null then raise exception using errcode='42501',message='authentication_required'; end if;
 if p_provider not in ('midtrans','rajaongkir') then raise exception using errcode='22023',message='payment_provider_invalid'; end if;
 if p_payment_type is not null and p_payment_type not in ('bank_transfer','qris') then raise exception using errcode='22023',message='payment_type_invalid'; end if;
 select * into o from public.oto_orders where id=p_order_id for update;
 if not found or o.customer_user_id<>a then raise exception using errcode='42501',message='order_ownership_required'; end if;
 if o.status<>'pending_payment' or o.total_amount<=0 or p_amount is distinct from o.total_amount then raise exception using errcode='22023',message='order_not_payable_or_amount_mismatch'; end if;
 if p_provider_order_id is null or length(p_provider_order_id)>180 then raise exception using errcode='22023',message='payment_provider_order_id_invalid'; end if;
 if exists(select 1 from public.oto_payment_intents where order_id=o.id and provider=p_provider and status in ('pending','challenge')) then
  select * into pi from public.oto_payment_intents where order_id=o.id and provider=p_provider and status in ('pending','challenge') order by created_at desc limit 1;
  return jsonb_build_object('intent',to_jsonb(pi),'replayed',true);
 end if;
 insert into public.oto_payment_intents(order_id,customer_user_id,provider,provider_order_id,amount,redirect_url,token,expires_at,payment_type,channel_code,payment_details)
 values(o.id,a,p_provider,p_provider_order_id,p_amount,p_redirect_url,p_token,p_expires_at,p_payment_type,p_channel_code,coalesce(p_payment_details,'{}'::jsonb)) returning * into pi;
 return jsonb_build_object('intent',to_jsonb(pi),'replayed',false);
end;$function$;
revoke all on function public.oto_payment_intent_create(uuid,text,text,numeric,text,text,timestamptz,text,text,jsonb) from public,anon;
grant execute on function public.oto_payment_intent_create(uuid,text,text,numeric,text,text,timestamptz,text,text,jsonb) to authenticated;
