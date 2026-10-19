-- Unknown-condition marketplace candidates must remain drafts until a staff member verifies condition.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'products_condition_known_before_review'
      AND conrelid = 'public.products'::regclass
  ) THEN
    ALTER TABLE public.products
      ADD CONSTRAINT products_condition_known_before_review
      CHECK (
        status::text NOT IN ('review', 'approved', 'published')
        OR condition::text <> 'unknown'
      ) NOT VALID;
  END IF;
END $$;

ALTER TABLE public.products VALIDATE CONSTRAINT products_condition_known_before_review;
