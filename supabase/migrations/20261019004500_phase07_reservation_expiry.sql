
create or replace function public.oto_expire_reservations(p_request_id text)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public' as $function$
declare
 a uuid:=auth.uid(); r public.oto_user_role; active boolean;
 old public.oto_idempotency_records%rowtype; o public.oto_orders%rowtype; res public.inventory_reservations%rowtype;
 cancelled_ids jsonb:='[]'::jsonb; released_count integer:=0; order_count integer:=0; b public.inventory_balances%rowtype;
 fp text:=md5('expire_reservations::{}'); out jsonb;
begin
 if a is null then raise exception using errcode='42501',message='authentication_required'; end if;
 select role,is_active into r,active from public.user_profiles where id=a;
 if not found or active is distinct from true then raise exception using errcode='42501',message='active_profile_required'; end if;
 if r not in ('admin'::public.oto_user_role,'inventory_manager'::public.oto_user_role,'order_manager'::public.oto_user_role) then raise exception using errcode='42501',message='inventory_role_required'; end if;
 if p_request_id is null or length(btrim(p_request_id))<8 or length(p_request_id)>128 then raise exception using errcode='22023',message='request_id_invalid'; end if;
 perform pg_advisory_xact_lock(hashtextextended(a::text||':'||p_request_id,0));
 select * into old from public.oto_idempotency_records where actor_user_id=a and request_id=p_request_id for update;
 if found then
  if old.action<>'expire_reservations' or old.target_id is not null or old.payload_fingerprint<>fp then raise exception using errcode='22023',message='request_id_reused_for_different_operation'; end if;
  return jsonb_set(old.result,'{replayed}','true'::jsonb,true);
 end if;
 for o in
  select ord.* from public.oto_orders ord
  where ord.status='pending_payment'
    and exists(select 1 from public.inventory_reservations ir where ir.order_id=ord.id and ir.status='reserved' and ir.expires_at<=now())
  order by ord.id for update skip locked
 loop
  for res in select * from public.inventory_reservations where order_id=o.id and status='reserved' order by product_id for update loop
   update public.inventory_balances set reserved=reserved-res.quantity,updated_at=now()
    where product_id=res.product_id and reserved>=res.quantity returning * into b;
   if not found then raise exception using errcode='23514',message='reservation_balance_inconsistent'; end if;
   update public.inventory_reservations set status='released',updated_at=now() where id=res.id;
   insert into public.inventory_ledger(product_id,movement,quantity_delta,reference_type,reference_id,reason,actor_user_id)
    values(res.product_id,'release',-res.quantity,'order',o.id,'Checkout reservation expired',a);
   released_count:=released_count+1;
  end loop;
  update public.oto_orders set status='cancelled',cancelled_at=now(),updated_at=now() where id=o.id;
  cancelled_ids:=cancelled_ids||jsonb_build_array(o.id);
  order_count:=order_count+1;
 end loop;
 out:=jsonb_build_object('cancelled_orders',order_count,'released_reservations',released_count,'order_ids',cancelled_ids,'replayed',false);
 insert into public.oto_idempotency_records(actor_user_id,request_id,action,target_id,payload_fingerprint,result)
 values(a,p_request_id,'expire_reservations',null,fp,out);
 insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
 values(a,'expire_reservations','inventory_reservation',null,p_request_id,
   jsonb_build_object('cancelled_orders',order_count,'released_reservations',released_count,'order_ids',cancelled_ids));
 return out;
end;$function$;
revoke all on function public.oto_expire_reservations(text) from public,anon;
grant execute on function public.oto_expire_reservations(text) to authenticated;
;
