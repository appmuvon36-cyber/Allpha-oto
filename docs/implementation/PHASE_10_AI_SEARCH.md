# Phase 10 — AI & Search Intelligence

**Status:** IN PROGRESS — first deterministic search slice committed to `main`.  
**Owner decision:** EC-09 accepted for phase progression under the 21 Oct 2026 QA waiver; authenticated production transaction checks remain deferred to Phase 12.

## Implemented slice

- Public read-only endpoint: `GET /v1/search/parts?q=<query>&limit=<1..20>`.
- Uses the existing FastAPI service and existing Supabase `products` and `product_fitments` data. No new database, search service, or schema migration.
- Candidate retrieval filters to `products.status = published`; fitment evidence is restricted to `product_fitments.status = verified`.
- Part-number normalization removes formatting punctuation and uppercases identifiers. It does not infer that two different identifiers are semantically interchangeable.
- Deterministic ranking prioritizes exact normalized part number, exact SKU, exact name, partial identifiers, and text-token overlap.
- Results include reasons, verified fitment rows, explicit uncertainty, and a warning that the heuristic score is not a probability. The endpoint does not assert stock or shipping validity and does not make any product/fitment publication decision.
- Empty catalog remains empty. No mock listings, prices, inventory, fitments, or user activity are generated.

## Initial automated coverage

`backend/tests/test_phase10_search.py` covers normalization, exact-versus-partial ranking, published-only product query constraints, verified-only fitment evidence, invalid normalized query rejection, and honest empty results. This is a source/CI test specification until the CI run for the new commit reports its result.

## Follow-on Phase 10 work

1. Add synonym and OEM/aftermarket cross-reference matching only when a trusted mapping source and evidence are available.
2. Add vehicle-aware candidate ranking that separates verified fitment from textual similarity and never upgrades an unverified fitment to verified.
3. Add catalog-backed query analytics with privacy-safe aggregation; do not log access tokens, contact details, or raw private user content.
4. Consider embeddings/LLM reranking only after an explicit provider/model configuration, cost/latency limits, prompt-injection-safe handling of catalog text, and deterministic fallback are designed.
5. Keep candidate confidence explainable; AI suggestions must never publish or change price, condition, stock, payment status, or fitment without an authorized workflow.

## Deferred release checks

Authenticated customer/staff E2E, production transaction journeys, full viewport/accessibility QA, and external provider delivery remain Phase 12 tasks. Their deferral is not evidence that they passed.
