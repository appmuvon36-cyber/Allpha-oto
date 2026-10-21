-- EC-07: auditable manual customer-contact history for existing orders.
-- No message is sent by this table/RPC; outcomes are staff-recorded observations.
create table if not exists public.oto_order_communications (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.oto_orders(id) on delete restrict,
  actor_user_id uuid not null references auth.users(id) on delete restrict,
  channel text not null check (channel in ('whatsapp','phone','email','internal_note')),
  direction text not null check (direction in ('outbound','inbound','internal')),
  outcome text not null check (outcome in ('planned','attempted','sent','received','failed','not_sent')),
  summary text not null check (length(btrim(summary)) between 2 and 2000),
  external_reference text check (external_reference is null or length(external_reference) <= 300),
  created_at timestamptz not null default now()
);

create index if not exists oto_order_communications_order_created_idx
  on public.oto_order_communications(order_id, created_at desc);

alter table public.oto_order_communications enable row level security;

drop policy if exists "order communications order staff read" on public.oto_order_communications;
create policy "order communications order staff read"
  on public.oto_order_communications
  for select
  to authenticated
  using (public.oto_has_staff_role(array['admin','order_manager']::public.oto_user_role[]));

revoke all on table public.oto_order_communications from anon;
revoke insert, update, delete, truncate, references, trigger on table public.oto_order_communications from authenticated;
grant select on table public.oto_order_communications to authenticated;

create or replace function public.oto_order_communication_add(
  p_order_id uuid,
  p_payload jsonb,
  p_request_id text
) returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $function$
declare
  a uuid := auth.uid();
  v_order_id uuid;
  v_channel text;
  v_direction text;
  v_outcome text;
  v_summary text;
  v_reference text;
  v_fingerprint text;
  v_previous public.oto_idempotency_records%rowtype;
  v_record public.oto_order_communications%rowtype;
  v_result jsonb;
begin
  if a is null then raise exception using errcode='42501',message='authentication_required'; end if;
  if not public.oto_has_staff_role(array['admin','order_manager']::public.oto_user_role[]) then
    raise exception using errcode='42501',message='order_role_required';
  end if;
  if p_request_id is null or length(btrim(p_request_id))<8 or length(p_request_id)>128 then
    raise exception using errcode='22023',message='idempotency_key_invalid';
  end if;
  if p_payload is null or jsonb_typeof(p_payload)<>'object' then
    raise exception using errcode='22023',message='communication_payload_invalid';
  end if;

  v_channel := nullif(btrim(p_payload->>'channel'),'');
  v_direction := nullif(btrim(p_payload->>'direction'),'');
  v_outcome := nullif(btrim(p_payload->>'outcome'),'');
  v_summary := nullif(btrim(p_payload->>'summary'),'');
  v_reference := nullif(btrim(p_payload->>'external_reference'),'');
  if v_channel is null or v_channel not in ('whatsapp','phone','email','internal_note')
     or v_direction is null or v_direction not in ('outbound','inbound','internal')
     or v_outcome is null or v_outcome not in ('planned','attempted','sent','received','failed','not_sent')
     or v_summary is null or length(v_summary)>2000
     or (v_reference is not null and length(v_reference)>300) then
    raise exception using errcode='22023',message='communication_payload_invalid';
  end if;

  select id into v_order_id from public.oto_orders where id=p_order_id;
  if not found then raise exception using errcode='P0002',message='order_not_found'; end if;

  v_fingerprint := encode(extensions.digest('order_communication_add:'||p_order_id::text||':'||p_payload::text,'sha256'),'hex');
  perform pg_advisory_xact_lock(hashtextextended(a::text||':'||p_request_id,0));
  select * into v_previous from public.oto_idempotency_records
   where actor_user_id=a and request_id=p_request_id;
  if found then
    if v_previous.action<>'order_communication_add'
       or v_previous.target_id is distinct from p_order_id
       or v_previous.payload_fingerprint<>v_fingerprint then
      raise exception using errcode='23505',message='idempotency_key_payload_conflict';
    end if;
    return v_previous.result || jsonb_build_object('replayed',true);
  end if;

  insert into public.oto_order_communications(
    order_id,actor_user_id,channel,direction,outcome,summary,external_reference
  ) values (
    p_order_id,a,v_channel,v_direction,v_outcome,v_summary,v_reference
  ) returning * into v_record;

  v_result := jsonb_build_object('communication',to_jsonb(v_record),'replayed',false);
  insert into public.oto_idempotency_records(actor_user_id,request_id,action,target_id,payload_fingerprint,result)
  values(a,p_request_id,'order_communication_add',p_order_id,v_fingerprint,v_result);
  insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
  values(a,'order_communication_add','order_communication',v_record.id,p_request_id,
    jsonb_build_object('order_id',p_order_id,'channel',v_channel,'direction',v_direction,'outcome',v_outcome));
  return v_result;
end;
$function$;

revoke all on function public.oto_order_communication_add(uuid,jsonb,text) from public, anon;
grant execute on function public.oto_order_communication_add(uuid,jsonb,text) to authenticated;
