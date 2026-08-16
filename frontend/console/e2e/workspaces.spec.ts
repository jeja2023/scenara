import { Buffer } from "node:buffer";
import { expect, test } from "@playwright/test";

const allowedInterfaceTerms = new Set([
  "AI",
  "API",
  "B",
  "GPU",
  "HTTP",
  "HTTPS",
  "JSON",
  "KB",
  "MiB",
  "OCR",
  "OpenAPI",
  "PDF",
  "PostgreSQL",
  "Python",
  "Redis",
  "S3",
  "SDK",
  "SHA",
  "TypeScript",
  "Scenara",
  "Agent",
  "Console",
  "CSV",
  "Data",
  "Edge",
  "Flow",
  "Index",
  "Model",
  "Parse",
  "portrait",
  "ocr",
  "Search",
  "RPO",
  "RTO",
]);

async function expectChineseInterface(
  page: import("@playwright/test").Page,
): Promise<void> {
  const text = await page.locator("body").innerText();
  const terms = [...new Set(text.match(/[A-Za-z][A-Za-z-]*/g) ?? [])];
  expect(terms.filter((term) => !allowedInterfaceTerms.has(term))).toEqual([]);
}

const workspaces = [
  ["datasets", "数据集治理", "数据集治理"],
  ["audit", "审计中心", "审计中心"],
  ["", "总览", "总览"],
  ["parse/portrait", "人像解析", "人像解析"],
  ["assets", "数据资产", "数据资产"],
  ["results", "解析结果", "解析结果"],
  ["search", "综合检索", "综合检索"],
  ["runs", "运行历史", "运行历史"],
  ["capabilities", "领域与能力", "领域与能力"],
  ["pipelines", "流水线", "流水线"],
  ["models", "模型管理", "模型管理"],
  ["feedback", "反馈与发布", "反馈与发布"],
  ["access", "接入与权限", "接入与权限"],
  ["operations", "系统运维", "系统运维"],
] as const;

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    if (localStorage.getItem("scenara.console.e2e.skip-auth") !== "1")
      sessionStorage.setItem("scenara.console.auth.v1", "1");
  });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = [];
    if (path === "/api/v1/auth/login") {
      data = {
        token: "session-token-e2e",
        session: {
          session_id: "ses-e2e",
          tenant_id: "default",
          project_id: "default",
          user_id: "console-user",
          expires_at: Date.now() / 1000 + 3600,
        },
      };
    } else if (path === "/api/v1/datasets" || path === "/api/v1/audit/events") {
      data = { items: [], offset: 0, limit: 50, total: 0 };
    } else if (path === "/api/v1/search/saved") {
      data = { items: [], offset: 0, limit: 100, total: 0 };
    }
    if (path === "/api/v1/media/assets" || path === "/api/v1/media/sources") {
      data = { items: [], offset: 0, limit: 50, total: 0 };
    } else if (path === "/api/v1/results") {
      data = { items: [], offset: 0, limit: 50, total: 0 };
    } else if (path === "/api/v1/domains") {
      data = [
        {
          domain_id: "portrait",
          display_name: "人像",
          schema_version: "1.0",
          console_route: "/parse?domain=portrait",
          capabilities: ["person_detection"],
          supported_media_kinds: ["image", "video", "document", "stream"],
          default_pipeline_id: "portrait.person-detection",
          navigation_order: 10,
        },
        {
          domain_id: "ocr",
          display_name: "OCR 文档",
          schema_version: "1.0",
          console_route: "/parse?domain=ocr",
          capabilities: ["text_recognition"],
          supported_media_kinds: ["image", "video", "document", "stream"],
          default_pipeline_id: "ocr.document",
          navigation_order: 20,
        },
      ];
    } else if (path === "/api/v1/runs") {
      data = { items: [], offset: 0, limit: 100, total: 0 };
    } else if (path === "/api/v1/system/status") {
      data = {
        version: "0.3.0.dev15",
        profile: "development",
        state_backend: "memory",
        object_backend: "local",
        queue_backend: "inline",
        production_models_required: false,
        auth_required: false,
      };
    } else if (path === "/api/v1/platform/products") {
      const products = [
        ["parse", "product_module", "available"],
        ["model", "product_module", "seed"],
        ["data", "product_module", "seed"],
        ["console", "control_plane", "available"],
        ["api", "developer_surface", "available"],
        ["sdk", "developer_surface", "available"],
        ["index", "foundation", "seed"],
        ["search", "product_module", "seed"],
        ["flow", "product_module", "planned"],
        ["edge", "product_module", "gated"],
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
            responsibilities: [
              "platform_runtime",
              "shared_console",
              "shared_open_api",
              "shared_sdks",
            ],
            excluded_responsibilities: [
              "model_training_jobs",
              "dataset_catalog_and_versioning",
            ],
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
            responsibilities: [
              "model_training_jobs",
              "experiment_tracking",
              "training_compute_scheduling",
            ],
            excluded_responsibilities: [
              "model_admission_release_and_deployment",
              "shared_console",
            ],
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
            responsibilities: [
              "dataset_catalog_and_versioning",
              "data_labeling_and_review",
              "dataset_quality_and_lineage",
            ],
            excluded_responsibilities: [
              "model_training_jobs",
              "operational_media_run_and_result_storage",
            ],
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
            summary:
              "Every request is scoped by tenant and project identifiers.",
            current_scope: [],
            not_in_scope_yet: [],
            next_gate:
              "Add first-class organization and project administration resources.",
          },
        ],
      };
    } else if (path === "/api/v1/platform/portrait-intelligence") {
      const modules = [
        ["data_governance", "planned", "scenara-data"],
        ["annotation", "planned", "scenara-data"],
        ["training", "external", "scenara-model"],
        ["algorithms", "partial", "scenara-model"],
        ["vector_retrieval", "partial", "scenara"],
        ["mlops", "seed", "scenara"],
      ] as const;
      const assets = [
        ["data_lake", "planned", ["data_governance", "annotation"]],
        [
          "foundation_model",
          "planned",
          ["algorithms", "training", "data_governance"],
        ],
        [
          "intelligence_engine",
          "seed",
          ["algorithms", "vector_retrieval", "mlops"],
        ],
      ] as const;
      const capabilities = [
        ["person_detection", "ready", true],
        ["body_embedding", "ready", true],
        ["face_detection", "fallback", false],
        ["face_embedding", "fallback", false],
        ["pose", "placeholder", false],
        ["gait", "fallback", false],
        ["appearance", "fallback", false],
      ] as const;
      data = {
        schema_version: "1.0",
        positioning: "portrait_intelligence_foundation_platform",
        modules: modules.map(([moduleId, maturity, owner]) => ({
          module_id: moduleId,
          name: `English backend name must not reach the interface (${moduleId})`,
          maturity,
          summary: "English backend summary must not reach the interface.",
          owner_repository_id: owner,
          current_scope: [],
          not_in_scope_yet: [],
          next_gate: "English backend gate must not reach the interface.",
        })),
        assets: assets.map(([assetId, maturity, deps]) => ({
          asset_id: assetId,
          name: `English backend name must not reach the interface (${assetId})`,
          maturity,
          summary: "English backend summary must not reach the interface.",
          depends_on_modules: [...deps],
          next_gate: "English backend gate must not reach the interface.",
        })),
        capabilities: capabilities.map(
          ([capabilityId, readiness, productionReady]) => ({
            capability_id: capabilityId,
            readiness,
            production_ready: productionReady,
            current_model: null,
            target_model: null,
            embedding_dimension: null,
            target_embedding_dimension: null,
          }),
        ),
      };
    } else if (
      path === "/api/v1/platform/service-accounts" &&
      route.request().method() === "GET"
    ) {
      data = [
        {
          tenant_id: "default",
          project_id: "default",
          service_account_id: "automation-console",
          display_name: "控制台自动化",
          scopes: ["iam:*"],
          product_ids: ["console"],
          disabled: false,
          created_at: 1,
          updated_at: 1,
        },
      ];
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

test("unauthenticated visitors are sent to the login page", async ({
  page,
}) => {
  await page.goto("runs");
  await page.evaluate(() => {
    localStorage.setItem("scenara.console.e2e.skip-auth", "1");
    sessionStorage.removeItem("scenara.console.auth.v1");
  });
  await page.goto("runs");
  await expect(page).toHaveURL(/\/console\/login\?redirect=\/runs/);
  await expect(
    page.getByRole("heading", { level: 2, name: "登录控制台" }),
  ).toBeVisible();
});

test("username and password login returns to the workspace", async ({
  page,
}) => {
  await page.goto("runs");
  await page.evaluate(() => {
    localStorage.setItem("scenara.console.e2e.skip-auth", "1");
    sessionStorage.removeItem("scenara.console.auth.v1");
  });
  await page.goto("login?redirect=%2Fruns");
  await page.getByLabel("用户名", { exact: true }).fill("console-user");
  await page.getByLabel("密码", { exact: true }).fill("local-password");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/console\/runs$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "运行历史" }),
  ).toBeVisible();
});

for (const [path, heading, title] of workspaces) {
  test(`${title} workspace renders without viewport overflow`, async ({
    page,
  }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await page.goto(path);
    await expect(
      page.getByRole("heading", { level: 1, name: heading }),
    ).toBeVisible();
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

test("平台主题、跳转入口与规范视口保持可用", async ({ page }, testInfo) => {
  const viewports = [
    ["desktop", 1440, 900],
    ["laptop", 1280, 800],
    ["tablet", 768, 1024],
    ["mobile", 390, 844],
  ] as const;

  for (const [name, width, height] of viewports) {
    await page.setViewportSize({ width, height });
    await page.goto("datasets");
    await expect(page.locator(".shell")).toHaveAttribute("data-platform", "data");
    expect(
      await page.locator(".shell").evaluate(
        (element) => getComputedStyle(element).getPropertyValue("--color-accent").trim(),
      ),
    ).toBe("#2f6b8a");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBe(true);
    const screenshot = await page.screenshot({
      path: testInfo.outputPath(`dataset-${name}.png`),
      fullPage: true,
    });
    expect(screenshot.byteLength).toBeGreaterThan(5_000);
  }

  await page.goto("models");
  await expect(page.locator(".shell")).toHaveAttribute("data-platform", "model");
  expect(
    await page.locator(".shell").evaluate(
      (element) => getComputedStyle(element).getPropertyValue("--color-accent").trim(),
    ),
  ).toBe("#6256a8");
  await page.keyboard.press("Tab");
  await expect(page.locator(".skip-link")).toBeFocused();
  await expect(page.locator(".skip-link")).toBeVisible();
});

test("overview exposes repository ownership without leaking backend copy", async ({
  page,
}) => {
  await page.goto("");
  await expect(page.getByRole("heading", { name: "仓库拓扑" })).toBeVisible();
  await expect(page.getByText("Scenara 平台集成仓库")).toBeVisible();
  await expect(page.getByText("Scenara Model 专业仓库")).toBeVisible();
  await expect(page.getByText("Scenara Data 专业仓库")).toBeVisible();
  await expect(page.getByText("禁止跨仓库共享数据库")).toBeVisible();
  await expect(
    page.getByText("English backend gate must not reach the interface."),
  ).toHaveCount(0);
  await expectChineseInterface(page);
});

test("领域与能力页面完整屏蔽后端英文文案和技术标识", async ({ page }) => {
  await page.route("**/api/v1/domains", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        schema_version: "1.0",
        request_id: "e2e-capabilities",
        data: [
          {
            domain_id: "portrait",
            display_name: "Portrait Workspace",
            schema_version: "1.0",
            console_route: "/parse?domain=portrait",
            description: "English backend description must not reach the page.",
            capabilities: ["person_detection", "face_detection"],
            supported_media_kinds: ["image", "video"],
            default_pipeline_id: "portrait.analysis",
            navigation_order: 10,
          },
        ],
      }),
    });
  });
  await page.route("**/api/v1/pipelines", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        schema_version: "1.0",
        request_id: "e2e-capabilities",
        data: [
          {
            pipeline_id: "portrait.analysis",
            version: "0.4.0",
            domain: "portrait",
            status: "active",
            pausable: true,
            nodes: [],
          },
          {
            pipeline_id: "portrait.custom",
            version: "1.0.0",
            domain: "portrait",
            status: "draft",
            pausable: false,
            nodes: [],
          },
        ],
      }),
    });
  });

  await page.goto("capabilities");
  const workspace = page.locator(".capabilities-page");
  await expect(workspace.getByText("人像", { exact: true })).toBeVisible();
  await expect(
    workspace.getByText("检测人员并分析人像相关的视觉特征。"),
  ).toBeVisible();
  await expect(workspace.getByText("人像综合分析")).toBeVisible();
  await expect(workspace.getByText("自定义解析流水线")).toBeVisible();
  await expect(workspace.getByText("版本 0.4.0")).toBeVisible();
  await expect(workspace.getByText("启用", { exact: true })).toBeVisible();
  await expect(workspace.getByText("草稿", { exact: true })).toBeVisible();

  const workspaceText = await workspace.innerText();
  expect(workspaceText).not.toContain("Portrait Workspace");
  expect(workspaceText).not.toContain("English backend description");
  expect(workspaceText).not.toContain("portrait.analysis");
  expect(workspaceText).not.toContain("portrait.custom");
});

test("mobile navigation opens and reaches another workspace", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto("");
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("link", { name: "数据资产" }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "数据资产" }),
  ).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test("导航栏直接提供人像解析与 OCR 文档解析入口", async ({ page }) => {
  await page.goto("");
  const mobileMenu = page.locator(".mobile-menu");
  if (await mobileMenu.isVisible()) await mobileMenu.click();
  const portraitLink = page.getByRole("link", { name: "人像解析", exact: true });
  await expect(portraitLink).toBeVisible();
  await portraitLink.click();
  await expect(page).toHaveURL(/\/parse\/portrait$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "人像解析" }),
  ).toBeVisible();
});

test("parse workbench exposes complete media-mode controls", async ({
  page,
}) => {
  await page.goto("ocr");
  await page.getByRole("tab", { name: "视频", exact: true }).click();
  await expect(page.getByLabel("采样策略")).toBeVisible();
  await page.getByRole("button", { name: "展开高级参数" }).click();
  await expect(page.getByLabel("起始时间（毫秒）")).toBeVisible();
  await expect(page.getByLabel("结束时间（毫秒）")).toBeVisible();
  await expect(page.getByLabel("帧最大边长（像素）")).toBeVisible();

  await page.getByRole("tab", { name: "文档" }).click();
  await expect(page.getByLabel("最大页数")).toHaveCount(0);
  await expect(page.getByLabel("渲染倍率")).toBeVisible();

  await page.getByRole("tab", { name: "视频流" }).click();
  await page.getByRole("button", { name: "展开高级参数" }).click();
  await expect(page.getByLabel("最大分析时长（毫秒）")).toBeVisible();
  await expect(page.getByLabel("最大重连次数")).toBeVisible();
  await expect(page.getByLabel("连接超时（毫秒）")).toBeVisible();
  await expect(page.getByLabel("读取超时（毫秒）")).toBeVisible();
  await expectChineseInterface(page);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    ),
  ).toBe(false);
});

test("parse domain pages keep media tabs inside the workspace", async ({
  page,
}) => {
  await page.goto("parse/portrait/video");

  const mobileMenu = page.locator(".mobile-menu");
  if (await mobileMenu.isVisible()) await mobileMenu.click();

  await expect(page).toHaveURL(/\/parse\/portrait\/video$/);
  const mediaTab = page.getByRole("tab", { name: "视频", exact: true });
  await expect(mediaTab).toHaveAttribute("aria-selected", "true");

  const portraitMenu = page.getByRole("link", { name: "人像解析", exact: true });
  await expect(portraitMenu).toBeVisible();
  await expect(page.locator(".parse-media-link")).toHaveCount(0);
  await expect(page.locator(".parse-domain-link small")).toHaveCount(0);
  await portraitMenu.click();
  await expect(page).toHaveURL(/\/parse\/portrait$/);
  await expect(
    page.getByRole("tab", { name: "图片", exact: true }),
  ).toBeVisible();
});

test("parse workbench completes every media flow and cancellation", async ({
  page,
}, testInfo) => {
  await page.unroute("**/api/**");
  let runCount = 0;
  let cancelRequested = false;
  const run = (runId: string, status: string) => ({
    run_id: runId,
    domain: "ocr",
    pipeline: { pipeline_id: "ocr.document", version: "2.1.0" },
    parameters: {},
    priority: 0,
    status,
    revision: 1,
    progress: status === "completed" ? 1 : 0.4,
    created_at: 1,
    updated_at: 1,
  });
  const result = (runId: string, unitType: "frame" | "page" = "frame") => ({
    schema_version: "1.0",
    run_id: runId,
    domain: "ocr",
    pipeline: { pipeline_id: "ocr.document", version: "2.1.0" },
    asset_id: unitType === "page" ? "asset-document" : "asset-media",
    source_id: runId === "run-stream" ? "source-1" : null,
    units: [
      {
        unit_id: unitType === "page" ? "page_1" : "frame_0",
        unit_type: unitType,
        index: 0,
        pts_ms: unitType === "frame" ? 0 : null,
        page_number: unitType === "page" ? 1 : null,
        width: 640,
        height: 360,
        objects: [],
      },
    ],
    domain_payload: { domain: "ocr", text: `OCR ${runId}`, blocks: [] },
    relations: [],
    artifacts: [],
    models: [],
    timings: {},
    media_metadata: {
      sampled_units: 1,
      timestamp_source:
        runId === "run-stream" ? "monotonic_clock" : "position_msec",
    },
    warnings: [],
    provenance: {},
    created_at: 1,
  });
  const envelope = (data: unknown) =>
    JSON.stringify({ schema_version: "1.0", request_id: "parse-e2e", data });

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/media/sources" && request.method() === "GET") {
      await route.fulfill({
        contentType: "application/json",
        body: envelope({
          items: [
            {
              source_id: "source-1",
              name: "东门",
              masked_url: "rtsp://camera.example/live",
              metadata: {},
              created_at: 1,
            },
          ],
          offset: 0,
          limit: 200,
          total: 1,
        }),
      });
      return;
    }
    if (path === "/api/v1/media/assets" && request.method() === "GET") {
      await route.fulfill({
        contentType: "application/json",
        body: envelope({ items: [], offset: 0, limit: 200, total: 0 }),
      });
      return;
    }
    if (path === "/api/v1/pipelines" && request.method() === "GET") {
      await route.fulfill({
        contentType: "application/json",
        body: envelope([
          {
            pipeline_id: "portrait.person-detection",
            version: "0.1.0",
            domain: "portrait",
            status: "active",
            pausable: true,
            nodes: [],
          },
          {
            pipeline_id: "ocr.document",
            version: "2.1.0",
            domain: "ocr",
            status: "active",
            pausable: true,
            nodes: [],
          },
        ]),
      });
      return;
    }
    if (path === "/api/v1/domains" && request.method() === "GET") {
      await route.fulfill({
        contentType: "application/json",
        body: envelope([
          {
            domain_id: "portrait",
            display_name: "人像",
            schema_version: "1.0",
            console_route: "/parse?domain=portrait",
            capabilities: ["person_detection"],
            supported_media_kinds: ["image", "video", "document", "stream"],
            default_pipeline_id: "portrait.person-detection",
            navigation_order: 10,
          },
          {
            domain_id: "ocr",
            display_name: "OCR 文档",
            schema_version: "1.0",
            console_route: "/parse?domain=ocr",
            capabilities: ["text_recognition"],
            supported_media_kinds: ["image", "video", "document", "stream"],
            default_pipeline_id: "ocr.document",
            navigation_order: 20,
          },
        ]),
      });
      return;
    }
    if (path === "/api/v1/media/assets" && request.method() === "POST") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: envelope({
          asset_id: "asset-upload",
          kind: "image",
          filename: "uploaded",
          content_type: "application/octet-stream",
          size_bytes: 1,
          sha256: "a".repeat(64),
          metadata: {},
          temporary: false,
          created_at: 1,
        }),
      });
      return;
    }
    if (path === "/api/v1/runs" && request.method() === "POST") {
      runCount += 1;
      const runId = [
        "run-image",
        "run-video",
        "run-document",
        "run-stream",
        "run-video-cancel",
      ][runCount - 1]!;
      const status =
        runId === "run-video"
          ? "queued"
          : runId === "run-video-cancel"
            ? "running"
            : "completed";
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: envelope(run(runId, status)),
      });
      return;
    }
    if (path.endsWith("/events")) {
      const runId = path.split("/").at(-2)!;
      const body =
        runId === "run-video-cancel"
          ? ""
          : `data: ${JSON.stringify({ status: "completed", payload: { progress: 1 } })}\n\n`;
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body,
      });
      return;
    }
    if (path.endsWith("/cancel") && request.method() === "POST") {
      cancelRequested = true;
      await route.fulfill({
        contentType: "application/json",
        body: envelope(run("run-video-cancel", "cancelling")),
      });
      return;
    }
    if (path.endsWith("/result")) {
      const runId = path.split("/").at(-2)!;
      const unitType = runId === "run-document" ? "page" : "frame";
      await route.fulfill({
        contentType: "application/json",
        body: envelope({
          result: result(runId, unitType),
          unit_offset: 0,
          unit_limit: 1000,
          unit_total: 1,
        }),
      });
      return;
    }
    if (/\/api\/v1\/runs\/[^/]+$/.test(path)) {
      const runId = path.split("/").at(-1)!;
      const status =
        runId === "run-video-cancel"
          ? cancelRequested
            ? "cancelled"
            : "running"
          : "completed";
      await route.fulfill({
        contentType: "application/json",
        body: envelope(run(runId, status)),
      });
      return;
    }
    await route.fulfill({
      contentType: "application/json",
      body: envelope([]),
    });
  });

  await page.goto("ocr");
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles({
    name: "frame.png",
    mimeType: "image/png",
    buffer: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZbZsAAAAASUVORK5CYII=",
      "base64",
    ),
  });
  await page.getByRole("button", { name: "开始解析" }).click();
  await expect(page.getByLabel("OCR 文本结果")).toHaveValue("OCR run-image");

  await page.getByRole("tab", { name: "视频", exact: true }).click();
  await page.getByRole("button", { name: "当前上传" }).click();
  await fileInput.setInputFiles({
    name: "clip.mp4",
    mimeType: "video/mp4",
    buffer: Buffer.from("video"),
  });
  await page.getByRole("button", { name: "开始解析" }).click();
  await expect(page.getByLabel("OCR 文本结果")).toHaveValue("OCR run-video");

  await page.getByRole("tab", { name: "文档" }).click();
  await page.getByRole("button", { name: "当前上传" }).click();
  await fileInput.setInputFiles({
    name: "report.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.7\n%%EOF"),
  });
  await page.getByRole("button", { name: "开始解析" }).click();
  await expect(page.getByLabel("OCR 文本结果")).toHaveValue("OCR run-document");

  await page.getByRole("tab", { name: "视频流" }).click();
  await page.getByLabel("已登记视频流").selectOption("source-1");
  await page.getByRole("button", { name: "开始解析" }).click();
  await expect(page.getByLabel("OCR 文本结果")).toHaveValue("OCR run-stream");
  const screenshot = await page.screenshot({
    path: testInfo.outputPath("parse-workbench.png"),
    fullPage: true,
  });
  expect(screenshot.byteLength).toBeGreaterThan(5_000);

  await page.getByRole("tab", { name: "视频", exact: true }).click();
  await page.getByRole("button", { name: "当前上传" }).click();
  await fileInput.setInputFiles({
    name: "cancel.mp4",
    mimeType: "video/mp4",
    buffer: Buffer.from("video"),
  });
  await page.getByRole("button", { name: "开始解析" }).click();
  await page.getByRole("button", { name: "取消运行" }).click();
  await expect(page.getByText("已取消", { exact: true })).toBeVisible();
  expect(cancelRequested).toBe(true);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    ),
  ).toBe(false);
});

test("access management tabs and one-time credential render", async ({
  page,
}) => {
  await page.goto("access");
  await page.getByRole("tab", { name: "服务凭据" }).click();
  await expect(
    page.getByRole("heading", { name: "创建服务账号" }),
  ).toBeVisible();
  await page.getByLabel("密钥名称").fill("控制台持续集成");
  await page.getByRole("button", { name: "签发密钥" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.locator("input[readonly]")).toHaveValue(
    "example-scenara-credential-value",
  );
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
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    ),
  ).toBe(false);
});
