// eslint-disable-next-line @typescript-eslint/no-require-imports -- Playwright spec is intentionally CommonJS (.cjs).
const { test, expect } = require("@playwright/test");

const WEB = process.env.OTOCLINIC_WEB_URL || "https://otoclinic-web-production.up.railway.app";
const ADMIN = process.env.OTOCLINIC_ADMIN_URL || "https://otoclinic-admin-production.up.railway.app";
const API = process.env.OTOCLINIC_API_URL || "https://otoclinic-api-production.up.railway.app";
const widths = [360, 390, 820, 1440];

async function overflow(page) {
  return page.evaluate(() => {
    const root = document.documentElement;
    const viewport = document.documentElement.clientWidth;
    const offenders = [...document.querySelectorAll("body *")].map((el) => {
      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      return {
        tag: el.tagName.toLowerCase(),
        id: el.id || null,
        className: typeof el.className === "string" ? el.className.slice(0, 100) : "",
        left: Math.round(rect.left),
        right: Math.round(rect.right),
        width: Math.round(rect.width),
        overflowX: style.overflowX,
      };
    }).filter((el) => el.width > 0 && (el.right > viewport + 1 || el.left < -1) && !(el.className.includes("pointer-events-none") && el.className.includes("absolute")) && !el.className.includes("pwa-splash-orbit"))
      .slice(0, 20);
    return {
      viewport: window.innerWidth,
      clientWidth: root.clientWidth,
      documentScrollWidth: root.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      offenders,
    };
  });
}

test.describe("OtoClinic public production UI QA", () => {
  for (const width of widths) {
    test(`customer homepage has no horizontal overflow at ${width}px`, async ({ browser }) => {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto(WEB, { waitUntil: "networkidle" });
      await expect(page.getByRole("heading", { name: "Spare part tepat, kendaraan tetap sehat.", exact: true })).toBeVisible();
      await expect(page.locator("#katalog h2", { hasText: "Semua produk" })).toBeVisible();
      const measured = await overflow(page);
      await page.screenshot({ path: `test-results/customer-${width}.png`, fullPage: true });
      expect(measured.documentScrollWidth, JSON.stringify(measured)).toBeLessThanOrEqual(width);
      expect(measured.bodyScrollWidth, JSON.stringify(measured)).toBeLessThanOrEqual(width);
      expect(measured.offenders, JSON.stringify(measured)).toEqual([]);
      expect(errors, errors.join("\n")).toEqual([]);
      await page.close();
    });
  }

  test("splash artwork renders and can be dismissed", async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    await page.addInitScript(() => sessionStorage.removeItem("otoclinic-splash-seen"));
    await page.goto(WEB, { waitUntil: "domcontentloaded" });
    const splash = page.locator(".pwa-splash-intro");
    await expect(splash).toBeVisible({ timeout: 5000 });
    await expect(splash.locator("img[src='https://raw.githubusercontent.com/fadliansyah36/Front-end-UI-Otoclinic/main/public/otoclinic_splash_art.jpg']")).toBeVisible();
    await expect(splash.getByRole("button", { name: "Lewati" })).toBeVisible();
    await splash.getByRole("button", { name: "Lewati" }).click();
    await expect(splash).toBeHidden();
    await expect(page.getByRole("button", { name: /Install App/i })).toBeVisible();
    await context.close();
  });

  test("category button updates search and empty results are explicit", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 });
    await page.goto(WEB, { waitUntil: "networkidle" });
    const search = page.getByRole("textbox", { name: /cari nama spare part/i });
    const categorySection = page.locator("#kategori");
    const categoryButtons = categorySection.locator("button.store-category-tile");
    await expect(categorySection).toBeVisible();
    await expect(categorySection.getByText("Memuat kategori dari katalog…")).toBeHidden({ timeout: 15000 }).catch(() => {});
    if (await categoryButtons.count()) {
      const firstCategory = categoryButtons.first();
      await expect(firstCategory.locator("span").filter({ hasText: /^ID:/ })).toBeVisible();
      await expect(firstCategory.getByText(/^Urutan:/)).toBeVisible();
      const categoryRequest = page.waitForRequest(request => {
        if (!request.url().includes("/v1/catalog/products")) return false;
        return Boolean(new URL(request.url()).searchParams.get("category_id"));
      });
      const expectedCategoryId = await firstCategory.locator("span").filter({ hasText: /^ID:/ }).innerText();
      await firstCategory.click();
      const request = await categoryRequest;
      expect(new URL(request.url()).searchParams.get("category_id")).toBe(expectedCategoryId.replace(/^ID:\s*/, ""));
      await expect(categorySection.getByText("Hierarki kategori terpilih")).toBeVisible();
      await expect(categorySection.getByText(/ID:/).first()).toBeVisible();
    } else {
      // Empty taxonomy and backend failures are different states. Neither path may seed fake categories.
      const emptyState = categorySection.getByText("Belum ada kategori aktif di master katalog.");
      const errorState = categorySection.getByRole("alert");
      await expect(emptyState.or(errorState).first()).toBeVisible({ timeout: 15000 });
      if (await errorState.count()) {
        await expect(errorState).toContainText("Kategori gagal dimuat dari backend");
      } else {
        await expect(emptyState).toBeVisible();
      }
    }
    await search.fill("qa-no-match-otoclinic");
    await expect(page.getByRole("heading", { name: /produk tidak ditemukan|belum ada produk/i })).toBeVisible({ timeout: 15000 });
  });

  test("keyboard focus is visible and browser history remains navigable", async ({ page }) => {
    await page.goto(WEB, { waitUntil: "networkidle" });
    await page.keyboard.press("Tab");
    const focus = await page.evaluate(() => ({
      tag: document.activeElement?.tagName,
      outlineStyle: getComputedStyle(document.activeElement).outlineStyle,
      outlineWidth: getComputedStyle(document.activeElement).outlineWidth,
    }));
    expect(focus.tag).not.toBe("BODY");
    expect(focus.outlineStyle).not.toBe("none");
    await page.goto(WEB + "/cart", { waitUntil: "domcontentloaded" });
    await page.goBack({ waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(WEB + "/");
    await page.goForward({ waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(WEB + "/cart");
  });

  test("direct customer routes resolve to safe public or sign-in states", async ({ page }) => {
    const cases = [
      ["/", /spare part tepat/i],
      ["/account", /masuk|akun/i],
      ["/cart", /masuk untuk checkout/i],
      ["/checkout", /masuk untuk checkout/i],
      ["/products/not-a-uuid", /produk|kembali ke katalog/i],
      ["/orders/not-a-uuid", /masuk|pesanan|pelanggan/i],
    ];
    for (const [path, heading] of cases) {
      const response = await page.goto(WEB + path, { waitUntil: "domcontentloaded" });
      expect(response, path).not.toBeNull();
      expect(response.status(), path).toBeLessThan(500);
      await expect(page.getByText(heading).first(), path).toBeVisible({ timeout: 15000 });
      if (path === "/checkout") await expect(page).toHaveURL(/\/cart$/);
    }
  });

  test("catalog loading skeleton appears before empty-state response", async ({ page }) => {
    await page.route(`${API}/v1/catalog/products**`, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1200));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [] }),
      });
    });
    await page.goto(WEB, { waitUntil: "domcontentloaded" });
    await expect(page.locator("#katalog .animate-pulse").first()).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole("heading", { name: /belum ada produk yang dipublikasikan/i })).toBeVisible({ timeout: 15000 });
  });

  test("catalog error state is rendered when API fails", async ({ page }) => {
    await page.route(`${API}/v1/catalog/products**`, (route) =>
      route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "QA injected service-unavailable response" }) })
    );
    await page.goto(WEB, { waitUntil: "domcontentloaded" });
    await expect(page.getByText(/katalog belum dapat dimuat/i)).toBeVisible({ timeout: 15000 });
  });

  test("vehicle selector safely represents empty taxonomy", async ({ page }) => {
    await page.goto(WEB, { waitUntil: "networkidle" });
    await expect(page.getByRole("combobox", { name: "Merek kendaraan" })).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Model kendaraan" })).toBeDisabled();
    await expect(page.getByRole("combobox", { name: /varian/i })).toBeDisabled();
  });

  test("admin operational routes resolve to a login or safe access-denied state", async ({ page }) => {
    for (const path of ["/catalog", "/suppliers", "/inventory-orders", "/users", "/audit"]) {
      await page.goto(ADMIN + path, { waitUntil: "networkidle" });
      const loginHeading = page.getByRole("heading", { name: /masuk ke otoclinic/i });
      const deniedState = page.getByText(/akses .* membutuhkan akun aktif|supabase belum dikonfigurasi|silakan login/i).first();
      await expect(loginHeading.or(deniedState)).toBeVisible({ timeout: 15000 });
      // No production records may be rendered for an unauthenticated browser context.
      await expect(page.locator("[data-protected-record='true']")).toHaveCount(0);
    }
  });

  test("private API endpoints reject requests without credentials", async ({ request }) => {
    for (const path of ["/v1/admin/overview", "/v1/orders?limit=1"]) {
      const response = await request.get(API + path);
      expect(response.status(), path).toBe(401);
    }
  });
});
