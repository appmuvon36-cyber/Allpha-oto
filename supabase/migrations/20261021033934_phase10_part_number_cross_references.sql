-- Phase 10: trusted OEM/aftermarket cross-reference evidence.
-- Additive only. Empty by default: no unsupported interchangeability claims are seeded.
create table if not exists public.part_number_cross_references (
  id uuid primary key default gen_random_uuid(),
  canonical_part_number text not null check (length(btrim(canonical_part_number)) between 1 and 120),
  alternate_part_number text not null check (length(btrim(alternate_part_number)) between 1 and 120),
  canonical_normalized text generated always as (regexp_replace(upper(canonical_part_number), '[^A-Z0-9]', '', 'g')) stored,
  alternate_normalized text generated always as (regexp_replace(upper(alternate_part_number), '[^A-Z0-9]', '', 'g')) stored,
  canonical_type text not null check (canonical_type in ('oem', 'aftermarket')),
  alternate_type text not null check (alternate_type in ('oem', 'aftermarket')),
  relation_type text not null default 'cross_reference' check (relation_type in ('cross_reference', 'supersedes', 'replaces')),
  manufacturer text,
  source_type text not null check (source_type in ('manufacturer_catalog', 'oem_catalog', 'authorized_distributor_catalog', 'tecdoc', 'verified_supplier_catalog')),
  source_name text not null check (length(btrim(source_name)) between 2 and 180),
  source_url text not null check (source_url ~* '^https?://[^[:space:]]+$'),
  source_reference text,
  source_checked_at timestamptz not null default now(),
  review_status text not null default 'pending_review' check (review_status in ('pending_review', 'approved', 'rejected')),
  review_note text,
  reviewed_by uuid references auth.users(id),
  reviewed_at timestamptz,
  created_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint part_number_cross_references_distinct_numbers check (
    canonical_normalized <> '' and alternate_normalized <> '' and canonical_normalized <> alternate_normalized
  ),
  constraint part_number_cross_references_different_types check (canonical_type <> alternate_type),
  constraint part_number_cross_references_review_fields check (
    (review_status = 'pending_review' and reviewed_by is null and reviewed_at is null)
    or (review_status in ('approved','rejected') and reviewed_by is not null and reviewed_at is not null)
  )
);

create unique index if not exists part_number_cross_references_pair_uq
  on public.part_number_cross_references (canonical_normalized, alternate_normalized);
create index if not exists part_number_cross_references_canonical_approved_idx
  on public.part_number_cross_references (canonical_normalized) where review_status = 'approved';
create index if not exists part_number_cross_references_alternate_approved_idx
  on public.part_number_cross_references (alternate_normalized) where review_status = 'approved';

alter table public.part_number_cross_references enable row level security;
revoke all on table public.part_number_cross_references from anon, authenticated;
grant select on table public.part_number_cross_references to anon, authenticated;
grant insert, update on table public.part_number_cross_references to authenticated;

drop policy if exists "public reads approved part number cross references" on public.part_number_cross_references;
create policy "public reads approved part number cross references"
  on public.part_number_cross_references for select to anon, authenticated
  using (review_status = 'approved');

drop policy if exists "catalog staff manages part number cross references" on public.part_number_cross_references;
create policy "catalog staff manages part number cross references"
  on public.part_number_cross_references for all to authenticated
  using (public.oto_has_staff_role(ARRAY['admin','catalog_editor','moderator']::public.oto_user_role[]))
  with check (public.oto_has_staff_role(ARRAY['admin','catalog_editor','moderator']::public.oto_user_role[]));

create or replace function public.oto_audit_part_number_cross_reference()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  actor uuid := auth.uid();
  mapping_id uuid;
  next_status text;
begin
  if actor is null or not public.oto_has_staff_role(ARRAY['admin','catalog_editor','moderator']::public.oto_user_role[]) then
    raise exception 'Active catalog staff role required' using errcode = '42501';
  end if;

  if tg_op = 'INSERT' then
    if new.created_by is distinct from actor then
      raise exception 'Mapping creator must match authenticated actor' using errcode = '42501';
    end if;
    mapping_id := new.id;
    next_status := new.review_status;
  else
    if new.review_status <> old.review_status then
      if new.reviewed_by is distinct from actor or new.reviewed_at is null then
        raise exception 'Review actor and timestamp are required' using errcode = '42501';
      end if;
    end if;
    new.updated_at := now();
    mapping_id := new.id;
    next_status := new.review_status;
  end if;

  if next_status = 'approved' and (
    new.source_type not in ('manufacturer_catalog','oem_catalog','authorized_distributor_catalog','tecdoc','verified_supplier_catalog')
    or new.source_url !~* '^https?://[^[:space:]]+$'
    or new.reviewed_by is null or new.reviewed_at is null
  ) then
    raise exception 'Approved mapping requires trusted source evidence and review metadata' using errcode = '23514';
  end if;

  insert into public.audit_logs(actor_user_id, action, entity_type, entity_id, request_id, details)
  values (
    actor,
    case when tg_op = 'INSERT' then 'part_number_mapping_created' else 'part_number_mapping_reviewed' end,
    'part_number_cross_reference',
    mapping_id,
    nullif(current_setting('request.headers', true), '')::jsonb ->> 'x-request-id',
    jsonb_build_object(
      'canonical_part_number', new.canonical_part_number,
      'alternate_part_number', new.alternate_part_number,
      'canonical_type', new.canonical_type,
      'alternate_type', new.alternate_type,
      'source_type', new.source_type,
      'source_name', new.source_name,
      'review_status', next_status
    )
  );
  return new;
end;
$$;

revoke all on function public.oto_audit_part_number_cross_reference() from public, anon, authenticated;
drop trigger if exists trg_audit_part_number_cross_reference on public.part_number_cross_references;
create trigger trg_audit_part_number_cross_reference
  before insert or update on public.part_number_cross_references
  for each row execute function public.oto_audit_part_number_cross_reference();
