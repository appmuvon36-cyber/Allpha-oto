
create index if not exists inventory_ledger_actor_user_id_idx on public.inventory_ledger(actor_user_id);
create index if not exists inventory_ledger_supplier_id_idx on public.inventory_ledger(supplier_id);
create index if not exists inventory_reservations_product_id_idx on public.inventory_reservations(product_id);
create index if not exists oto_order_items_product_id_idx on public.oto_order_items(product_id);
create index if not exists oto_payment_events_submitted_by_idx on public.oto_payment_events(submitted_by);
create index if not exists oto_payment_events_reviewed_by_idx on public.oto_payment_events(reviewed_by);
create index if not exists oto_returns_customer_user_id_idx on public.oto_returns(customer_user_id);
create index if not exists oto_returns_reviewed_by_idx on public.oto_returns(reviewed_by);
create index if not exists oto_returns_received_by_idx on public.oto_returns(received_by);
create index if not exists oto_return_items_order_item_id_idx on public.oto_return_items(order_item_id);
create index if not exists shopping_cart_items_product_id_idx on public.shopping_cart_items(product_id);
;
