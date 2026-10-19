-- Additive Catalog Media & Provenance foundation. No existing data is changed.
create table if not exists public.product_media (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.products(id) on delete cascade,
  storage_path text,
  source_url text,
  source_listing_url text,
  source_name text,
  media_kind text not null default 'product_photo' check (media_kind in ('product_photo','packaging','label','fitment_reference','illustration')),
  alt_text text not null,
  content_type text,
  byte_size bigint check (byte_size is null or byte_size between 1 and 15728640),
  sha256 text check (sha256 is null or sha256 ~ '^[a-f0-9]{64}$'),
  rights_status text not null default 'unknown' check (rights_status in ('unknown','permission_granted','licensed','public_domain','user_owned','not_permitted')),
  rights_evidence_url text,
  rights_evidence_note text,
  review_status text not null default 'pending' check (review_status in ('pending','approved','rejected')),
  is_primary boolean not null default false,
  captured_at timestamptz,
  reviewed_at timestamptz,
  reviewed_by uuid references auth.users(id) on delete set null,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint product_media_storage_or_source check (storage_path is not null or source_url is not null),
  constraint product_media_rights_approval check (review_status <> 'approved' or (rights_status in ('permission_granted','licensed','public_domain','user_owned') and rights_evidence_note is not null and length(btrim(rights_evidence_note)) > 0))
);
create index if not exists product_media_product_review_idx on public.product_media(product_id, review_status, is_primary);
create unique index if not exists product_media_bucket_path_unique on public.product_media(storage_path) where storage_path is not null;
create unique index if not exists product_media_one_primary_approved_idx on public.product_media(product_id) where is_primary and review_status='approved';

alter table public.product_media enable row level security;
revoke all on public.product_media from anon, authenticated;
grant select on public.product_media to anon, authenticated;
grant insert, update, delete on public.product_media to authenticated;

drop policy if exists "public reads approved media for published products" on public.product_media;
create policy "public reads approved media for published products"
on public.product_media for select to anon, authenticated
using (
  review_status='approved'
  and rights_status in ('permission_granted','licensed','public_domain','user_owned')
  and exists (select 1 from public.products p where p.id=product_id and p.status::text='published')
);
drop policy if exists "catalog staff manage product media" on public.product_media;
create policy "catalog staff manage product media"
on public.product_media for all to authenticated
using (public.oto_has_staff_role(array['admin','catalog_editor','moderator']::public.oto_user_role[]))
with check (public.oto_has_staff_role(array['admin','catalog_editor','moderator']::public.oto_user_role[]));

insert into storage.buckets (id,name,public,file_size_limit,allowed_mime_types)
values ('product-media','product-media',false,15728640,array['image/jpeg','image/png','image/webp','image/avif'])
on conflict (id) do update set public=false,file_size_limit=15728640,allowed_mime_types=array['image/jpeg','image/png','image/webp','image/avif'];

drop policy if exists "catalog staff upload product media" on storage.objects;
create policy "catalog staff upload product media" on storage.objects
for insert to authenticated
with check (bucket_id='product-media' and public.oto_has_staff_role(array['admin','catalog_editor','moderator']::public.oto_user_role[]));
drop policy if exists "catalog staff update product media objects" on storage.objects;
create policy "catalog staff update product media objects" on storage.objects
for update to authenticated
using (bucket_id='product-media' and public.oto_has_staff_role(array['admin','catalog_editor','moderator']::public.oto_user_role[]))
with check (bucket_id='product-media' and public.oto_has_staff_role(array['admin','catalog_editor','moderator']::public.oto_user_role[]));
drop policy if exists "catalog staff delete product media objects" on storage.objects;
create policy "catalog staff delete product media objects" on storage.objects
for delete to authenticated
using (bucket_id='product-media' and public.oto_has_staff_role(array['admin','catalog_editor','moderator']::public.oto_user_role[]));
drop policy if exists "public reads approved product media objects" on storage.objects;
create policy "public reads approved product media objects" on storage.objects
for select to anon, authenticated
using (
  bucket_id='product-media'
  and exists (
    select 1 from public.product_media m
    join public.products p on p.id=m.product_id
    where m.storage_path=objects.name
      and m.review_status='approved'
      and m.rights_status in ('permission_granted','licensed','public_domain','user_owned')
      and p.status::text='published'
  )
);