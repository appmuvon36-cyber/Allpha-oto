-- Phase 06 security hardening: inactive or unprovisioned profiles must not use owner-scoped RLS reads/uploads.
drop policy if exists "supplier owner reads own supplier" on public.suppliers;
create policy "supplier owner reads own supplier" on public.suppliers
  for select to authenticated
  using (
    owner_user_id=(select auth.uid())
    and exists(select 1 from public.user_profiles p where p.id=(select auth.uid()) and p.is_active=true)
  );

drop policy if exists "supplier owner reads own offers" on public.supplier_offers;
create policy "supplier owner reads own offers" on public.supplier_offers
  for select to authenticated
  using (
    exists (
      select 1 from public.suppliers s
      join public.user_profiles p on p.id=s.owner_user_id and p.is_active=true
      where s.id=supplier_offers.supplier_id and s.owner_user_id=(select auth.uid())
    )
  );

drop policy if exists "supplier owners read own documents" on public.supplier_documents;
create policy "supplier owners read own documents" on public.supplier_documents
  for select to authenticated
  using (
    exists (
      select 1 from public.suppliers s
      join public.user_profiles p on p.id=s.owner_user_id and p.is_active=true
      where s.id=supplier_documents.supplier_id and s.owner_user_id=(select auth.uid())
    )
  );

drop policy if exists "supplier owners upload verification documents" on storage.objects;
create policy "supplier owners upload verification documents" on storage.objects
  for insert to authenticated
  with check (
    bucket_id='supplier-verification-documents'
    and (storage.foldername(name))[1]=(select auth.uid())::text
    and exists (
      select 1 from public.suppliers s
      join public.user_profiles p on p.id=s.owner_user_id and p.is_active=true
      where s.owner_user_id=(select auth.uid())
        and s.id::text=(storage.foldername(name))[2]
        and s.status in ('pending_review','active')
    )
  );

drop policy if exists "supplier owners read verification documents" on storage.objects;
create policy "supplier owners read verification documents" on storage.objects
  for select to authenticated
  using (
    bucket_id='supplier-verification-documents'
    and (storage.foldername(name))[1]=(select auth.uid())::text
    and exists (
      select 1 from public.suppliers s
      join public.user_profiles p on p.id=s.owner_user_id and p.is_active=true
      where s.owner_user_id=(select auth.uid())
        and s.id::text=(storage.foldername(name))[2]
    )
  );
