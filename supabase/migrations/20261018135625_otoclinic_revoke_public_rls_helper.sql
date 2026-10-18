-- Applied to the live OtoClinic Supabase project on 2026-10-18.
-- The event-trigger helper must not be callable as an exposed PostgREST RPC.
revoke execute on function public.rls_auto_enable() from public, anon, authenticated;
