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


## Latest verification update — 19 October 2026, after deployment of commit `4bd88b6f1121769e2b4662471c56348ee9d7d870`

### Deployment and CI evidence
- Web deployment `ab5603ca-2f22-44eb-9acc-b040eb9f70e7`: **SUCCESS**, commit `4bd88b6f1121769e2b4662471c56348ee9d7d870`, branch `main`.
- Admin deployment `245666ac-6991-4d31-9112-a6a3dc3f7751`: **SUCCESS**, commit `4bd88b6f1121769e2b4662471c56348ee9d7d870`, branch `main`.
- GitHub Actions [OtoClinic CI run #281](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39186898533) for `4bd88b6`: **completed successfully**.
- The checkout route fix was introduced in commit [`7339333`](https://github.com/appmuvon36-cyber/Allpha-oto/commit/73393331dfd832b40a516cb1e8b42cb991400a08); the later deployed commit includes it. Its dedicated Phase 05 contract/build run [#116](https://github.com/appmuvon36-cyber/Allpha-oto/actions/runs/39186817133) completed successfully.
- Production check of `/checkout` now resolves to `/cart` and renders “Masuk untuk checkout”; the previous 404 is no longer observed. This route intentionally reuses the existing authenticated cart/checkout flow.

### Latest interactive browser checks
- Customer homepage: clicked category **Mesin**; the search textbox changed to `mesin`. Replacing the query with `filter` showed **“Produk tidak ditemukan”**, matching the currently empty live catalog.
- Keyboard: Tab navigation moved focus between interactive controls; the browser reported a visible 3px orange/peach focus outline.
- Browser back/forward: navigation returned between `/cart` and `/` without a reported route failure.
- Vehicle selection: make dropdown contains only “Semua merek”; model and variant/year controls are disabled because the production vehicle taxonomy endpoint returns `items=[]`. A positive vehicle-selection path is therefore blocked by missing real data and was not fabricated.
- Admin direct routes `/catalog`, `/suppliers`, `/inventory-orders`, `/users`, and `/audit`: all redirected unauthenticated browser sessions to `/login`; no protected content was exposed.
- Direct `/checkout`: final URL `/cart`, sign-in-required checkout screen visible, no 404.
- Viewport screenshots freshly captured after deployment:
  - [360 screenshot](https://storage.googleapis.com/firecrawl-scrape-media/screenshot-53370882-8b34-451d-a776-03ad9448e1fd.png)
  - [390 screenshot](https://storage.googleapis.com/firecrawl-scrape-media/screenshot-d5db5356-8e9b-4adc-8104-263d25c6ad69.png)
  - [820 screenshot](https://storage.googleapis.com/firecrawl-scrape-media/screenshot-0b36ef48-d4ab-40f3-8bea-3c287f8a21cb.png)
  - [1440 screenshot](https://storage.googleapis.com/firecrawl-scrape-media/screenshot-d9d2e68b-f700-4925-a35c-1bd4666ec3a6.png)
- **Horizontal overflow limitation:** screenshot requests were made for all four target widths, but the interactive browser runtime does not support resizing its main viewport. Its measurable default viewport was 1905px with document/body scroll width 1905px and no overflowing elements at that default size. This is not sufficient to certify no horizontal overflow at 360/390/820/1440. Keep that check open rather than claiming it passed.
- **Runtime errors/loading/error states:** no application page error was emitted by the interaction result, but the tool does not provide a reliable full console/network trace. Existing empty and unavailable states were observed; exhaustive forced loading/error-state testing remains open.
- **Authenticated authorization matrix:** no approved test customer or staff credentials were provided in this QA context. No login attempts, customer orders, role mutations, or production writes were made. Unauthenticated guard tests do not prove that permitted staff roles work or that disallowed roles are denied after login.

## Remaining blockers before Phase 10
1. Run viewport-resized browser tests (or a local/CI browser harness with Playwright installed) to record exact `clientWidth` vs `scrollWidth` at 360, 390, 820, and 1440, including console/network errors.
2. Repeat direct-route, loading, error, empty, keyboard and back/forward checks across all customer routes and all Admin operational routes.
3. With approved test identities, test customer login, real vehicle selection/product/cart/checkout/order path, plus staff role-allowed and role-denied behavior. Current empty production taxonomy/catalog prevents positive commerce-path verification without approved non-production fixtures or real approved catalog data.
4. Keep the phase gate **PARTIAL** until the above evidence is recorded. Phase 10 remains deferred.
