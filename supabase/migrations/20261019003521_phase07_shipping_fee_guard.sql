
do $$
begin
 if not exists(select 1 from pg_constraint where conrelid='public.oto_orders'::regclass and conname='oto_orders_shipping_fee_unconfigured_check') then
  alter table public.oto_orders add constraint oto_orders_shipping_fee_unconfigured_check check (shipping_fee=0);
 end if;
end $$;
;
