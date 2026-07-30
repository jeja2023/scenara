import { expect, test } from "@playwright/test";

const allowedInterfaceTerms = new Set([
  "AI", "API", "GPU", "HTTP", "HTTPS", "JSON", "KB", "MiB", "OCR", "OpenAPI", "PostgreSQL", "Python", "Redis", "S3", "SDK", "SHA", "TypeScript",
  "Scenara", "Agent", "Console", "Data", "Edge", "Flow", "Index", "Model", "Parse", "Search",
]);

async function expectChineseInterface(page: import("@playwright/test").Page): Promise<void> {
  const text = await page.locator("body").innerText();
  const terms = [...new Set(text.match(/[A-Za-z][A-Za-z-]*/g) ?? [])];
  expect(terms.filter((term) => !allowedInterfaceTerms.has(term))).toEqual([]);
}

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
        version: "0.3.0.dev0",
        profile: "development",
        state_backend: "memory",
        object_backend: "local",
        queue_backend: "inline",
        production_models_required: false,
        auth_required: false,
      };
    } else if (path === "/api/v1/platform/products") {
      const products = [
        ["parse", "product_module", "available"], ["model", "product_module", "seed"],
        ["data", "product_module", "seed"], ["console", "control_plane", "available"],
        ["api", "developer_surface", "available"], ["sdk", "developer_surface", "available"],
        ["index", "foundation", "seed"], ["search", "product_module", "planned"],
        ["flow", "product_module", "planned"], ["edge", "product_module", "gated"],
        ["agent", "product_module", "gated"],
      ] as const;
      data = products.map(([productId, layer, maturity]) => ({
        product_id: productId,
        name: `Scenara ${productId}`,
        layer,
        maturity,
        summary: "English backend summary must not reach the interface.",
        current_scope: [],
        not_in_scope_yet: [],
        api_paths: [],
        depends_on: [],
        next_gate: "English backend gate must not reach the interface.",
      }));
    } else if (path === "/api/v1/platform/repositories") {
      data = {
        schema_version: "1.0",
        current_repository_id: "scenara",
        repositories: [
          {
            repository_id: "scenara",
            name: "Scenara",
            kind: "platform_integration",
            lifecycle: "current",
            current_repository: true,
            primary_product_ids: ["parse", "console", "api", "sdk"],
            integration_product_ids: ["model", "data"],
            responsibilities: ["platform_runtime", "shared_console", "shared_open_api", "shared_sdks"],
            excluded_responsibilities: ["model_training_jobs", "dataset_catalog_and_versioning"],
            next_gate: "English backend gate must not reach the interface.",
          },
          {
            repository_id: "scenara-model",
            name: "Scenara Model",
            kind: "specialized_product",
            lifecycle: "external_existing",
            current_repository: false,
            primary_product_ids: ["model"],
            integration_product_ids: ["data", "console", "api", "sdk"],
            responsibilities: ["model_training_jobs", "experiment_tracking", "training_compute_scheduling"],
            excluded_responsibilities: ["model_admission_release_and_deployment", "shared_console"],
            next_gate: "English backend gate must not reach the interface.",
          },
          {
            repository_id: "scenara-data",
            name: "Scenara Data",
            kind: "specialized_product",
            lifecycle: "planned",
            current_repository: false,
            primary_product_ids: ["data"],
            integration_product_ids: ["model", "console", "api", "sdk"],
            responsibilities: ["dataset_catalog_and_versioning", "data_labeling_and_review", "dataset_quality_and_lineage"],
            excluded_responsibilities: ["model_training_jobs", "operational_media_run_and_result_storage"],
            next_gate: "English backend gate must not reach the interface.",
          },
        ],
        integration_contracts: [
          { contract_id: "model-package-admission" },
          { contract_id: "hard-sample-handoff" },
          { contract_id: "dataset-version-input" },
          { contract_id: "deployment-feedback" },
        ],
        boundary_rules: [
          "versioned_contracts_only",
          "no_shared_database",
          "no_cross_repository_source_imports",
          "immutable_artifact_references",
        ],
      };
    } else if (path === "/api/v1/platform/iam/summary") {
      data = {
        schema_version: "1.0",
        tenant_id: "default",
        project_id: "default",
        inventory: {
          organizations: 0,
          projects: 0,
          users: 0,
          roles: 0,
          memberships: 0,
          service_accounts: 0,
          api_keys: 0,
          product_entitlements: 0,
        },
        default_admin_scopes: ["*", "iam:*", "platform:*"],
      };
    } else if (path === "/api/v1/platform/access-foundation") {
      data = {
        schema_version: "1.0",
        auth_mode: "development_open",
        principal_source: "anonymous",
        tenant_id: "default",
        project_id: "default",
        principal_id: "anonymous",
        policy_provider: "development-open",
        capabilities: [
          {
            capability_id: "tenant_project_context",
            name: "Tenant and project context",
            status: "available",
            summary: "Every request is scoped by tenant and project identifiers.",
            current_scope: [],
            not_in_scope_yet: [],
            next_gate: "Add first-class organization and project administration resources.",
          },
        ],
      };
    } else if (path === "/api/v1/platform/service-accounts" && route.request().method() === "GET") {
      data = [{
        tenant_id: "default",
        project_id: "default",
        service_account_id: "automation-console",
        display_name: "控制台自动化",
        scopes: ["iam:*"],
        product_ids: ["console"],
        disabled: false,
        created_at: 1,
        updated_at: 1,
      }];
    } else if (path.endsWith("/service-accounts/automation-console/api-keys")) {
      data = {
        record: {
          tenant_id: "default",
          project_id: "default",
          key_id: "key-console",
          service_account_id: "automation-console",
          name: "控制台持续集成",
          token_prefix: "sk_scenara_key-console",
          scopes: ["iam:read"],
          product_ids: ["console"],
          created_at: 1,
        },
        api_key: "example-scenara-credential-value",
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
    await expectChineseInterface(page);
  });
}

test("overview exposes repository ownership without leaking backend copy", async ({ page }) => {
  await page.goto("");
  await expect(page.getByRole("heading", { name: "仓库拓扑" })).toBeVisible();
  await expect(page.getByText("Scenara 平台集成仓库")).toBeVisible();
  await expect(page.getByText("Scenara Model 专业仓库")).toBeVisible();
  await expect(page.getByText("Scenara Data 专业仓库")).toBeVisible();
  await expect(page.getByText("禁止跨仓库共享数据库")).toBeVisible();
  await expect(page.getByText("English backend gate must not reach the interface.")).toHaveCount(0);
  await expectChineseInterface(page);
});

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

test("access management tabs and one-time credential render", async ({ page }) => {
  await page.goto("access");
  await page.getByRole("tab", { name: "服务凭据" }).click();
  await expect(page.getByRole("heading", { name: "创建服务账号" })).toBeVisible();
  await page.getByLabel("密钥名称").fill("控制台持续集成");
  await page.getByRole("button", { name: "签发密钥" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.locator("input[readonly]")).toHaveValue("example-scenara-credential-value");
  await dialog.getByRole("button", { name: "完成" }).click();

  for (const [tab, heading] of [
    ["成员与角色", "组织"],
    ["产品授权", "项目产品授权"],
    ["事件回调", "事件回调订阅"],
    ["连接设置", "浏览器连接"],
  ] as const) {
    await page.getByRole("tab", { name: tab }).click();
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await expectChineseInterface(page);
  }
  await expectChineseInterface(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)).toBe(false);
});
