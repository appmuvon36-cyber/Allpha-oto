drop policy if exists "catalog staff read product media objects" on storage.objects;
create policy "catalog staff read product media objects" on storage.objects
for select to authenticated
using (bucket_id='product-media' and public.oto_has_staff_role(array['admin','catalog_editor','moderator']::public.oto_user_role[]));