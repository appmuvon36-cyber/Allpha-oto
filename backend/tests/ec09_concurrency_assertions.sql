do $$
declare v_count integer; v_reserved integer; v_on_hand integer;
begin
 select count(distinct o.id) into v_count from public.oto_orders o join public.oto_order_items i on i.order_id=o.id
 where o.customer_user_id='09000000-0000-4000-8000-000000000001' and i.product_id='09000000-0000-4000-8000-000000000003';
 select reserved,on_hand into v_reserved,v_on_hand from public.inventory_balances where product_id='09000000-0000-4000-8000-000000000003';
 if v_count<>1 then raise exception 'EC-09 concurrent checkout expected exactly one order, found %',v_count; end if;
 if v_reserved<>4 or v_on_hand<>5 then raise exception 'EC-09 concurrent checkout oversold or corrupted inventory (reserved %, on_hand %)',v_reserved,v_on_hand; end if;
 if (select count(*) from public.inventory_reservations where product_id='09000000-0000-4000-8000-000000000003' and status='reserved')<>1 then
  raise exception 'EC-09 concurrent checkout did not create exactly one active reservation';
 end if;
end $$;
select 'EC-09 concurrent checkout reserved stock exactly once without oversell' as result;
