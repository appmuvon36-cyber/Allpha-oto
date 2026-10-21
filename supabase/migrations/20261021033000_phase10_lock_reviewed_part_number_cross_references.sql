-- Phase 10 hardening: prevent approved/rejected evidence from being silently rewritten.
create or replace function public.oto_lock_reviewed_part_number_cross_reference()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if old.review_status in ('approved','rejected') and (
    new.canonical_part_number is distinct from old.canonical_part_number
    or new.alternate_part_number is distinct from old.alternate_part_number
    or new.canonical_type is distinct from old.canonical_type
    or new.alternate_type is distinct from old.alternate_type
    or new.relation_type is distinct from old.relation_type
    or new.manufacturer is distinct from old.manufacturer
    or new.source_type is distinct from old.source_type
    or new.source_name is distinct from old.source_name
    or new.source_url is distinct from old.source_url
    or new.source_reference is distinct from old.source_reference
    or new.source_checked_at is distinct from old.source_checked_at
  ) then
    raise exception 'Reviewed part-number evidence is immutable; create a new mapping for corrections' using errcode = '23514';
  end if;
  return new;
end;
$$;
revoke all on function public.oto_lock_reviewed_part_number_cross_reference() from public, anon, authenticated;
drop trigger if exists trg_lock_reviewed_part_number_cross_reference on public.part_number_cross_references;
create trigger trg_lock_reviewed_part_number_cross_reference
  before update on public.part_number_cross_references
  for each row execute function public.oto_lock_reviewed_part_number_cross_reference();
