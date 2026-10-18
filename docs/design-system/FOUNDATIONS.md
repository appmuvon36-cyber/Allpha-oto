# OtoClinic Design System — Foundations v1

Status: initial implementation baseline. Keep brand name exactly **OtoClinic**.

## Experience goals
- Trustworthy, practical, mobile-first automotive spare-parts shopping.
- Admin surfaces optimize operational clarity, fast scanning, and low error rates.
- Use Indonesian language and IDR formatting by default.
- Avoid overdecorated gradients, excessive shadows, generic AI visuals, and invented metrics.

## Color tokens
| Token | Hex | Use |
|---|---|---|
| `--color-ink` | `#101B2B` | Headings/navigation |
| `--color-primary` | `#EF5B2A` | Main action/active state |
| `--color-canvas` | `#F5F6F8` | App background |
| `--color-surface` | `#FFFFFF` | Content surfaces |
| `--color-border` | `#E2E8F0` | Borders/dividers |
| `--color-muted` | `#64748B` | Helper text |
| `--color-success` | `#047857` | Confirmed states |
| `--color-warning` | `#B45309` | Review/attention |
| `--color-danger` | `#B91C1C` | Critical/destructive |
| `--color-info` | `#1D4ED8` | Informational |

## Typography
- Inter when available, otherwise system sans-serif.
- Body 14–16px, line height 1.45–1.6.
- Small/helper 12px; never use for essential condition, fitment, warranty or price.
- Page title 28–36px; section title 20–24px.
- Use tabular numerals for price, quantities and IDs.

## Spacing and shape
- 4px base spacing unit; common values 4/8/12/16/24/32/40/48px.
- Inputs 10–12px radius; major surfaces 12–16px.
- Prefer whitespace and alignment to excessive card shadows.
- Interactive targets generally 40–44px minimum.

## Components
Buttons (primary/secondary/danger/loading/disabled), form controls, badges, alerts, toast, dialog, drawer, table, pagination, filters, skeleton, empty/error/offline state, product card, fitment state, condition label, stock freshness, confirmation dialog.

## Product trust rules
Explicitly distinguish new OEM, new aftermarket, used/copotan, refurbished/rekondisi, remanufactured, and damaged-for-parts. Show fitment evidence/status, stock freshness, warranty/returns, package quantity and source. Never claim fitment verified without evidence. Do not publish supplier photos without rights evidence. Do not compare unlike vehicle variants, part numbers, condition, or package quantities.

## Responsive
- Mobile 360–767px: one column, drawer filters, touch-first controls.
- Tablet 768–1023px: compact two-column layouts and collapsible navigation.
- Desktop 1024px+: persistent admin nav and full tables.
- Tables need a deliberate mobile list or horizontal-scroll pattern.
- Honor reduced motion and visible keyboard focus.

## Accessibility and states
Persistent labels; clear validation; keyboard operation; accessible names; status text not color alone; loading, empty, error, success, offline and permission-denied states are first-class. Destructive/financial/inventory actions need confirmation and server-side permission checks.
