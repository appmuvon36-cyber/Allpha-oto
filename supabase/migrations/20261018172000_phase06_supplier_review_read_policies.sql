-- Phase 06: moderators can read supplier review queues; mutations remain RPC-authorized.
drop policy if exists "moderators read suppliers" on public.suppliers;
create policy "moderators read suppliers" on public.suppliers
  for select to authenticated
  using (public.oto_has_staff_role(array['admin'::public.oto_user_role,'moderator'::public.oto_user_role]));

drop policy if exists "moderators read supplier offers" on public.supplier_offers;
create policy "moderators read supplier offers" on public.supplier_offers
  for select to authenticated
  using (public.oto_has_staff_role(array['admin'::public.oto_user_role,'moderator'::public.oto_user_role]));
