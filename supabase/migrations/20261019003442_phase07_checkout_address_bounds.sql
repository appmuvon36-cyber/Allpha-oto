
do $$
begin
 if not exists(select 1 from pg_constraint where conrelid='public.oto_orders'::regclass and conname='oto_orders_shipping_address_bounds_check') then
  alter table public.oto_orders add constraint oto_orders_shipping_address_bounds_check check (
   length(btrim(coalesce(shipping_address->>'recipient_name',''))) between 2 and 100
   and length(btrim(coalesce(shipping_address->>'phone',''))) between 6 and 30
   and length(btrim(coalesce(shipping_address->>'address',''))) between 8 and 500
   and length(btrim(coalesce(shipping_address->>'city',''))) <= 100
   and length(btrim(coalesce(shipping_address->>'province',''))) <= 100
   and length(btrim(coalesce(shipping_address->>'postal_code',''))) <= 12
   and length(shipping_address::text) <= 2000
  );
 end if;
end $$;
;
