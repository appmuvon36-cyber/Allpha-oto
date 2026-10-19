# UI/UX Refactor QA — 19 October 2026

Status: **PARTIAL — responsive screenshots and public-route smoke collected; interactive browser QA and authenticated role/session matrix remain open.**

## Scope and safety
- Canonical repository: `appmuvon36-cyber/Allpha-oto`, branch `main`.
- Production URLs: Customer Web `https://otoclinic-web-production.up.railway.app`; Admin `https://otoclinic-admin-production.up.railway.app`; API `https://otoclinic-api-production.up.railway.app`.
- No production writes, order submissions, user mutations, or fake data were created as part of this QA.
- Public catalog and vehicle taxonomy are currently empty; empty-state behavior is expected and not a reason to seed production.

## Responsive screenshot evidence
Firecrawl screenshot captures were collected with requested viewport sizes. These confirm the route rendered and a screenshot was produced; they do **not** independently prove zero horizontal overflow or complete accessibility.

### Customer homepage
- [360 × 900](https://storage.googleapis.com/firecrawl-scrape-media/screenshot-90275f05-99e6-44b6-80d1-ffdd8537f149.png)
- [390 × 900](https://storage.googleapis.com/firecrawl-scrape-media/screenshot-ea4e9a99-6f6f-49de-b86d-c44f22531d8e.png)
- [820 × 900](https://storage.googleapis.com/firecrawl-scrape-media/screenshot-e9a89c9d-7e94-4720-adec-eb942caab4ef.png)
- [1440 × 900](https://storage.googleapis.com/firecrawl-scrape-media/screenshot-32f9d41d-5e53-444d-b7e4-808ea58ab550.png)

### Admin login (unauthenticated safe state)
- [360 × 900](https://storage.googleapis.com/firecrawl-scrape-media/screenshot-c42f0e24-784f-4d54-91f3-e60abb77ef8b.png)
- [390 × 900](https://storage.googleapis.com/firecrawl-scrape-media/screenshot-8cda1401-ed32-433c-852a-dcf14a8b171e.png)
- [820 × 900](https://storage.googleapis.com/firecrawl-scrape-media/screenshot-dd565a52-df17-459e-8767-4fe11724d018.png)
- [1440 × 900](https://storage.googleapis.com/firecrawl-scrape-media/screenshot-54f0234b-f82c-44ab-a43d-8384a86cecc7.png)

Screenshot links are temporary signed evidence URLs and may expire.

## Public smoke checks
| Route / behavior | Observed result | Assessment |
|---|---|---|
| Customer `/` | HTTP 200; homepage and “Cari berdasarkan kategori” rendered | Pass |
| Customer category section | Present in production HTML; category buttons are wired to set the existing search query in source | Static smoke pass; click behavior still needs interactive browser confirmation |
| `GET /v1/vehicles/makes` | HTTP 200, `items=[]`, `count=0` | Empty state expected; cannot exercise make/model/variant selection without real taxonomy rows |
| `GET /v1/catalog/products?limit=3` | HTTP 200, empty result | Empty catalog state expected; no fake products inserted |
| `/products/not-a-uuid` | HTTP 200 page with unavailable/not-found state | Pass for safe UI fallback |
| `/cart` unauthenticated | HTTP 200; sign-in-required checkout flow | Pass |
| `/checkout` before fix | HTTP 404 | Defect found; fixed by adding a server-side redirect to the existing authenticated cart/checkout flow. Must verify after the fix deployment becomes live. |
| `/account` unauthenticated | HTTP 200; customer sign-in screen | Pass |
| `/orders/not-a-uuid` unauthenticated | HTTP 200; sign-in-required state | Pass |
| Admin `/catalog`, `/suppliers`, `/inventory-orders`, `/users`, `/audit` unauthenticated | Each redirected to `/login` (final HTTP 200) | Pass for unauthenticated route guard |
| `GET /v1/admin/overview` without token | HTTP 401 | Pass |
| `GET /v1/orders?limit=1` without token | HTTP 401 | Pass |

## Live data baseline observed
- Vehicle makes: 0
- Public catalog products: 0
- These results are consistent with the existing no-seed policy. They prevent a full positive-path check of vehicle selection, product-to-cart, and authenticated checkout in this production environment.

## Follow-up required before marking refactor complete
1. Verify the new `/checkout` redirect after the matching Web deployment is SUCCESS and live.
2. Run real browser interaction tests at 360, 390, 820, and 1440 widths, recording horizontal overflow, console/page errors, category/search interaction, keyboard/focus, and back/forward navigation. Screenshot generation alone is not a pass for these checks.
3. With an explicitly approved test customer and test staff identities, exercise sign-in, product/cart/checkout/order paths, role-allowed and role-denied screens, and ownership/IDOR checks. No real user session was available/used for this pass.
4. For all admin modules, repeat route/data loading checks with the appropriate staff role. Unauthenticated redirect tests do not prove the authorized experience.
5. Re-run the relevant CI/build workflow for the exact latest source commit and confirm the final Web/Admin deployments. Do not close the gate until the above evidence is recorded.

## Current verdict
**Not yet fully passed.** Public smoke and screenshot capture are documented, one direct-checkout 404 was found and fixed in source, and authenticated/interactive checks remain outstanding. Phase 10 remains deferred until this QA gate is closed.
