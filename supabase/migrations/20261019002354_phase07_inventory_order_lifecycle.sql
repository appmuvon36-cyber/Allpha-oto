
-- Phase 07 additive schema. Existing business tables and inventory_ledger are preserved.
create table if not exists public.inventory_balances (
 product_id uuid primary key references public.products(id) on delete restrict,
 on_hand integer not null default 0 check(on_hand>=0),
 reserved integer not null default 0 check(reserved>=0 and reserved<=on_hand),
 updated_at timestamptz not null default now()
);
insert into public.inventory_balances(product_id,on_hand)
select product_id,greatest(0,sum(case when movement in ('receipt','adjustment_increase','return','sale','adjustment_decrease','write_off') then quantity_delta else 0 end))::integer
from public.inventory_ledger group by product_id on conflict(product_id) do nothing;

create table if not exists public.shopping_carts(
 id uuid primary key default gen_random_uuid(), customer_user_id uuid not null unique references auth.users(id) on delete restrict,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.shopping_cart_items(
 id uuid primary key default gen_random_uuid(), cart_id uuid not null references public.shopping_carts(id) on delete cascade,
 product_id uuid not null references public.products(id) on delete restrict, quantity integer not null check(quantity between 1 and 100),
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(cart_id,product_id)
);
create table if not exists public.oto_orders(
 id uuid primary key default gen_random_uuid(), customer_user_id uuid not null references auth.users(id) on delete restrict,
 status text not null default 'pending_payment' check(status in ('pending_payment','payment_review','paid','processing','shipped','delivered','cancelled','return_requested','returned','partially_returned')),
 subtotal numeric(14,2) not null check(subtotal>=0), shipping_fee numeric(14,2) not null default 0 check(shipping_fee>=0),
 total_amount numeric(14,2) not null check(total_amount>=0), currency char(3) not null default 'IDR' check(currency='IDR'),
 shipping_address jsonb not null check(jsonb_typeof(shipping_address)='object'), tracking_code text, shipped_at timestamptz,
 delivered_at timestamptz, cancelled_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.oto_order_items(
 id uuid primary key default gen_random_uuid(), order_id uuid not null references public.oto_orders(id) on delete restrict,
 product_id uuid not null references public.products(id) on delete restrict, sku_snapshot text not null, name_snapshot text not null,
 condition_snapshot public.oto_product_condition not null, unit_price numeric(14,2) not null check(unit_price>=0),
 quantity integer not null check(quantity between 1 and 100), line_total numeric(14,2) not null check(line_total>=0),
 created_at timestamptz not null default now(), unique(order_id,product_id)
);
create table if not exists public.inventory_reservations(
 id uuid primary key default gen_random_uuid(), order_id uuid not null references public.oto_orders(id) on delete restrict,
 product_id uuid not null references public.products(id) on delete restrict, quantity integer not null check(quantity>0),
 status text not null default 'reserved' check(status in ('reserved','released','consumed')),
 expires_at timestamptz not null default(now()+interval '30 minutes'), created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(), unique(order_id,product_id)
);
create table if not exists public.oto_payment_events(
 id uuid primary key default gen_random_uuid(), order_id uuid not null references public.oto_orders(id) on delete restrict,
 event_type text not null default 'payment' check(event_type in ('payment','refund')),
 submitted_by uuid references auth.users(id) on delete restrict, amount numeric(14,2) not null check(amount>=0),
 method text not null default 'manual_transfer' check(method in ('manual_transfer','provider')), provider_reference text,
 evidence_reference text, status text not null default 'pending_review' check(status in ('pending_review','verified','rejected','refund_pending','refunded')),
 reviewed_by uuid references auth.users(id) on delete restrict, reviewed_at timestamptz, review_note text,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.oto_returns(
 id uuid primary key default gen_random_uuid(), order_id uuid not null unique references public.oto_orders(id) on delete restrict,
 customer_user_id uuid not null references auth.users(id) on delete restrict,
 status text not null default 'requested' check(status in ('requested','approved','rejected','received','refund_pending','refunded')),
 reason text not null check(length(btrim(reason)) between 3 and 1000), requested_refund numeric(14,2) not null default 0 check(requested_refund>=0),
 refund_provider_reference text, reviewed_by uuid references auth.users(id) on delete restrict, reviewed_at timestamptz,
 received_by uuid references auth.users(id) on delete restrict, received_at timestamptz, refunded_at timestamptz,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.oto_return_items(
 id uuid primary key default gen_random_uuid(), return_id uuid not null references public.oto_returns(id) on delete restrict,
 order_item_id uuid not null references public.oto_order_items(id) on delete restrict, quantity integer not null check(quantity between 1 and 100),
 refund_amount numeric(14,2) not null check(refund_amount>=0), restocked boolean not null default false,
 created_at timestamptz not null default now(), unique(return_id,order_item_id)
);
create table if not exists public.oto_idempotency_records(
 actor_user_id uuid not null references auth.users(id) on delete restrict, request_id text not null check(length(btrim(request_id)) between 8 and 128),
 action text not null, target_id uuid, payload_fingerprint text not null, result jsonb not null, created_at timestamptz not null default now(),
 primary key(actor_user_id,request_id)
);
create index if not exists inventory_ledger_product_created_idx on public.inventory_ledger(product_id,created_at desc);
create index if not exists inventory_reservations_expiry_idx on public.inventory_reservations(status,expires_at);
create index if not exists oto_orders_customer_created_idx on public.oto_orders(customer_user_id,created_at desc);
create index if not exists oto_orders_status_created_idx on public.oto_orders(status,created_at desc);
create index if not exists oto_order_items_order_idx on public.oto_order_items(order_id);
create index if not exists oto_payment_events_order_created_idx on public.oto_payment_events(order_id,created_at desc);
create index if not exists oto_returns_customer_created_idx on public.oto_returns(customer_user_id,created_at desc);

alter table public.inventory_balances enable row level security;
alter table public.shopping_carts enable row level security;
alter table public.shopping_cart_items enable row level security;
alter table public.oto_orders enable row level security;
alter table public.oto_order_items enable row level security;
alter table public.inventory_reservations enable row level security;
alter table public.oto_payment_events enable row level security;
alter table public.oto_returns enable row level security;
alter table public.oto_return_items enable row level security;
alter table public.oto_idempotency_records enable row level security;
drop policy if exists "inventory balances staff read" on public.inventory_balances;
create policy "inventory balances staff read" on public.inventory_balances for select to authenticated using(public.oto_has_staff_role(array['admin','inventory_manager','order_manager']::public.oto_user_role[]));
drop policy if exists "cart owner read" on public.shopping_carts;
create policy "cart owner read" on public.shopping_carts for select to authenticated using(customer_user_id=(select auth.uid()));
drop policy if exists "cart item owner read" on public.shopping_cart_items;
create policy "cart item owner read" on public.shopping_cart_items for select to authenticated using(exists(select 1 from public.shopping_carts c where c.id=cart_id and c.customer_user_id=(select auth.uid())));
drop policy if exists "orders owner or order staff read" on public.oto_orders;
create policy "orders owner or order staff read" on public.oto_orders for select to authenticated using(customer_user_id=(select auth.uid()) or public.oto_has_staff_role(array['admin','order_manager']::public.oto_user_role[]));
drop policy if exists "order items owner or order staff read" on public.oto_order_items;
create policy "order items owner or order staff read" on public.oto_order_items for select to authenticated using(exists(select 1 from public.oto_orders o where o.id=order_id and (o.customer_user_id=(select auth.uid()) or public.oto_has_staff_role(array['admin','order_manager']::public.oto_user_role[]))));
drop policy if exists "reservation owner or inventory staff read" on public.inventory_reservations;
create policy "reservation owner or inventory staff read" on public.inventory_reservations for select to authenticated using(exists(select 1 from public.oto_orders o where o.id=order_id and (o.customer_user_id=(select auth.uid()) or public.oto_has_staff_role(array['admin','inventory_manager','order_manager']::public.oto_user_role[]))));
drop policy if exists "payment owner or order staff read" on public.oto_payment_events;
create policy "payment owner or order staff read" on public.oto_payment_events for select to authenticated using(exists(select 1 from public.oto_orders o where o.id=order_id and (o.customer_user_id=(select auth.uid()) or public.oto_has_staff_role(array['admin','order_manager']::public.oto_user_role[]))));
drop policy if exists "returns owner or order staff read" on public.oto_returns;
create policy "returns owner or order staff read" on public.oto_returns for select to authenticated using(customer_user_id=(select auth.uid()) or public.oto_has_staff_role(array['admin','order_manager']::public.oto_user_role[]));
drop policy if exists "return items owner or order staff read" on public.oto_return_items;
create policy "return items owner or order staff read" on public.oto_return_items for select to authenticated using(exists(select 1 from public.oto_returns r where r.id=return_id and (r.customer_user_id=(select auth.uid()) or public.oto_has_staff_role(array['admin','order_manager']::public.oto_user_role[]))));
revoke all on public.inventory_balances,public.shopping_carts,public.shopping_cart_items,public.oto_orders,public.oto_order_items,public.inventory_reservations,public.oto_payment_events,public.oto_returns,public.oto_return_items,public.oto_idempotency_records from anon,authenticated;
grant select on public.inventory_balances,public.shopping_carts,public.shopping_cart_items,public.oto_orders,public.oto_order_items,public.inventory_reservations,public.oto_payment_events,public.oto_returns,public.oto_return_items to authenticated;

create or replace function public.oto_inventory_mutate(p_action text,p_product_id uuid,p_payload jsonb,p_request_id text)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public' as $function$
declare
 a uuid:=auth.uid(); r public.oto_user_role; active boolean; q integer:=nullif(p_payload->>'quantity','')::integer;
 mv public.oto_inventory_movement; d integer; b public.inventory_balances%rowtype; l public.inventory_ledger%rowtype;
 old public.oto_idempotency_records%rowtype; out jsonb; why text:=nullif(btrim(p_payload->>'reason'),'');
 target_supplier uuid:=nullif(p_payload->>'supplier_id','')::uuid;
 fp text:=md5(coalesce(p_action,'')||':'||coalesce(p_product_id::text,'')||':'||coalesce(p_payload,'{}'::jsonb)::text);
begin
 if a is null then raise exception using errcode='42501',message='authentication_required'; end if;
 select role,is_active into r,active from public.user_profiles where id=a;
 if not found or active is distinct from true then raise exception using errcode='42501',message='active_profile_required'; end if;
 if r not in ('admin'::public.oto_user_role,'inventory_manager'::public.oto_user_role) then raise exception using errcode='42501',message='inventory_role_required'; end if;
 if p_request_id is null or length(btrim(p_request_id))<8 or length(p_request_id)>128 then raise exception using errcode='22023',message='request_id_invalid'; end if;
 if p_action not in ('receipt','adjustment_increase','adjustment_decrease','write_off') then raise exception using errcode='22023',message='unsupported_inventory_action'; end if;
 if p_product_id is null or q is null or q<1 or q>1000000 or why is null then raise exception using errcode='22023',message='inventory_quantity_and_reason_required'; end if;
 perform pg_advisory_xact_lock(hashtextextended(a::text||':'||p_request_id,0));
 select * into old from public.oto_idempotency_records where actor_user_id=a and request_id=p_request_id for update;
 if found then
  if old.action<>p_action or old.target_id is distinct from p_product_id or old.payload_fingerprint<>fp then raise exception using errcode='22023',message='request_id_reused_for_different_operation'; end if;
  return jsonb_set(old.result,'{replayed}','true'::jsonb,true);
 end if;
 if not exists(select 1 from public.products where id=p_product_id and status='published') then raise exception using errcode='P0002',message='published_product_not_found'; end if;
 insert into public.inventory_balances(product_id) values(p_product_id) on conflict(product_id) do nothing;
 select * into b from public.inventory_balances where product_id=p_product_id for update;
 case p_action when 'receipt' then mv:='receipt';d:=q; when 'adjustment_increase' then mv:='adjustment_increase';d:=q; when 'adjustment_decrease' then mv:='adjustment_decrease';d:=-q; when 'write_off' then mv:='write_off';d:=-q; end case;
 if d<0 and b.on_hand+d<b.reserved then raise exception using errcode='22023',message='inventory_below_reserved_quantity'; end if;
 update public.inventory_balances set on_hand=on_hand+d,updated_at=now() where product_id=p_product_id returning * into b;
 insert into public.inventory_ledger(product_id,supplier_id,movement,quantity_delta,reference_type,reference_id,reason,actor_user_id)
 values(p_product_id,target_supplier,mv,d,'inventory_mutation',nullif(p_payload->>'reference_id','')::uuid,why,a) returning * into l;
 out:=jsonb_build_object('balance',to_jsonb(b),'ledger',to_jsonb(l),'available',b.on_hand-b.reserved,'replayed',false);
 insert into public.oto_idempotency_records values(a,p_request_id,p_action,p_product_id,fp,out,now());
 insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
 values(a,'inventory_'||p_action,'inventory_balance',p_product_id,p_request_id,jsonb_build_object('quantity_delta',d,'on_hand',b.on_hand,'reserved',b.reserved,'reason',why,'ledger_id',l.id));
 return out;
end;$function$;

create or replace function public.oto_order_mutate(p_action text,p_order_id uuid,p_payload jsonb,p_request_id text)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public' as $function$
declare
 a uuid:=auth.uid(); r public.oto_user_role; active boolean; o public.oto_orders%rowtype; oi public.oto_order_items%rowtype;
 pe public.oto_payment_events%rowtype; ret public.oto_returns%rowtype; bal public.inventory_balances%rowtype; res public.inventory_reservations%rowtype;
 old public.oto_idempotency_records%rowtype; out jsonb; target uuid; fp text:=md5(coalesce(p_action,'')||':'||coalesce(p_order_id::text,'')||':'||coalesce(p_payload,'{}'::jsonb)::text);
 pid uuid; qty integer; price numeric(14,2); sub numeric(14,2):=0; fee numeric(14,2):=coalesce(nullif(p_payload->>'shipping_fee','')::numeric,0);
 item jsonb; addr jsonb:=coalesce(p_payload->'shipping_address','{}'::jsonb); why text:=nullif(btrim(p_payload->>'reason'),'');
 eventid uuid; providerref text:=nullif(btrim(p_payload->>'provider_reference'),''); evidence text:=nullif(btrim(p_payload->>'evidence_reference'),'');
 tracking text:=nullif(btrim(p_payload->>'tracking_code'),''); refund numeric(14,2);
begin
 if a is null then raise exception using errcode='42501',message='authentication_required'; end if;
 select role,is_active into r,active from public.user_profiles where id=a;
 if not found or active is distinct from true then raise exception using errcode='42501',message='active_profile_required'; end if;
 if p_request_id is null or length(btrim(p_request_id))<8 or length(p_request_id)>128 then raise exception using errcode='22023',message='request_id_invalid'; end if;
 if p_action not in ('cart_add','cart_set_quantity','cart_remove','cart_clear','checkout','submit_payment_evidence','verify_payment','reject_payment','cancel_order','start_fulfillment','mark_shipped','mark_delivered','request_return','approve_return','reject_return','receive_return','record_refund') then raise exception using errcode='22023',message='unsupported_order_action'; end if;
 if p_action in ('cart_add','cart_set_quantity','cart_remove','cart_clear','checkout','submit_payment_evidence','cancel_order','request_return') and r not in ('customer'::public.oto_user_role,'admin'::public.oto_user_role,'order_manager'::public.oto_user_role) then raise exception using errcode='42501',message='customer_or_order_role_required'; end if;
 if p_action in ('verify_payment','reject_payment','start_fulfillment','mark_shipped','mark_delivered','approve_return','reject_return','receive_return','record_refund') and r not in ('admin'::public.oto_user_role,'order_manager'::public.oto_user_role) then raise exception using errcode='42501',message='order_management_role_required'; end if;
 if p_action like 'cart_%' and r<>'customer'::public.oto_user_role then raise exception using errcode='42501',message='customer_role_required'; end if;
 target:=coalesce(p_order_id,case when p_action in ('cart_add','cart_set_quantity','cart_remove') then nullif(p_payload->>'product_id','')::uuid else null end);
 perform pg_advisory_xact_lock(hashtextextended(a::text||':'||p_request_id,0));
 select * into old from public.oto_idempotency_records where actor_user_id=a and request_id=p_request_id for update;
 if found then
  if old.action<>p_action or old.target_id is distinct from target or old.payload_fingerprint<>fp then raise exception using errcode='22023',message='request_id_reused_for_different_operation'; end if;
  return jsonb_set(old.result,'{replayed}','true'::jsonb,true);
 end if;

 if p_action like 'cart_%' then
  insert into public.shopping_carts(customer_user_id) values(a) on conflict(customer_user_id) do nothing;
  if p_action='cart_clear' then delete from public.shopping_cart_items where cart_id=(select id from public.shopping_carts where customer_user_id=a);
  else
   pid:=nullif(p_payload->>'product_id','')::uuid; qty:=nullif(p_payload->>'quantity','')::integer;
   if pid is null then raise exception using errcode='22023',message='product_id_required'; end if;
   if not exists(select 1 from public.products where id=pid and status='published' and retail_price is not null) then raise exception using errcode='P0002',message='published_product_not_found'; end if;
   if p_action='cart_remove' then delete from public.shopping_cart_items where cart_id=(select id from public.shopping_carts where customer_user_id=a) and product_id=pid;
   else
    if qty is null or qty<1 or qty>100 then raise exception using errcode='22023',message='cart_quantity_invalid'; end if;
    insert into public.shopping_cart_items(cart_id,product_id,quantity) values((select id from public.shopping_carts where customer_user_id=a),pid,qty)
    on conflict(cart_id,product_id) do update set quantity=excluded.quantity,updated_at=now();
   end if;
  end if;
  out:=jsonb_build_object('cart',coalesce((select jsonb_agg(jsonb_build_object('product_id',ci.product_id,'quantity',ci.quantity,'sku',p.sku,'name',p.name,'condition',p.condition,'unit_price',p.retail_price,'line_total',p.retail_price*ci.quantity,'available',greatest(0,coalesce(b.on_hand,0)-coalesce(b.reserved,0))) order by p.name) from public.shopping_cart_items ci join public.shopping_carts c on c.id=ci.cart_id join public.products p on p.id=ci.product_id left join public.inventory_balances b on b.product_id=p.id where c.customer_user_id=a),'[]'::jsonb),'replayed',false);
 elsif p_action='checkout' then
  if p_order_id is not null or jsonb_typeof(p_payload->'items')<>'array' or jsonb_array_length(p_payload->'items')<1 or jsonb_array_length(p_payload->'items')>50 then raise exception using errcode='22023',message='checkout_items_invalid'; end if;
  if jsonb_typeof(addr)<>'object' or length(btrim(coalesce(addr->>'recipient_name','')))<2 or length(btrim(coalesce(addr->>'phone','')))<6 or length(btrim(coalesce(addr->>'address','')))<8 or fee<0 or fee>100000000 then raise exception using errcode='22023',message='checkout_address_or_shipping_invalid'; end if;
  for item in select value from jsonb_array_elements(p_payload->'items') order by value->>'product_id' loop
   pid:=nullif(item->>'product_id','')::uuid; qty:=nullif(item->>'quantity','')::integer;
   if pid is null or qty is null or qty<1 or qty>100 then raise exception using errcode='22023',message='checkout_item_invalid'; end if;
   select retail_price into price from public.products where id=pid and status='published' and retail_price is not null for share;
   if not found then raise exception using errcode='P0002',message='published_product_not_found'; end if;
   insert into public.inventory_balances(product_id) values(pid) on conflict(product_id) do nothing;
   select * into bal from public.inventory_balances where product_id=pid for update;
   if bal.on_hand-bal.reserved<qty then raise exception using errcode='22023',message='insufficient_available_stock'; end if;
   sub:=sub+price*qty;
  end loop;
  insert into public.oto_orders(customer_user_id,status,subtotal,shipping_fee,total_amount,shipping_address) values(a,'pending_payment',sub,fee,sub+fee,addr) returning * into o;
  for item in select value from jsonb_array_elements(p_payload->'items') order by value->>'product_id' loop
   pid:=(item->>'product_id')::uuid; qty:=(item->>'quantity')::integer;
   insert into public.oto_order_items(order_id,product_id,sku_snapshot,name_snapshot,condition_snapshot,unit_price,quantity,line_total)
   select o.id,p.id,p.sku,p.name,p.condition,p.retail_price,qty,p.retail_price*qty from public.products p where p.id=pid;
   update public.inventory_balances set reserved=reserved+qty,updated_at=now() where product_id=pid;
   insert into public.inventory_reservations(order_id,product_id,quantity) values(o.id,pid,qty);
   insert into public.inventory_ledger(product_id,movement,quantity_delta,reference_type,reference_id,reason,actor_user_id) values(pid,'reservation',qty,'order',o.id,'Checkout stock reservation',a);
  end loop;
  delete from public.shopping_cart_items where cart_id=(select id from public.shopping_carts where customer_user_id=a);
  out:=jsonb_build_object('order',to_jsonb(o),'items',(select coalesce(jsonb_agg(to_jsonb(x)),'[]'::jsonb) from public.oto_order_items x where x.order_id=o.id),'replayed',false);
 else
  if p_order_id is null then raise exception using errcode='22023',message='order_id_required'; end if;
  select * into o from public.oto_orders where id=p_order_id for update;
  if not found then raise exception using errcode='P0002',message='order_not_found'; end if;
  if o.customer_user_id<>a and r not in ('admin'::public.oto_user_role,'order_manager'::public.oto_user_role) then raise exception using errcode='42501',message='order_ownership_required'; end if;
  if p_action='submit_payment_evidence' then
   if o.status<>'pending_payment' or evidence is null or length(evidence)>1000 or nullif(p_payload->>'amount','')::numeric is distinct from o.total_amount then raise exception using errcode='22023',message='payment_evidence_or_amount_invalid'; end if;
   if exists(select 1 from public.oto_payment_events where order_id=o.id and event_type='payment' and status in ('pending_review','verified')) then raise exception using errcode='22023',message='payment_already_submitted'; end if;
   insert into public.oto_payment_events(order_id,submitted_by,amount,method,evidence_reference,status)
   values(o.id,a,o.total_amount,coalesce(nullif(p_payload->>'method',''),'manual_transfer'),evidence,'pending_review') returning * into pe;
   update public.oto_orders set status='payment_review',updated_at=now() where id=o.id returning * into o;
   out:=jsonb_build_object('order',to_jsonb(o),'payment',jsonb_build_object('id',pe.id,'status',pe.status,'amount',pe.amount),'message','Bukti diterima untuk pemeriksaan; pembayaran belum terverifikasi.','replayed',false);
  elsif p_action in ('verify_payment','reject_payment') then
   eventid:=nullif(p_payload->>'payment_event_id','')::uuid;
   select * into pe from public.oto_payment_events where id=eventid and order_id=o.id and event_type='payment' for update;
   if not found or pe.status<>'pending_review' then raise exception using errcode='22023',message='pending_payment_event_required'; end if;
   if p_action='verify_payment' then
    if o.status<>'payment_review' or pe.amount<>o.total_amount or (providerref is null and nullif(btrim(p_payload->>'verification_note'),'') is null) then raise exception using errcode='22023',message='payment_verification_precondition_failed'; end if;
    update public.oto_payment_events set status='verified',provider_reference=providerref,review_note=nullif(btrim(p_payload->>'verification_note'),''),reviewed_by=a,reviewed_at=now(),updated_at=now() where id=pe.id returning * into pe;
    update public.oto_orders set status='paid',updated_at=now() where id=o.id returning * into o;
   else
    if why is null then raise exception using errcode='22023',message='payment_rejection_reason_required'; end if;
    update public.oto_payment_events set status='rejected',review_note=why,reviewed_by=a,reviewed_at=now(),updated_at=now() where id=pe.id returning * into pe;
    update public.oto_orders set status='pending_payment',updated_at=now() where id=o.id returning * into o;
   end if;
   out:=jsonb_build_object('order',to_jsonb(o),'payment',jsonb_build_object('id',pe.id,'status',pe.status),'replayed',false);
  elsif p_action='cancel_order' then
   if o.status not in ('pending_payment','payment_review') then raise exception using errcode='22023',message='order_cannot_be_cancelled'; end if;
   for res in select * from public.inventory_reservations where order_id=o.id and status='reserved' order by product_id for update loop
    update public.inventory_balances set reserved=reserved-res.quantity,updated_at=now() where product_id=res.product_id and reserved>=res.quantity;
    if not found then raise exception using errcode='23514',message='reservation_balance_inconsistent'; end if;
    update public.inventory_reservations set status='released',updated_at=now() where id=res.id;
    insert into public.inventory_ledger(product_id,movement,quantity_delta,reference_type,reference_id,reason,actor_user_id) values(res.product_id,'release',-res.quantity,'order',o.id,'Order cancelled; reservation released',a);
   end loop;
   update public.oto_orders set status='cancelled',cancelled_at=now(),updated_at=now() where id=o.id returning * into o;
   out:=jsonb_build_object('order',to_jsonb(o),'replayed',false);
  elsif p_action='start_fulfillment' then
   if o.status<>'paid' then raise exception using errcode='22023',message='paid_order_required'; end if;
   update public.oto_orders set status='processing',updated_at=now() where id=o.id returning * into o; out:=jsonb_build_object('order',to_jsonb(o),'replayed',false);
  elsif p_action='mark_shipped' then
   if o.status<>'processing' or tracking is null then raise exception using errcode='22023',message='tracking_and_processing_required'; end if;
   for res in select * from public.inventory_reservations where order_id=o.id and status='reserved' order by product_id for update loop
    update public.inventory_balances set on_hand=on_hand-res.quantity,reserved=reserved-res.quantity,updated_at=now() where product_id=res.product_id and on_hand>=res.quantity and reserved>=res.quantity;
    if not found then raise exception using errcode='23514',message='reservation_balance_inconsistent'; end if;
    update public.inventory_reservations set status='consumed',updated_at=now() where id=res.id;
    insert into public.inventory_ledger(product_id,movement,quantity_delta,reference_type,reference_id,reason,actor_user_id) values(res.product_id,'sale',-res.quantity,'order',o.id,'Order shipped; reserved stock consumed',a);
   end loop;
   update public.oto_orders set status='shipped',tracking_code=tracking,shipped_at=now(),updated_at=now() where id=o.id returning * into o; out:=jsonb_build_object('order',to_jsonb(o),'replayed',false);
  elsif p_action='mark_delivered' then
   if o.status<>'shipped' then raise exception using errcode='22023',message='shipped_order_required'; end if;
   update public.oto_orders set status='delivered',delivered_at=now(),updated_at=now() where id=o.id returning * into o; out:=jsonb_build_object('order',to_jsonb(o),'replayed',false);
  elsif p_action='request_return' then
   if o.customer_user_id<>a or o.status<>'delivered' or why is null or jsonb_typeof(p_payload->'items')<>'array' or jsonb_array_length(p_payload->'items')<1 then raise exception using errcode='22023',message='delivered_order_return_requirements_invalid'; end if;
   insert into public.oto_returns(order_id,customer_user_id,reason,requested_refund) values(o.id,a,why,0) returning * into ret;
   refund:=0;
   for item in select value from jsonb_array_elements(p_payload->'items') loop
    eventid:=nullif(item->>'order_item_id','')::uuid; qty:=nullif(item->>'quantity','')::integer;
    select * into oi from public.oto_order_items where id=eventid and order_id=o.id;
    if not found or qty is null or qty<1 or qty>oi.quantity then raise exception using errcode='22023',message='return_item_quantity_invalid'; end if;
    price:=oi.unit_price*qty; refund:=refund+price;
    insert into public.oto_return_items(return_id,order_item_id,quantity,refund_amount) values(ret.id,oi.id,qty,price);
   end loop;
   update public.oto_returns set requested_refund=refund,updated_at=now() where id=ret.id returning * into ret;
   update public.oto_orders set status='return_requested',updated_at=now() where id=o.id returning * into o;
   out:=jsonb_build_object('order',to_jsonb(o),'return',to_jsonb(ret),'replayed',false);
  elsif p_action in ('approve_return','reject_return') then
   eventid:=nullif(p_payload->>'return_id','')::uuid;
   select * into ret from public.oto_returns where id=eventid and order_id=o.id for update;
   if not found or ret.status<>'requested' then raise exception using errcode='22023',message='requested_return_required'; end if;
   if p_action='approve_return' then update public.oto_returns set status='approved',reviewed_by=a,reviewed_at=now(),updated_at=now() where id=ret.id returning * into ret;
   else
    if why is null then raise exception using errcode='22023',message='return_rejection_reason_required'; end if;
    update public.oto_returns set status='rejected',reviewed_by=a,reviewed_at=now(),updated_at=now() where id=ret.id returning * into ret;
    update public.oto_orders set status='delivered',updated_at=now() where id=o.id returning * into o;
   end if;
   out:=jsonb_build_object('order',to_jsonb(o),'return',to_jsonb(ret),'replayed',false);
  elsif p_action='receive_return' then
   eventid:=nullif(p_payload->>'return_id','')::uuid;
   select * into ret from public.oto_returns where id=eventid and order_id=o.id for update;
   if not found or ret.status<>'approved' then raise exception using errcode='22023',message='approved_return_required'; end if;
   for oi in select x.* from public.oto_order_items x join public.oto_return_items ri on ri.order_item_id=x.id where ri.return_id=ret.id order by x.product_id for update loop
    select quantity into qty from public.oto_return_items where return_id=ret.id and order_item_id=oi.id;
    if exists(select 1 from jsonb_array_elements_text(coalesce(p_payload->'restock_items','[]'::jsonb)) z(value) where z.value=oi.id::text) then
     insert into public.inventory_balances(product_id) values(oi.product_id) on conflict(product_id) do nothing;
     update public.inventory_balances set on_hand=on_hand+qty,updated_at=now() where product_id=oi.product_id;
     update public.oto_return_items set restocked=true where return_id=ret.id and order_item_id=oi.id;
     insert into public.inventory_ledger(product_id,movement,quantity_delta,reference_type,reference_id,reason,actor_user_id) values(oi.product_id,'return',qty,'return',ret.id,'Returned item inspected and approved for restock',a);
    end if;
   end loop;
   update public.oto_returns set status='refund_pending',received_by=a,received_at=now(),updated_at=now() where id=ret.id returning * into ret;
   out:=jsonb_build_object('order',to_jsonb(o),'return',to_jsonb(ret),'replayed',false);
  elsif p_action='record_refund' then
   eventid:=nullif(p_payload->>'return_id','')::uuid;
   select * into ret from public.oto_returns where id=eventid and order_id=o.id for update;
   if not found or ret.status<>'refund_pending' or providerref is null then raise exception using errcode='22023',message='refund_reference_and_pending_return_required'; end if;
   insert into public.oto_payment_events(order_id,event_type,submitted_by,amount,method,provider_reference,status,reviewed_by,reviewed_at)
   values(o.id,'refund',a,ret.requested_refund,'provider',providerref,'refunded',a,now()) returning * into pe;
   update public.oto_returns set status='refunded',refund_provider_reference=providerref,refunded_at=now(),updated_at=now() where id=ret.id returning * into ret;
   update public.oto_orders set status=case when ret.requested_refund>=total_amount then 'returned' else 'partially_returned' end,updated_at=now() where id=o.id returning * into o;
   out:=jsonb_build_object('order',to_jsonb(o),'return',to_jsonb(ret),'refund_event_id',pe.id,'replayed',false);
  end if;
 end if;
 insert into public.oto_idempotency_records(actor_user_id,request_id,action,target_id,payload_fingerprint,result) values(a,p_request_id,p_action,target,fp,out);
 insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
 values(a,p_action,case when p_action like 'cart_%' then 'shopping_cart' when p_action='checkout' then 'order' when p_action like '%payment%' or p_action in ('verify_payment','reject_payment','record_refund') then 'payment' when p_action like '%return%' or p_action='receive_return' then 'return' else 'order' end,
 coalesce(p_order_id,(out->'order'->>'id')::uuid,(out->'return'->>'id')::uuid),p_request_id,
 jsonb_build_object('action',p_action,'order_id',coalesce(p_order_id,(out->'order'->>'id')::uuid),'result_status',coalesce(out->'order'->>'status',out->'return'->>'status'),'result_id',coalesce(out->'order'->>'id',out->'return'->>'id')));
 return out;
end;$function$;
revoke all on function public.oto_inventory_mutate(text,uuid,jsonb,text) from public,anon;
revoke all on function public.oto_order_mutate(text,uuid,jsonb,text) from public,anon;
grant execute on function public.oto_inventory_mutate(text,uuid,jsonb,text) to authenticated;
grant execute on function public.oto_order_mutate(text,uuid,jsonb,text) to authenticated;
;
