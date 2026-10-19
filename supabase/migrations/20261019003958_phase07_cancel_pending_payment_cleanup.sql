
create or replace function public.oto_cancel_pending_payments_on_order_cancel()
returns trigger language plpgsql security definer set search_path to 'pg_catalog','public' as $function$
begin
 if new.status='cancelled' and old.status is distinct from 'cancelled' then
  update public.oto_payment_events
   set status='rejected',reviewed_by=auth.uid(),reviewed_at=now(),review_note='Order cancelled before payment verification',updated_at=now()
   where order_id=new.id and event_type='payment' and status='pending_review';
 end if;
 return new;
end;$function$;
drop trigger if exists oto_cancel_pending_payments_on_order_cancel on public.oto_orders;
create trigger oto_cancel_pending_payments_on_order_cancel
after update of status on public.oto_orders
for each row execute function public.oto_cancel_pending_payments_on_order_cancel();
revoke all on function public.oto_cancel_pending_payments_on_order_cancel() from public,anon,authenticated;
;
