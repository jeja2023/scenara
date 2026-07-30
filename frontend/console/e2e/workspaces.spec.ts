import { expect, test } from "@playwright/test";

const workspaces = [
  ["", "总览", "总览"],
  ["media", "媒体", "媒体"],
  ["runs", "运行", "运行"],
  ["results", "结果", "结果"],
  ["portrait", "人像解析", "人像解析"],
  ["ocr", "OCR 文档解析", "OCR 文档"],
  ["pipelines", "流水线", "流水线"],
  ["models", "模型", "模型"],
  ["feedback", "反馈与发布", "反馈与发布"],
  ["access", "接入", "接入"],
  ["operations", "运维", "运维"],
  ["enterprise", "企业工作区", "企业"],
] as const;

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/enterprise/status") {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ request_id: "e2e", error: { code: "NOT_INSTALLED", message: "not installed" } }),
      });
      return;
    }
    let data: unknown = [];
    if (path === "/api/v1/media/assets" || path === "/api/v1/media/sources") {
      data = { items: [], offset: 0, limit: 50, total: 0 };
    } else if (path === "/api/v1/runs") {
      data = { items: [], offset: 0, limit: 100, total: 0 };
    } else if (path === "/api/v1/system/status") {
      data = {
        version: "0.2.0.dev0",
        profile: "development",
        state_backend: "memory",
        object_backend: "local",
        queue_backend: "inline",
        production_models_required: false,
        auth_required: false,
      };
    }
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ schema_version: "1.0", request_id: "e2e", data }),
    });
  });
});

for (const [path, heading, title] of workspaces) {
  test(`${title} workspace renders without viewport overflow`, async ({ page }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
    await expect(page).toHaveTitle(`${title} · Scenara 景枢`);
    await page.waitForTimeout(100);
    const overflowsViewport = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    );
    expect(overflowsViewport).toBe(false);
    expect(pageErrors).toEqual([]);
  });
}

test("mobile navigation opens and reaches another workspace", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto("");
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("link", { name: "媒体" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "媒体" })).toBeVisible();
  expect(pageErrors).toEqual([]);
});
