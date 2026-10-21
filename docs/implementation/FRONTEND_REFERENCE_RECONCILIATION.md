# Frontend UI Reference Reconciliation

Date: 2026-10-21
Scope: Customer PWA presentation only. The canonical application remains `appmuvon36-cyber/Allpha-oto` on `main`.

## Reference inspected

- Repository: https://github.com/fadliansyah36/Front-end-UI-Otoclinic
- Stack observed: React 19 + Vite + Tailwind CSS v4, Lucide icons, `vite-plugin-pwa`, and a client-side `AppContext`.
- Useful visual patterns: mobile-first header, compact search, category tiles, bottom navigation, install prompt, safe-area handling, press feedback, product cards, offline status presentation, and responsive layouts.
- Reference-only business state: `src/context/AppContext.tsx` imports `src/data/mockData.ts` for initial products, orders, requests, audit logs, and notifications. Its `App.tsx` also includes a demo Super Admin view and local state mutations. These flows are not authoritative for OtoClinic production.
- Reference package dependencies include `@google/genai`, but the existing production customer PWA does not need to import the reference AI client to render this design.

## Reconciliation decisions

1. Keep the canonical Next.js App Router in `apps/web`; do not migrate the production app to Vite or copy the reference app shell wholesale.
2. Reuse presentation patterns only. Product/category/vehicle/fitment/order/checkout/sourcing data continues to come from existing FastAPI endpoints and Supabase-backed workflows.
3. Keep the current Supabase browser client restricted to the public anon key; protected operations continue to send the customer's session token to FastAPI.
4. Preserve existing product detail, cart, checkout redirect, account/order, sourcing, supplier, WhatsApp handoff, and PWA service-worker routes. No API, database, RLS, or Super Admin source was changed by this UI pass.
5. Keep the existing manifest and service worker policy. The service worker caches the app shell/static same-origin assets and must not cache API responses or private order/payment data.
6. Preserve honest catalog states: empty collections for best-seller, popularity, promo, or ads remain empty until their corresponding real data/integration exists. Do not add sample products, prices, discounts, ratings, stock, or fitment claims.
7. Apply the existing OtoClinic tokens: navy `#101B2B`, action orange `#EF5B2A`, canvas `#F5F6F8`, surface `#FFFFFF`, and border `#E2E8F0`.

## Changes in this pass

- Added a scoped presentation layer in `apps/web/src/app/globals.css` for touch behavior, visible focus, reduced motion, safe-area bottom navigation, hero/promo surface, category tiles, product cards, collection shelves, and sourcing panel.
- Applied presentation classes to the existing homepage hero, categories, catalog cards, collection shelves, header, sourcing panel, and bottom navigation. Existing data loading and action handlers were left intact.
- No new dependencies, schemas, endpoints, or production data were introduced.

## Verification status

- Source and repository structure inspected: yes.
- Reference code audited for mock/demo coupling: yes.
- Local lint/typecheck/build executed in this pass: no.
- GitHub CI after the commit: pending until workflow status is inspected.
- Railway live deployment of this exact commit: not yet verified.
- Authenticated end-to-end and interactive viewport QA: still required; do not infer success from a build or HTTP 200 alone.

## Next phase

Complete Phase 09 UI/UX QA gate: inspect CI results, verify the exact deployed commit and existing routes, and run responsive/interactions/accessibility checks at 360, 390, 820, and 1440 px. Continue to Phase 10 only after the required gate is closed.
