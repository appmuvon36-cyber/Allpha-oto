-- Phase 06 security: privileged supplier mutations must go through the audited RPCs.
drop policy if exists "staff manages suppliers" on public.suppliers;
create policy "staff reads suppliers" on public.suppliers
  for select to authenticated
  using (public.oto_has_staff_role(array['admin'::public.oto_user_role,'catalog_editor'::public.oto_user_role,'inventory_manager'::public.oto_user_role]));

drop policy if exists "staff manages offers" on public.supplier_offers;
create policy "staff reads supplier offers" on public.supplier_offers
  for select to authenticated
  using (public.oto_has_staff_role(array['admin'::public.oto_user_role,'catalog_editor'::public.oto_user_role,'inventory_manager'::public.oto_user_role]));

drop policy if exists "staff manages supplier documents" on public.supplier_documents;
create policy "staff reads supplier documents" on public.supplier_documents
  for select to authenticated
  using (public.oto_has_staff_role(array['admin'::public.oto_user_role,'moderator'::public.oto_user_role,'catalog_editor'::public.oto_user_role]));
