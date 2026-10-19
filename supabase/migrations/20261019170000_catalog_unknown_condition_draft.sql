-- Allow incomplete marketplace candidates to be stored as drafts without misrepresenting condition.
-- A separate additive constraint migration gates any review/approval/publication while condition is unknown.
ALTER TYPE public.oto_product_condition ADD VALUE IF NOT EXISTS 'unknown';
