-- EC-02: bind the signed provider quote weight to the exact immutable order-item quantities.
-- The API signs and refreshes the quote; this deferred constraint closes the cart/weight
-- race between quote calculation and the transactional order snapshot.
CREATE OR REPLACE FUNCTION public.oto_validate_checkout_shipping_weight()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
  target_order_id uuid;
  address_snapshot jsonb;
  quote_weight integer;
  item_count integer;
  invalid_weight_count integer;
  expected_weight bigint;
BEGIN
  IF TG_OP = 'DELETE' THEN
    target_order_id := OLD.order_id;
  ELSE
    target_order_id := NEW.order_id;
  END IF;

  SELECT o.shipping_address
    INTO address_snapshot
    FROM public.oto_orders AS o
   WHERE o.id = target_order_id;

  -- Preserve compatibility for legacy orders created before signed shipping quotes.
  IF NOT FOUND OR jsonb_typeof(address_snapshot->'shipping_quote') IS DISTINCT FROM 'object' THEN
    RETURN NULL;
  END IF;

  BEGIN
    quote_weight := NULLIF(address_snapshot->'shipping_quote'->>'weight_grams', '')::integer;
  EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'shipping_quote_weight_invalid';
  END;

  SELECT count(*)::integer,
         count(*) FILTER (WHERE p.weight_grams IS NULL OR p.weight_grams < 1)::integer,
         coalesce(sum(p.weight_grams::bigint * oi.quantity), 0)::bigint
    INTO item_count, invalid_weight_count, expected_weight
    FROM public.oto_order_items AS oi
    JOIN public.products AS p ON p.id = oi.product_id
   WHERE oi.order_id = target_order_id;

  IF item_count < 1
     OR invalid_weight_count > 0
     OR quote_weight IS NULL
     OR quote_weight < 1
     OR expected_weight <> quote_weight THEN
    RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'shipping_quote_weight_mismatch';
  END IF;

  RETURN NULL;
END;
$function$;

REVOKE ALL ON FUNCTION public.oto_validate_checkout_shipping_weight() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS oto_order_item_shipping_weight_guard ON public.oto_order_items;
CREATE CONSTRAINT TRIGGER oto_order_item_shipping_weight_guard
AFTER INSERT OR UPDATE OR DELETE ON public.oto_order_items
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION public.oto_validate_checkout_shipping_weight();
