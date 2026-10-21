-- EC-09 competing checkout request; signed quote and stock fixture exist only in disposable CI.
do $ec09_checkout$
declare
 v_customer uuid := '09000000-0000-4000-8000-000000000001';
 v_product uuid := '09000000-0000-4000-8000-000000000003';
 v_signing_key text := 'ec02-ci-secret-not-production';
 v_quoted_at text;
 v_quote jsonb;
 v_quote_message text;
 v_signature text;
 v_payload jsonb;
begin
 v_quoted_at:=to_char(clock_timestamp() at time zone 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"');
 v_quote:=jsonb_build_object('origin_id','ci-origin','destination_id','ci-destination','courier','jne',
  'service','REG','description','EC-09 concurrency quote fixture','cost',12000,'weight_grams',1000,
  'quoted_at',v_quoted_at,'expires_in_seconds',900,'currency','IDR');
 v_quote_message:=v_customer::text||'|'||(v_quote->>'origin_id')||'|'||(v_quote->>'destination_id')||'|'||
  (v_quote->>'courier')||'|'||(v_quote->>'service')||'|'||(v_quote->>'cost')||'|'||
  (v_quote->>'weight_grams')||'|'||(v_quote->>'quoted_at')||'|'||(v_quote->>'expires_in_seconds');
 v_signature:=encode(extensions.hmac(convert_to(v_quote_message,'UTF8'),convert_to(v_signing_key,'UTF8'),'sha256'),'hex');
 v_payload:=jsonb_build_object(
  'items',jsonb_build_array(jsonb_build_object('product_id',v_product::text,'quantity',4)),
  'shipping_fee',12000,'shipping_quote',v_quote||jsonb_build_object('signature',v_signature),
  'shipping_address',jsonb_build_object('recipient_name','EC09 Fixture','phone','081234567890',
   'address','CI-only fixture address','city','Bogor','province','Jawa Barat','postal_code','16120',
   'shipping_quote',v_quote));
 perform set_config('request.jwt.claim.sub',v_customer::text,true);
 perform public.oto_order_mutate('checkout',null,v_payload,'ec09-concurrent-checkout-b');
end
$ec09_checkout$;
