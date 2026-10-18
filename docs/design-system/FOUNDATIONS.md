# Allpha Oto — Design System Foundations v1

Status: **Proposed visual baseline**. Reconcile these tokens with the actual application stack and any existing styles before production use.

## Brand and experience

- Product: Indonesian automotive spare-parts marketplace and operations platform.
- Customer surface: confident, useful, product-first; emphasize vehicle fitment, item condition, stock freshness, warranty, and clear pricing.
- Admin surface: light, information-dense but readable; optimized for repeat operational work.
- Avoid generic gradients, excessive shadows, nested cards, noisy badges, and decorative animation.
- Use Indonesian as the default product language; currency is IDR and numbers follow Indonesian formatting.

## Color tokens

| Token | Value | Intended use |
|---|---|---|
| `color.ink` | `#101B2B` | Primary navigation, headings, dark surfaces |
| `color.action` | `#EF5B2A` | Primary action, active navigation, key highlights |
| `color.canvas` | `#F5F6F8` | Application background |
| `color.surface` | `#FFFFFF` | Cards, tables, menus, dialogs |
| `color.border` | `#E2E8F0` | Inputs, dividers, table separators |
| `color.text` | `#17202A` | Main body and headings |
| `color.muted` | `#64748B` | Secondary copy and helper text |
| `color.success` | `#047857` | Successful and published states |
| `color.warning` | `#B45309` | Review queues and attention states |
| `color.danger` | `#B91C1C` | Critical errors and destructive actions |
| `color.info` | `#1D4ED8` | Informational states |

Use semantic token names in code instead of repeating raw values. Status meaning must always be expressed in text, not color alone.

## Typography

- Prefer Inter or a system sans-serif stack; use no more than two font families.
- Body: 14–16 px, line-height 1.45–1.6.
- Small/helper: 12 px, line-height 1.5; do not use for essential purchase information.
- H1: 28–36 px; H2: 20–24 px; H3: 16–18 px.
- Keep long-form copy around 60–75 characters per line where practical.
- Use tabular numerals for prices, quantities, IDs, and metrics.

## Spacing, radius, elevation

- Base spacing unit: 4 px.
- Common spacing: 4, 8, 12, 16, 24, 32, 40, 48 px.
- Inputs and controls: 10–12 px radius; cards and major surfaces: 12–16 px radius.
- Prefer alignment, whitespace, and dividers over card borders and shadows.
- Use elevation only when needed to communicate overlays or interaction hierarchy.

## Interaction and components

Required shared components:
- Button: primary, secondary, tertiary, danger, loading, disabled.
- Input, search input, select, combobox, checkbox, radio, date picker.
- Badge/status, alert, toast, tooltip, dialog, drawer, popover.
- Table, sortable header, pagination, filter bar, bulk-action bar.
- Skeleton, empty state, error state, offline state, retry action.
- Product card, fitment status, condition label, price block, stock freshness indicator.
- Confirm-action dialog for sensitive or irreversible actions.

Rules:
- Target sizes should generally be at least 40–44 px, especially on mobile.
- Every interactive element needs visible keyboard focus and accessible names.
- Forms need persistent labels, validation text, and field-level error states.
- Destructive, financial, inventory, moderation, and publishing actions need confirmation and server-side authorization.
- Tables must support narrow screens via deliberate horizontal scrolling or a mobile list pattern.
- Loading, empty, error, success, offline, and permission-denied states are part of the design, not afterthoughts.

## Responsive behavior

- Mobile (360–767 px): one-column layouts, collapsible navigation, filters in drawers, touch-first controls, product details stacked.
- Tablet (768–1023 px): two-column layouts where useful; collapsible admin navigation.
- Desktop (1024 px+): persistent admin navigation, full data tables, constrained content width.
- Breakpoints should be applied consistently and tested on real device widths.
- Motion should be subtle and respect reduced-motion preferences.

## Spare-part trust requirements

Product cards and detail pages must distinguish:
- New OEM, new aftermarket, used/copotan, refurbished/rekondisi, remanufactured, and damaged/for-parts.
- Condition grade and inspection evidence where relevant.
- Vehicle fitment status: verified, partial/needs review, or unverified.
- Stock status and last-confirmed timestamp.
- Warranty/return terms, quantity/package contents, and seller/source.
- Listing images may only be published when usage rights/permission are established.

Do not compare prices across mismatched vehicle variants, part numbers, conditions, package quantities, or warranty terms. If comparable evidence is insufficient, show NOT_READY for pricing recommendation.

## Frontend implementation guidance

Use shared design tokens and reusable accessible components. shadcn/ui and Tailwind CSS are candidate tools, not assumed dependencies: inspect the repository before adopting them. Avoid introducing a second UI framework or duplicate component libraries without an architecture decision.

## Design QA checklist

- [ ] Visual hierarchy is clear at mobile and desktop widths.
- [ ] Text and interactive states meet contrast expectations.
- [ ] Focus order and keyboard interaction work.
- [ ] Form labels, validation, and error messages are understandable.
- [ ] Loading, empty, error, success, offline, and permission states are covered.
- [ ] Product condition and fitment status cannot be confused.
- [ ] No sample price, stock, order, or KPI is represented as live data.
- [ ] Sensitive data is not exposed in screenshots, logs, or public cache.
