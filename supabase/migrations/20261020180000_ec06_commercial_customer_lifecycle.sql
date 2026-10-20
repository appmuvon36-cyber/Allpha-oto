-- EC-06: commercial rules and customer lifecycle. Additive only; preserve existing commerce records.
alter table public.oto_orders
  add column if not exists coupon_code text,
  add column if not exists discount_amount numeric(14,2) not null default 0
    check (discount_amount >= 0 and discount_amount <= subtotal);

create table if not exists public.oto_coupons (
  id uuid primary key default gen_random_uuid(),
  code text not null,
  description text,
  discount_type text not null check (discount_type in ('fixed','percent')),
  discount_value numeric(14,2) not null check (discount_value > 0),
  max_discount numeric(14,2),
  minimum_subtotal numeric(14,2) not null default 0 check (minimum_subtotal >= 0),
  starts_at timestamptz not null default now(),
  ends_at timestamptz,
  usage_limit integer check (usage_limit is null or usage_limit > 0),
  per_customer_limit integer not null default 1 check (per_customer_limit > 0),
  is_active boolean not null default false,
  is_public boolean not null default false,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint oto_coupons_code_upper check (code = upper(btrim(code))),
  constraint oto_coupons_percent_range check (discount_type <> 'percent' or discount_value <= 100),
  constraint oto_coupons_end_after_start check (ends_at is null or ends_at > starts_at)
);
create unique index if not exists oto_coupons_code_unique on public.oto_coupons(code);
create table if not exists public.oto_coupon_redemptions (
  id uuid primary key default gen_random_uuid(),
  coupon_id uuid not null references public.oto_coupons(id) on delete restrict,
  order_id uuid not null unique references public.oto_orders(id) on delete restrict,
  customer_user_id uuid not null references auth.users(id) on delete restrict,
  code_snapshot text not null,
  subtotal numeric(14,2) not null check (subtotal >= 0),
  discount_amount numeric(14,2) not null check (discount_amount >= 0),
  created_at timestamptz not null default now()
);
create index if not exists oto_coupon_redemptions_customer_idx on public.oto_coupon_redemptions(coupon_id,customer_user_id);

create table if not exists public.oto_wishlist_items (
  id uuid primary key default gen_random_uuid(),
  customer_user_id uuid not null references auth.users(id) on delete cascade,
  product_id uuid not null references public.products(id) on delete cascade,
  created_at timestamptz not null default now(),
  unique(customer_user_id,product_id)
);
create index if not exists oto_wishlist_customer_idx on public.oto_wishlist_items(customer_user_id,created_at desc);

create table if not exists public.oto_saved_vehicles (
  id uuid primary key default gen_random_uuid(),
  customer_user_id uuid not null references auth.users(id) on delete cascade,
  nickname text not null check (length(btrim(nickname)) between 1 and 80),
  make_id uuid references public.vehicle_makes(id) on delete set null,
  model_id uuid references public.vehicle_models(id) on delete set null,
  variant_id uuid references public.vehicle_variants(id) on delete set null,
  model_year integer check (model_year between 1950 and 2100),
  plate_label text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint oto_saved_vehicle_make_model_required check (make_id is not null or model_id is not null or variant_id is not null)
);
create index if not exists oto_saved_vehicles_customer_idx on public.oto_saved_vehicles(customer_user_id,created_at desc);

create table if not exists public.oto_notifications (
  id uuid primary key default gen_random_uuid(),
  customer_user_id uuid not null references auth.users(id) on delete cascade,
  event_type text not null,
  title text not null,
  body text not null,
  resource_type text,
  resource_id uuid,
  read_at timestamptz,
  created_at timestamptz not null default now(),
  unique(customer_user_id,event_type,resource_type,resource_id)
);
create index if not exists oto_notifications_inbox_idx on public.oto_notifications(customer_user_id,created_at desc);

alter table public.oto_coupons enable row level security;
alter table public.oto_coupon_redemptions enable row level security;
alter table public.oto_wishlist_items enable row level security;
alter table public.oto_saved_vehicles enable row level security;
alter table public.oto_notifications enable row level security;

drop policy if exists oto_coupons_staff_read on public.oto_coupons;
create policy oto_coupons_staff_read on public.oto_coupons for select to authenticated
using (public.oto_has_staff_role(array['admin','order_manager']::public.oto_user_role[]));
drop policy if exists oto_coupons_staff_insert on public.oto_coupons;
create policy oto_coupons_staff_insert on public.oto_coupons for insert to authenticated
with check (public.oto_has_staff_role(array['admin','order_manager']::public.oto_user_role[]) and (created_by is null or created_by=auth.uid()));
drop policy if exists oto_coupons_staff_update on public.oto_coupons;
create policy oto_coupons_staff_update on public.oto_coupons for update to authenticated
using (public.oto_has_staff_role(array['admin','order_manager']::public.oto_user_role[]))
with check (public.oto_has_staff_role(array['admin','order_manager']::public.oto_user_role[]));

drop policy if exists oto_coupon_redemptions_owner_staff_read on public.oto_coupon_redemptions;
create policy oto_coupon_redemptions_owner_staff_read on public.oto_coupon_redemptions for select to authenticated
using (customer_user_id=auth.uid() or public.oto_has_staff_role(array['admin','order_manager']::public.oto_user_role[]));

drop policy if exists oto_wishlist_owner_all on public.oto_wishlist_items;
create policy oto_wishlist_owner_all on public.oto_wishlist_items for all to authenticated
using (customer_user_id=auth.uid()) with check (customer_user_id=auth.uid());
drop policy if exists oto_saved_vehicles_owner_all on public.oto_saved_vehicles;
create policy oto_saved_vehicles_owner_all on public.oto_saved_vehicles for all to authenticated
using (customer_user_id=auth.uid()) with check (customer_user_id=auth.uid());
drop policy if exists oto_notifications_owner_read on public.oto_notifications;
create policy oto_notifications_owner_read on public.oto_notifications for select to authenticated
using (customer_user_id=auth.uid());
drop policy if exists oto_notifications_owner_update on public.oto_notifications;
create policy oto_notifications_owner_update on public.oto_notifications for update to authenticated
using (customer_user_id=auth.uid()) with check (customer_user_id=auth.uid());

revoke all on public.oto_coupons,public.oto_coupon_redemptions,public.oto_wishlist_items,public.oto_saved_vehicles,public.oto_notifications from anon;
grant select,insert,update on public.oto_coupons to authenticated;
grant select on public.oto_coupon_redemptions to authenticated;
grant select,insert,delete on public.oto_wishlist_items to authenticated;
grant select,insert,update,delete on public.oto_saved_vehicles to authenticated;
grant select,update on public.oto_notifications to authenticated;

-- Validate discounts inside the database, not in the browser.
create or replace function public.oto_coupon_preview(p_code text,p_subtotal numeric)
returns jsonb language plpgsql security definer set search_path=pg_catalog,public,pg_temp as $function$
declare c public.oto_coupons%rowtype; a uuid:=auth.uid(); used_total integer; used_customer integer; d numeric(14,2);
begin
 if a is null then raise exception using errcode='42501',message='authentication_required'; end if;
 if p_subtotal is null or p_subtotal<0 or p_subtotal>100000000000 then raise exception using errcode='22023',message='subtotal_invalid'; end if;
 select * into c from public.oto_coupons where code=upper(btrim(coalesce(p_code,''))) and is_active and is_public for share;
 if not found or c.starts_at>now() or (c.ends_at is not null and c.ends_at<=now()) then raise exception using errcode='P0002',message='coupon_unavailable'; end if;
 if p_subtotal<c.minimum_subtotal then raise exception using errcode='22023',message='coupon_minimum_subtotal_not_met'; end if;
 select count(*) into used_total from public.oto_coupon_redemptions where coupon_id=c.id;
 select count(*) into used_customer from public.oto_coupon_redemptions where coupon_id=c.id and customer_user_id=a;
 if (c.usage_limit is not null and used_total>=c.usage_limit) or used_customer>=c.per_customer_limit then raise exception using errcode='22023',message='coupon_usage_limit_reached'; end if;
 d:=case when c.discount_type='fixed' then c.discount_value else round(p_subtotal*c.discount_value/100,2) end;
 if c.max_discount is not null then d:=least(d,c.max_discount); end if;
 d:=least(p_subtotal,d);
 return jsonb_build_object('code',c.code,'description',c.description,'subtotal',p_subtotal,'discount_amount',d,'total_before_shipping',p_subtotal-d,'currency','IDR');
end;
$function$;
revoke all on function public.oto_coupon_preview(text,numeric) from public,anon;
grant execute on function public.oto_coupon_preview(text,numeric) to authenticated;

-- Notifications are emitted from real order state transitions and are idempotent.
create or replace function public.oto_order_customer_notification()
returns trigger language plpgsql security definer set search_path=pg_catalog,public,pg_temp as $function$
declare t text; b text; e text;
begin
 if tg_op<>'UPDATE' or new.status is not distinct from old.status then return new; end if;
 e:='order_'||new.status;
 t:=case new.status when 'paid' then 'Pembayaran terverifikasi' when 'processing' then 'Pesanan sedang diproses' when 'shipped' then 'Pesanan dikirim' when 'delivered' then 'Pesanan diterima' when 'cancelled' then 'Pesanan dibatalkan' when 'payment_review' then 'Bukti pembayaran diterima' else null end;
 if t is null then return new; end if;
 b:=case new.status when 'paid' then 'Pembayaran pesanan Anda telah diverifikasi.' when 'processing' then 'Pesanan Anda mulai disiapkan.' when 'shipped' then 'Pesanan Anda telah diserahkan untuk pengiriman.' when 'delivered' then 'Pesanan Anda telah ditandai diterima.' when 'cancelled' then 'Pesanan Anda dibatalkan.' when 'payment_review' then 'Bukti pembayaran Anda sedang diperiksa.' else t end;
 insert into public.oto_notifications(customer_user_id,event_type,title,body,resource_type,resource_id)
 values(new.customer_user_id,e,t,b,'order',new.id) on conflict(customer_user_id,event_type,resource_type,resource_id) do nothing;
 return new;
end;$function$;
drop trigger if exists oto_order_customer_notification_trigger on public.oto_orders;
create trigger oto_order_customer_notification_trigger after update of status on public.oto_orders
for each row execute function public.oto_order_customer_notification();
revoke all on function public.oto_order_customer_notification() from public,anon,authenticated;

-- Extend the existing transaction RPC rather than introducing a parallel checkout path.
do $migration$
declare d text; old_decl text:='refund numeric(14,2);'; new_decl text:='refund numeric(14,2); coupon public.oto_coupons%rowtype; coupon_code_value text; coupon_discount numeric(14,2):=0; coupon_total_count integer; coupon_customer_count integer;';
 old_insert text:=$old$insert into public.oto_orders(customer_user_id,status,subtotal,shipping_fee,total_amount,shipping_address) values(a,'pending_payment',sub,fee,sub+fee,addr) returning * into o;$old$;
 new_insert text:=$new$ coupon_code_value:=nullif(upper(btrim(coalesce(p_payload->>'coupon_code',''))),'');
  if coupon_code_value is not null then
   select * into coupon from public.oto_coupons where code=coupon_code_value and is_active for update;
   if not found or coupon.starts_at>now() or (coupon.ends_at is not null and coupon.ends_at<=now()) then raise exception using errcode='22023',message='coupon_unavailable'; end if;
   if sub<coupon.minimum_subtotal then raise exception using errcode='22023',message='coupon_minimum_subtotal_not_met'; end if;
   select count(*) into coupon_total_count from public.oto_coupon_redemptions where coupon_id=coupon.id;
   select count(*) into coupon_customer_count from public.oto_coupon_redemptions where coupon_id=coupon.id and customer_user_id=a;
   if (coupon.usage_limit is not null and coupon_total_count>=coupon.usage_limit) or coupon_customer_count>=coupon.per_customer_limit then raise exception using errcode='22023',message='coupon_usage_limit_reached'; end if;
   coupon_discount:=case when coupon.discount_type='fixed' then coupon.discount_value else round(sub*coupon.discount_value/100,2) end;
   if coupon.max_discount is not null then coupon_discount:=least(coupon_discount,coupon.max_discount); end if;
   coupon_discount:=least(sub,coupon_discount);
  end if;
  insert into public.oto_orders(customer_user_id,status,subtotal,shipping_fee,total_amount,shipping_address,coupon_code,discount_amount)
  values(a,'pending_payment',sub,fee,sub-coupon_discount+fee,addr,coupon_code_value,coupon_discount) returning * into o;
  if coupon_code_value is not null then
   insert into public.oto_coupon_redemptions(coupon_id,order_id,customer_user_id,code_snapshot,subtotal,discount_amount)
   values(coupon.id,o.id,a,coupon.code,sub,coupon_discount);
  end if;$new$;
begin
 select pg_get_functiondef(p.oid) into d from pg_proc p join pg_namespace n on n.oid=p.pronamespace
 where n.nspname='public' and p.proname='oto_order_mutate'
 and pg_get_function_identity_arguments(p.oid)='p_action text, p_order_id uuid, p_payload jsonb, p_request_id text';
 if d is null then raise exception 'Expected order transaction RPC not found'; end if;
 if position('coupon_code_value' in d)>0 then return; end if;
 if position(old_decl in d)=0 or position(old_insert in d)=0 then raise exception 'Order RPC definition did not match expected baseline; refusing unsafe replacement'; end if;
 d:=replace(d,old_decl,new_decl);
 d:=replace(d,old_insert,new_insert);
 execute d;
end;$migration$;

-- Keep coupon preview limited to published public campaigns; staff can manage private coupons via RLS.
