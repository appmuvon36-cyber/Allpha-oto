# OtoClinic — MagicPath UI/UX Handoff

## Existing plugin project
- Project: **Allpha Oto — Premium Spare Parts UI/UX**
- MagicPath project ID: `462564795376340992`
- Open the project through MagicPath's project canvas in the connected account.

## Created components
| Screen/artifact | MagicPath generated name | Purpose |
|---|---|---|
| Customer Homepage & Smart Parts Finder | `friendly-ocean-4932` | Customer marketplace home, vehicle selector, part search, categories, product cards, sourcing CTA |
| Super Admin Operations Dashboard | `bold-air-1063` | Operational overview, catalog/supplier/inventory metrics, latest products |
| Design System Foundations | `dreamily-park-9006` | Color tokens, typography, spacing, controls, responsive and status patterns |

## Design tokens
- Ink/navy: `#101B2B`
- Action orange: `#EF5B2A`
- Canvas: `#F5F6F8`
- Surface: `#FFFFFF`
- Border: `#E2E8F0`
- Muted: `#64748B`
- Success: `#047857`
- Warning: `#B45309`
- Danger: `#B91C1C`
- 4px spacing base; body 14–16px; minimum interactive target 40–44px; responsive breakpoints: mobile 360–767, tablet 768–1023, desktop 1024+.

## Integration requirements
1. Treat these components as the accepted visual reference; reconcile with `apps/web` and `apps/admin` instead of creating a second design language.
2. Keep OtoClinic brand name. Replace prototype-only static product arrays and hard-coded KPI with actual API/Supabase data. If no approved records exist, render a clear empty state.
3. Customer UI: real search, make/model/year from vehicle taxonomy, real product details, condition, warranty, verified fitment evidence and stock freshness.
4. Admin UI: session verification, role denial, real authorized queries, audit context, explicit loading/error/empty states. Client checks are not the security boundary.
5. Use existing Tailwind/design tokens and the current project dependencies. Before installing MagicPath-generated code, inspect its dependencies and remove unused helper code.
6. Do not publish prototype values/prices, sample vehicle options, demo metrics, or claims of verified fitment as live data.
7. Test keyboard focus, accessible names, mobile layout, empty/error states, reduced motion, and direct navigation to each route.

## Important known limitation
The MagicPath customer component contains sample product records and notices that the content is a prototype. It is a visual reference only until wired to production data. The Super Admin screen also must be checked for role enforcement and must not expose protected records before authorization.

## Production integration progress — 19 October 2026
- Customer PWA source now includes a category-first mobile section whose actions drive the existing live API search; vehicle selectors and product/catalog states remain backed by FastAPI.
- Super Admin source includes quick navigation to existing operational routes. Metrics remain fetched through the authenticated overview endpoint.
- The MagicPath sample product/KPI arrays are not copied into production. Prototype remains visual reference; no product, stock, price, fitment, or audit records are fabricated.
- Source integration commits are recorded in `docs/implementation/PHASES.md`. Production deployment and responsive QA remain pending until checked against the exact latest commit.
