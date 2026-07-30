#!/usr/bin/env node

async function buildClient() {
  const { ScenaraClient } = await import("../../sdk/typescript/dist/index.js");
  const baseUrl = (process.env.SCENARA_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  const tenantId = process.env.SCENARA_TENANT_ID || "default";
  const projectId = process.env.SCENARA_PROJECT_ID || "default";
  const token = process.env.SCENARA_API_TOKEN || "";
  const transport = async (method, path, options = {}) => {
    const headers = {
      "Content-Type": "application/json",
      "X-Tenant-Id": tenantId,
      "X-Project-Id": projectId,
    };
    if (token) headers.Authorization = `Bearer ${token}`;
    if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;
    const response = await fetch(baseUrl + path, {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
    const payload = response.status === 204 ? { data: undefined } : await response.json();
    if (!response.ok) throw new Error(payload?.error?.message || `HTTP ${response.status}`);
    return payload.data;
  };
  return { client: new ScenaraClient({ transport }), baseUrl };
}

function value(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 && index + 1 < process.argv.length ? process.argv[index + 1] : fallback;
}

async function run() {
  const { client, baseUrl } = await buildClient();
  const assetId = value("--asset-id");
  const sourceId = value("--source-id");
  const domain = value("--domain", "portrait");
  const pipelineId = value("--pipeline", domain === "ocr" ? "ocr.document" : "portrait.person-detection");
  const planned = ["listDomains", "listPipelines"];
  if (assetId || sourceId) planned.push("createRun", "waitResult");
  if (process.argv.includes("--dry-run")) return { dry_run: true, base_url: baseUrl, planned_steps: planned };

  const payload = {
    dry_run: false,
    domains: await client.listDomains(),
    pipelines: await client.listPipelines(),
  };
  if (assetId || sourceId) {
    const created = await client.createRun({
      domain,
      pipelineId,
      pipelineVersion: "0.1.0",
      assetId: assetId || undefined,
      sourceId: sourceId || undefined,
    });
    payload.run = created;
    payload.result = await client.waitResult(created.run_id);
  }
  return payload;
}

run()
  .then((payload) => console.log(JSON.stringify(payload, null, 2)))
  .catch((error) => {
    console.error(JSON.stringify({ error: error instanceof Error ? error.message : String(error) }));
    process.exitCode = 1;
  });
