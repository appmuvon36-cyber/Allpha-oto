
drop policy if exists "idempotency records deny direct access" on public.oto_idempotency_records;
create policy "idempotency records deny direct access" on public.oto_idempotency_records
for all to authenticated using (false) with check (false);
;
