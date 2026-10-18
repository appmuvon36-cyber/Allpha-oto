# Allpha Oto — Implementation Phase Plan

Status: **Planning baseline — not a claim of implementation completion**  
Target repository: `appmuvon36-cyber/Allpha-oto`  
Primary branch: `main`

## Operating rules

1. Inspect before changing: repository, dependencies, deployment configuration, Supabase schema, migrations, policies, and existing data.
2. Keep PostgreSQL/Supabase as the system of record; do not add a second database without an explicit architecture decision.
3. Keep sensitive business rules and privileged operations behind authenticated backend/API functions. The browser must not bypass authorization.
4. Never use demo records as production data. Label fixtures and prototypes clearly.
5. Never claim fitment, price, stock, condition, supplier availability, or payment is verified without evidence.
6. Apply schema changes as reviewed migrations; do not edit production data ad hoc.
7. Work on feature branches and use pull requests with checks; do not push unreviewed changes directly to `main`.

## Phase 00 — Repository and live-environment audit

**Goal:** establish a reliable baseline before scaffolding.

Tasks:
- Record repository tree, branch/commit, package manager, frameworks, lint/test/build scripts, and deployment target.
- Inspect README, agent instructions, environment examples, CI workflows, and secrets references without exposing secret values.
- Inspect Supabase schemas, extensions, tables, indexes, functions, triggers, RLS policies, grants, Storage buckets, Auth settings, and migrations.
- Record differences between repository migrations and live Supabase state.
- Define a baseline architecture decision record and risk list.

Acceptance:
- Audit report references observed files/resources.
- No secrets are committed or copied into reports.
- No migration or production mutation is performed during discovery.
- Any unknowns are marked UNKNOWN, not assumed absent beyond the inspected scope.

## Phase 01 — Product flows and acceptance criteria

- Define customer journey: vehicle selection, part search, fitment confirmation, product detail, cart, checkout, payment evidence, order tracking, return/help.
- Define supplier journey: onboarding, documents, offer submission, stock/price refresh, performance.
- Define operations journey: product review, sourcing request, inventory adjustment, order/payment review, moderation, return/refund.
- Map every action to role, permission, API, state transition, audit event, and failure state.

Acceptance: user-flow diagrams, role/action matrix, lifecycle definitions, and testable acceptance criteria are reviewed.

## Phase 02 — Design system and UI/UX

- Establish semantic color, typography, spacing, radius, elevation, icon, motion, and responsive tokens.
- Create shared primitives: buttons, fields, selects, dialogs, tables, pagination, badges, alerts, toasts, skeletons, empty/error/offline states.
- Design customer PWA and Super Admin separately while preserving shared tokens and interaction rules.
- Validate keyboard navigation, focus visibility, contrast, touch targets, localization, and responsive behavior.

Acceptance: token specification, component inventory, screen specs, and responsive review are complete. Prototype components are not treated as production integration.

## Phase 03 — Application foundation

Only after Phase 00 confirms the appropriate stack:
- Create or align monorepo/apps without overwriting existing work.
- Configure type checking, linting, formatting, test framework, environment validation, and CI.
- Add accessible application shell, routing, error boundaries, logging, and loading patterns.
- Add environment-specific configuration and safe secret handling.

Acceptance: clean install, lint, type check, unit tests, and build pass in CI.

## Phase 04 — Identity and authorization

- Supabase Auth integration and secure session handling.
- Server-side identity validation and role/permission checks.
- RLS policies and grants tested with anonymous, customer, supplier, staff, and admin contexts.
- Staff MFA and audit events for privileged operations.

Acceptance: negative authorization tests demonstrate that users cannot read or mutate data outside their permissions.

## Phase 05 — Catalog and vehicle fitment

- Vehicle make/model/generation/year/variant master data.
- Product/SKU/brand/part-number/condition/grade/packaging data model.
- Evidence-backed fitment records with source, reviewer, and verification status.
- Product lifecycle: DRAFT → REVIEW → APPROVED → PUBLISHED → ARCHIVED; rejected items retain reason and audit history.
- Search, filters, pagination, image rights/consent, and catalog import validation.

Acceptance: no product is presented as fitment-verified or published without required evidence and authorization.

## Phase 06 — Supplier and sourcing

- Supplier onboarding and document review.
- Supplier offers, source URLs/evidence, quote validity, stock timestamp, acquisition costs, and lead time.
- Customer part-request lifecycle and quote comparison.
- Deduplication and source/license review for imported listings.

Acceptance: stale/unverified quotes are clearly labeled; insufficient evidence yields NOT_READY.

## Phase 07 — Inventory and order lifecycle

- Inventory ledger, reservations, adjustments, reconciliation, and low-stock alerts.
- Cart and checkout with server-side price/stock revalidation.
- Order lifecycle, payment evidence, finance verification, fulfillment, cancellation, return/refund.
- Idempotency for checkout, payment verification, refunds, stock mutation, and notifications.

Acceptance: every stock and order transition is atomic, authorized, idempotent where required, and audited.

## Phase 08 — Super Admin operations

- Dashboard and work queues.
- Catalog/SKU management, supplier review, inventory, order/payment review, moderation, returns, roles, audit logs.
- Bulk import/export with validation, preview, row-level errors, and safe retry.
- Destructive or financial actions require explicit confirmation and server authorization.

Acceptance: each screen has permission-based access and complete loading/empty/error/success states.

## Phase 09 — Customer PWA

- Responsive home, search, vehicle selector, product detail, condition/fitment evidence, cart, checkout, order tracking, sourcing request.
- Accessible navigation, installable PWA, offline-safe shell, and carefully scoped caching.
- Never publicly cache sensitive order/payment data or rely on cached stock/prices at checkout.

Acceptance: critical purchase flows work on mobile and desktop with real API responses.

## Phase 10 — AI and search intelligence

- Natural-language parts search and part-number normalization.
- Candidate matching with cited evidence and confidence/uncertainty.
- Human review for risky fitment, price publication, and moderation decisions.
- AI tools use an allowlist and backend-mediated authorization; no unrestricted SQL or secret access.

Acceptance: model output cannot independently publish uncertain data or assert unsupported fitment/prices.

## Phase 11 — Integrations

- WhatsApp/outbox worker, email, supplier feeds, payment gateway when selected, and logistics adapters.
- Webhook signature validation, retry/backoff, idempotency, dead-letter handling, and observability.
- Secrets managed outside source control.

Acceptance: failure/retry scenarios are tested and do not duplicate orders, payments, or notifications.

## Phase 12 — Quality, security, and release

- Unit, integration, RLS/permission, API contract, E2E, accessibility, responsive, performance, and security tests.
- Staging smoke tests, backup/restore drill, migration rollback/forward plan, monitoring, and incident runbook.
- Gradual rollout with explicit release gates.

Acceptance: critical flows pass; no unresolved critical/high security finding; production readiness evidence is attached to release.

## Initial priority

1. Phase 00 audit
2. Phase 01 product flows
3. Phase 02 design system and screen review
4. Phase 03 stack alignment and CI
5. Phase 04 identity/security foundation
6. Phases 05–09 in vertical slices
7. Phases 10–12 as prerequisites and product maturity allow

## Status tracking

Use `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, `IN_REVIEW`, or `DONE`. A phase is `DONE` only when its acceptance criteria are met and evidence is linked. A design prototype or successful build alone does not mean the feature is integrated or production-ready.
