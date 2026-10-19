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

-- Privileged weight update: only active catalog staff may set a positive package weight.
create or replace function public.oto_product_set_shipping_weight(p_product_id uuid, p_weight_grams integer, p_request_id text)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public' as $function$
declare
  actor uuid := auth.uid();
  actor_role public.oto_user_role;
  active boolean;
  existing public.audit_logs%rowtype;
  result jsonb;
begin
  if actor is null then raise exception using errcode='42501', message='authentication_required'; end if;
  select role,is_active into actor_role,active from public.user_profiles where id=actor;
  if not found or active is distinct from true or actor_role not in ('admin'::public.oto_user_role,'catalog_editor'::public.oto_user_role) then
    raise exception using errcode='42501', message='catalog_role_required';
  end if;
  if p_product_id is null or p_weight_grams is null or p_weight_grams < 1 or p_weight_grams > 1000000 then
    raise exception using errcode='22023', message='shipping_weight_invalid';
  end if;
  if p_request_id is null or length(btrim(p_request_id)) < 8 or length(p_request_id) > 128 then
    raise exception using errcode='22023', message='request_id_invalid';
  end if;
  perform pg_advisory_xact_lock(hashtextextended(actor::text || ':' || p_request_id,0));
  select * into existing from public.audit_logs where actor_user_id=actor and request_id=p_request_id limit 1;
  if found then
    if existing.details->>'action' is distinct from 'set_shipping_weight'
       or existing.details->'payload' is distinct from jsonb_build_object('weight_grams',p_weight_grams)
       or existing.details->'target_id' is distinct from to_jsonb(p_product_id) then
      raise exception using errcode='22023', message='request_id_reused_for_different_operation';
    end if;
    return jsonb_set(coalesce(existing.details->'result','{}'::jsonb),'{replayed}','true'::jsonb,true);
  end if;
  update public.products set weight_grams=p_weight_grams, updated_by=actor, updated_at=now() where id=p_product_id returning id into p_product_id;
  if not found then raise exception using errcode='P0002', message='product_not_found'; end if;
  result := jsonb_build_object('product_id',p_product_id,'weight_grams',p_weight_grams,'replayed',false);
  insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
  values(actor,'catalog_set_shipping_weight','product',p_product_id,p_request_id,jsonb_build_object('action','set_shipping_weight','payload',jsonb_build_object('weight_grams',p_weight_grams),'target_id',to_jsonb(p_product_id),'result',result));
  return result;
end;$function$;
revoke all on function public.oto_product_set_shipping_weight(uuid,integer,text) from public, anon;
grant execute on function public.oto_product_set_shipping_weight(uuid,integer,text) to authenticated;
