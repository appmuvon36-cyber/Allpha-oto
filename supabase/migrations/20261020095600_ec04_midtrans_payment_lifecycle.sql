-- EC-04: additive payment intents and idempotent signed-provider webhook ledger.
create table if not exists public.oto_payment_intents (
 id uuid primary key default gen_random_uuid(),
 order_id uuid not null references public.oto_orders(id) on delete restrict,
 customer_user_id uuid not null references auth.users(id) on delete restrict,
 provider text not null check(provider in ('midtrans')),
 provider_order_id text not null unique,
 provider_transaction_id text,
 amount numeric(14,2) not null check(amount > 0),
 currency char(3) not null default 'IDR' check(currency='IDR'),
 status text not null default 'pending' check(status in ('pending','challenge','settlement','capture','deny','cancel','expire','failure','refunded')),
 redirect_url text,
 token text,
 expires_at timestamptz,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 unique(order_id, provider)
);
create index if not exists oto_payment_intents_order_idx on public.oto_payment_intents(order_id, created_at desc);
create table if not exists public.oto_payment_webhook_events (
 id uuid primary key default gen_random_uuid(),
 provider text not null check(provider in ('midtrans')),
 provider_event_key text not null,
 order_id uuid references public.oto_orders(id) on delete restrict,
 payment_intent_id uuid references public.oto_payment_intents(id) on delete restrict,
 status text not null,
 signature_valid boolean not null,
 payload_digest text not null,
 processed_at timestamptz,
 created_at timestamptz not null default now(),
 unique(provider, provider_event_key)
);
alter table public.oto_payment_intents enable row level security;
alter table public.oto_payment_webhook_events enable row level security;
revoke all on public.oto_payment_intents, public.oto_payment_webhook_events from anon, authenticated;
grant select on public.oto_payment_intents to authenticated;
drop policy if exists "payment intents owner or order staff read" on public.oto_payment_intents;
create policy "payment intents owner or order staff read" on public.oto_payment_intents for select to authenticated using (
 customer_user_id=(select auth.uid()) or public.oto_has_staff_role(array['admin','order_manager']::public.oto_user_role[])
);
create or replace function public.oto_payment_intent_create(
 p_order_id uuid, p_provider text, p_provider_order_id text, p_amount numeric,
 p_redirect_url text, p_token text, p_expires_at timestamptz
) returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public' as $function$
declare a uuid:=auth.uid(); o public.oto_orders%rowtype; pi public.oto_payment_intents%rowtype;
begin
 if a is null then raise exception using errcode='42501',message='authentication_required'; end if;
 select * into o from public.oto_orders where id=p_order_id for update;
 if not found or o.customer_user_id<>a then raise exception using errcode='42501',message='order_ownership_required'; end if;
 if o.status<>'pending_payment' or o.total_amount<=0 or p_amount is distinct from o.total_amount then raise exception using errcode='22023',message='order_not_payable_or_amount_mismatch'; end if;
 if p_provider<>'midtrans' or p_provider_order_id is null or length(p_provider_order_id)>100 then raise exception using errcode='22023',message='payment_provider_invalid'; end if;
 if exists(select 1 from public.oto_payment_intents where order_id=o.id and status in ('pending','challenge','capture','settlement')) then
  select * into pi from public.oto_payment_intents where order_id=o.id and status in ('pending','challenge','capture','settlement') order by created_at desc limit 1;
  return jsonb_build_object('intent',to_jsonb(pi),'replayed',true);
 end if;
 insert into public.oto_payment_intents(order_id,customer_user_id,provider,provider_order_id,amount,redirect_url,token,expires_at)
 values(o.id,a,p_provider,p_provider_order_id,p_amount,p_redirect_url,p_token,p_expires_at) returning * into pi;
 return jsonb_build_object('intent',to_jsonb(pi),'replayed',false);
end;$function$;
revoke all on function public.oto_payment_intent_create(uuid,text,text,numeric,text,text,timestamptz) from public, anon;
grant execute on function public.oto_payment_intent_create(uuid,text,text,numeric,text,text,timestamptz) to authenticated;
create or replace function public.oto_payment_webhook_apply(
 p_event_key text,p_provider_order_id text,p_transaction_id text,p_status text,
 p_amount numeric,p_payload_digest text
) returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public' as $function$
declare pi public.oto_payment_intents%rowtype; o public.oto_orders%rowtype; ev public.oto_payment_webhook_events%rowtype;
begin
 if auth.role() <> 'service_role' then raise exception using errcode='42501',message='service_role_required'; end if;
 if p_event_key is null or length(p_event_key)>200 or p_provider_order_id is null or p_status not in ('pending','capture','settlement','deny','cancel','expire','failure','refund','partial_refund') then raise exception using errcode='22023',message='webhook_fields_invalid'; end if;
 perform pg_advisory_xact_lock(hashtextextended('midtrans:'||p_event_key,0));
 select * into ev from public.oto_payment_webhook_events where provider='midtrans' and provider_event_key=p_event_key for update;
 if found then return jsonb_build_object('replayed',true,'event_id',ev.id,'status',ev.status); end if;
 select * into pi from public.oto_payment_intents where provider='midtrans' and provider_order_id=p_provider_order_id for update;
 if not found then raise exception using errcode='P0002',message='payment_intent_not_found'; end if;
 select * into o from public.oto_orders where id=pi.order_id for update;
 if p_amount is distinct from pi.amount or p_amount is distinct from o.total_amount then raise exception using errcode='23514',message='payment_amount_mismatch'; end if;
 if p_status in ('capture','settlement') then
  if o.status='pending_payment' then
   insert into public.oto_payment_events(order_id,event_type,amount,method,provider_reference,status,review_note,reviewed_at)
   values(o.id,'payment',p_amount,'provider',p_transaction_id,'verified','Verified by signed Midtrans notification',now());
   update public.oto_orders set status='paid',updated_at=now() where id=o.id;
  elsif o.status not in ('paid','processing','shipped','delivered') then raise exception using errcode='22023',message='order_state_blocks_payment_settlement'; end if;
 end if;
 update public.oto_payment_intents set status=p_status,provider_transaction_id=coalesce(p_transaction_id,provider_transaction_id),updated_at=now() where id=pi.id;
 insert into public.oto_payment_webhook_events(provider,provider_event_key,order_id,payment_intent_id,status,signature_valid,payload_digest,processed_at)
 values('midtrans',p_event_key,o.id,pi.id,p_status,true,p_payload_digest,now()) returning * into ev;
 insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
 values(null,'payment_webhook_'||p_status,'oto_payment_intent',pi.id,p_event_key,jsonb_build_object('provider','midtrans','order_id',o.id,'transaction_id',p_transaction_id,'payload_digest',p_payload_digest));
 return jsonb_build_object('replayed',false,'event_id',ev.id,'status',p_status,'order_id',o.id);
end;$function$;
revoke all on function public.oto_payment_webhook_apply(text,text,text,text,numeric,text) from public, anon, authenticated;
grant execute on function public.oto_payment_webhook_apply(text,text,text,text,numeric,text) to service_role;
