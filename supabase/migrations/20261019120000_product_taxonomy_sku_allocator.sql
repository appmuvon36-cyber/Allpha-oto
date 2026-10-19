-- Additive OtoClinic product taxonomy and on-demand SKU allocator.
-- Master taxonomy rows are valid business data; no fake products, prices or stock are inserted.
create table if not exists public.product_categories (
 id uuid primary key default gen_random_uuid(),
 parent_id uuid references public.product_categories(id) on delete restrict,
 name text not null,
 slug text not null unique check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
 code text not null unique check (code ~ '^[A-Z0-9]{2,6}$'),
 description text,
 vehicle_scope text not null default 'all' check (vehicle_scope in ('all','motorcycle','car','commercial')),
 sort_order integer not null default 100 check (sort_order >= 0),
 is_active boolean not null default true,
 created_by uuid references auth.users(id) on delete set null,
 updated_by uuid references auth.users(id) on delete set null,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 constraint product_categories_parent_not_self check (parent_id is null or parent_id <> id)
);
create unique index if not exists product_categories_name_ci_uidx on public.product_categories(lower(name));
create index if not exists product_categories_active_order_idx on public.product_categories(is_active,sort_order,name);
alter table public.product_categories enable row level security;
revoke all on public.product_categories from anon, authenticated;
grant select on public.product_categories to anon, authenticated;
grant insert, update on public.product_categories to authenticated;
drop policy if exists "public reads active product categories" on public.product_categories;
create policy "public reads active product categories" on public.product_categories for select to anon,authenticated
using (is_active=true or public.oto_has_staff_role(array['admin','catalog_editor','moderator']::public.oto_user_role[]));
drop policy if exists "catalog staff create product categories" on public.product_categories;
create policy "catalog staff create product categories" on public.product_categories for insert to authenticated
with check (public.oto_has_staff_role(array['admin','catalog_editor']::public.oto_user_role[]) and created_by=auth.uid() and updated_by=auth.uid());
drop policy if exists "catalog staff update product categories" on public.product_categories;
create policy "catalog staff update product categories" on public.product_categories for update to authenticated
using (public.oto_has_staff_role(array['admin','catalog_editor']::public.oto_user_role[]))
with check (public.oto_has_staff_role(array['admin','catalog_editor']::public.oto_user_role[]) and updated_by=auth.uid());

create table if not exists public.product_sku_sequences(
 category_id uuid primary key references public.product_categories(id) on delete restrict,
 last_value integer not null default 0 check(last_value between 0 and 999999),
 updated_at timestamptz not null default now()
);
alter table public.product_sku_sequences enable row level security;
revoke all on public.product_sku_sequences from anon,authenticated;

create or replace function public.oto_next_product_sku(p_category_id uuid)
returns text language plpgsql security definer set search_path=pg_catalog,public as $$
declare v_actor uuid:=auth.uid(); v_role public.oto_user_role; v_active boolean; v_code text; v_value integer;
begin
 if v_actor is null then raise exception using errcode='42501',message='authentication_required'; end if;
 select role,is_active into v_role,v_active from public.user_profiles where id=v_actor;
 if not found or v_active is distinct from true then raise exception using errcode='42501',message='active_profile_required'; end if;
 if v_role not in ('admin'::public.oto_user_role,'catalog_editor'::public.oto_user_role) then raise exception using errcode='42501',message='catalog_role_required'; end if;
 select code into v_code from public.product_categories where id=p_category_id and is_active=true;
 if not found then raise exception using errcode='P0002',message='active_category_not_found'; end if;
 insert into public.product_sku_sequences(category_id,last_value) values(p_category_id,1)
 on conflict(category_id) do update set last_value=public.product_sku_sequences.last_value+1,updated_at=now()
 returning last_value into v_value;
 if v_value>999999 then raise exception using errcode='22023',message='category_sku_capacity_reached'; end if;
 return 'OTO-'||v_code||'-'||lpad(v_value::text,6,'0');
end; $$;
revoke all on function public.oto_next_product_sku(uuid) from public,anon;
grant execute on function public.oto_next_product_sku(uuid) to authenticated;

create or replace function public.oto_product_category_audit()
returns trigger language plpgsql security definer set search_path=pg_catalog,public as $$
declare v_actor uuid:=auth.uid(); v_row public.product_categories%rowtype; v_action text;
begin
 if tg_op='DELETE' then v_row:=old; v_action:='archive_category';
 else v_row:=new; v_action:=case when tg_op='INSERT' then 'create_category' else 'update_category' end; end if;
 if v_actor is not null then
  insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
  values(v_actor,v_action,'product_category',v_row.id,gen_random_uuid()::text,jsonb_build_object('category_name',v_row.name,'slug',v_row.slug,'is_active',v_row.is_active));
 end if;
 if tg_op='DELETE' then return old; end if; return new;
end; $$;
drop trigger if exists product_categories_audit_trigger on public.product_categories;
create trigger product_categories_audit_trigger after insert or update or delete on public.product_categories
for each row execute function public.oto_product_category_audit();

insert into public.product_categories(name,slug,code,description,vehicle_scope,sort_order) values
('Mesin & Komponen Mesin','mesin-komponen-mesin','ENGINE','Blok mesin, piston, gasket, timing dan komponen internal.','all',10),
('Sistem Bahan Bakar','sistem-bahan-bakar','FUEL','Injeksi, karburator, pompa dan komponen bahan bakar.','all',20),
('Oli, Pelumas & Filter','oli-pelumas-filter','LUBE','Oli mesin, cairan pelumas dan filter.','all',30),
('Pendingin Mesin','pendingin-mesin','COOL','Radiator, kipas, thermostat dan sistem pendingin.','all',40),
('Transmisi','transmisi','TRANS','Gearbox, CVT, girboks dan komponen transmisi.','all',50),
('Kopling','kopling','CLUTCH','Kampas kopling, master kopling dan komponen terkait.','all',60),
('Kelistrikan & Pengapian','kelistrikan-pengapian','ELEC','Alternator, starter, busi, koil dan kabel.','all',70),
('Aki & Sistem Pengisian','aki-sistem-pengisian','BAT','Aki, regulator dan sistem pengisian.','all',80),
('Sistem Rem','sistem-rem','BRAKE','Kampas, cakram, kaliper dan hidrolik rem.','all',90),
('Suspensi','suspensi','SUSP','Shockbreaker, per dan komponen suspensi.','all',100),
('Kemudi','kemudi','STEER','Rack steer, tie rod dan komponen kemudi.','all',110),
('Bearing & Bantalan','bearing-bantalan','BEAR','Bearing roda, laher dan bantalan.','all',120),
('Ban','ban','TIRE','Ban motor, mobil dan kendaraan komersial.','all',130),
('Velg & Roda','velg-roda','WHEEL','Velg, mur roda dan komponen roda.','all',140),
('Body & Eksterior','body-eksterior','BODY','Panel body, bumper, kap dan trim eksterior.','all',150),
('Interior','interior','INTER','Dashboard, jok, panel dan trim interior.','all',160),
('Lampu & Visibilitas','lampu-visibilitas','LIGHT','Lampu, wiper, kaca dan visibilitas.','all',170),
('Knalpot','knalpot','EXHAU','Header, muffler dan komponen gas buang.','all',180),
('Rantai, Gear & Sprocket','rantai-gear-sprocket','CHAIN','Rantai, gir depan/belakang dan sprocket motor.','motorcycle',190),
('Aksesori & Perlengkapan','aksesori-perlengkapan','ACCES','Aksesori fungsional dan perlengkapan kendaraan.','all',200),
('Sensor & Elektronik','sensor-elektronik','SENS','Sensor, modul kontrol dan perangkat elektronik.','all',210),
('AC & HVAC','ac-hvac','AIRCON','Kompresor, evaporator dan sistem pendingin kabin.','car',220),
('Kaca & Spion','kaca-spion','GLASS','Kaca kendaraan, spion dan mekanisme.','all',230),
('Baut, Mur & Fastener','baut-mur-fastener','FAST','Baut, mur, klip dan pengikat.','all',240),
('Tools & Perawatan','tools-perawatan','TOOLS','Perkakas dan peralatan perawatan kendaraan.','all',250),
('Komponen Kendaraan Listrik','komponen-kendaraan-listrik','EVPART','Komponen khusus kendaraan listrik.','all',260)
on conflict(slug) do nothing;
