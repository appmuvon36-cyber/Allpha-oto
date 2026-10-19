-- EC-02: store the real product package weight used by RajaOngkir.
-- Nullable for existing records; quote calculation rejects missing/invalid weights.
alter table public.products add column if not exists weight_grams integer;
do $$
begin
  if not exists (select 1 from pg_constraint where conrelid = 'public.products'::regclass and conname = 'products_weight_grams_positive_check') then
    alter table public.products add constraint products_weight_grams_positive_check check (weight_grams is null or weight_grams > 0) not valid;
  end if;
end $$;

alter table public.oto_orders drop constraint if exists oto_orders_shipping_fee_unconfigured_check;
