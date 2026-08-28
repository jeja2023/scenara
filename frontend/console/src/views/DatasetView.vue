<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { Check, Database, Plus, UploadCloud } from "@lucide/vue";
import { api, userFacingError } from "../api";
import type { DatasetRecord, DatasetVersion, MediaAsset } from "../types";

const datasets = ref<DatasetRecord[]>([]);
const versions = ref<DatasetVersion[]>([]);
const assets = ref<MediaAsset[]>([]);
const selectedDatasetId = ref("");
const selectedAssetIds = ref<string[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const message = ref("");
const datasetForm = reactive({ name: "", description: "" });
const versionForm = reactive({
  version: "",
  manifest_sha256: "",
  quality_score: "",
});

const selectedDataset = computed(
  () =>
    datasets.value.find(
      (item) => item.dataset_id === selectedDatasetId.value,
    ) ?? null,
);
const selectedAssets = computed(() =>
  assets.value.filter((item) => selectedAssetIds.value.includes(item.asset_id)),
);

function clearFeedback(): void {
  error.value = "";
  message.value = "";
}

async function loadVersions(): Promise<void> {
  if (!selectedDatasetId.value) {
    versions.value = [];
    return;
  }
  const page = await api<{ items: DatasetVersion[] }>(
    `/api/v1/datasets/${encodeURIComponent(selectedDatasetId.value)}/versions?limit=200`,
  );
  versions.value = page.items;
}

async function refresh(): Promise<void> {
  loading.value = true;
  clearFeedback();
  try {
    const [datasetPage, assetPage] = await Promise.all([
      api<{ items: DatasetRecord[] }>("/api/v1/datasets?limit=200"),
      api<{ items: MediaAsset[] }>("/api/v1/media/assets?limit=200"),
    ]);
    datasets.value = datasetPage.items;
    assets.value = assetPage.items.filter((item) => !item.original_deleted_at);
    if (!selectedDatasetId.value && datasets.value.length)
      selectedDatasetId.value = datasets.value[0]?.dataset_id ?? "";
    if (
      selectedDatasetId.value &&
      !datasets.value.some(
        (item) => item.dataset_id === selectedDatasetId.value,
      )
    ) {
      selectedDatasetId.value = datasets.value[0]?.dataset_id ?? "";
    }
    await loadVersions();
  } catch (caught) {
    error.value = userFacingError(caught, "数据集治理数据加载失败");
  } finally {
    loading.value = false;
  }
}

async function createDataset(): Promise<void> {
  if (!datasetForm.name.trim()) return;
  saving.value = true;
  clearFeedback();
  try {
    const created = await api<DatasetRecord>("/api/v1/datasets", {
      method: "POST",
      body: JSON.stringify({
        name: datasetForm.name.trim(),
        description: datasetForm.description.trim(),
      }),
    });
    datasetForm.name = "";
    datasetForm.description = "";
    selectedDatasetId.value = created.dataset_id;
    message.value = "数据集已创建";
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught, "数据集创建失败");
  } finally {
    saving.value = false;
  }
}

async function createVersion(): Promise<void> {
  if (
    !selectedDatasetId.value ||
    !versionForm.version.trim() ||
    !versionForm.manifest_sha256.trim()
  )
    return;
  saving.value = true;
  clearFeedback();
  try {
    await api<DatasetVersion>(
      `/api/v1/datasets/${encodeURIComponent(selectedDatasetId.value)}/versions`,
      {
        method: "POST",
        body: JSON.stringify({
          version: versionForm.version.trim(),
          manifest_sha256: versionForm.manifest_sha256.trim(),
          asset_ids: selectedAssetIds.value,
          quality_score:
            versionForm.quality_score === ""
              ? null
              : Number(versionForm.quality_score),
          lineage: {
            source: "console",
            selected_asset_count: selectedAssetIds.value.length,
          },
          annotation_summary: { status: "pending_review" },
        }),
      },
    );
    versionForm.version = "";
    versionForm.manifest_sha256 = "";
    versionForm.quality_score = "";
    selectedAssetIds.value = [];
    message.value = "数据集版本已创建，等待校验";
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught, "数据集版本创建失败");
  } finally {
    saving.value = false;
  }
}

async function transition(
  version: DatasetVersion,
  status: "validated" | "published" | "retired",
): Promise<void> {
  saving.value = true;
  clearFeedback();
  try {
    await api<DatasetVersion>(
      `/api/v1/dataset-versions/${encodeURIComponent(version.version_id)}/transition`,
      {
        method: "POST",
        body: JSON.stringify({ status }),
      },
    );
    message.value = status === "published" ? "版本已发布" : "版本状态已更新";
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught, "版本状态更新失败");
  } finally {
    saving.value = false;
  }
}

function toggleAsset(assetId: string): void {
  selectedAssetIds.value = selectedAssetIds.value.includes(assetId)
    ? selectedAssetIds.value.filter((item) => item !== assetId)
    : [...selectedAssetIds.value, assetId];
}

function statusLabel(status: string): string {
  return (
    {
      draft: "草稿",
      active: "使用中",
      archived: "已归档",
      validated: "已校验",
      published: "已发布",
      retired: "已退役",
    }[status] ?? status
  );
}

function statusClass(status: string): string {
  if (status === "active" || status === "published") return "active";
  if (status === "validated") return "dot-dev";
  if (status === "retired" || status === "archived") return "warn-badge";
  return "";
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page">
    <p v-if="error" class="callout error">{{ error }}</p>
    <p v-if="message" class="callout success">{{ message }}</p>

    <div class="governance-grid">
      <!-- 1. 新建数据集 -->
      <section class="panel create-panel">
        <div class="panel-header">
          <h2>新建数据集</h2>
        </div>
        <div class="panel-body form-stack">
          <label class="form-field">
            <span class="field-label">数据集名称</span>
            <input
              v-model="datasetForm.name"
              class="field-input"
              maxlength="120"
              placeholder="例如：2026 年园区人像样本"
            />
          </label>
          <label class="form-field">
            <span class="field-label">用途与授权边界说明</span>
            <textarea
              v-model="datasetForm.description"
              class="field-textarea"
              maxlength="1000"
              placeholder="记录数据用途、标注规范和授权边界"
            />
          </label>
          <button
            class="button primary submit-btn"
            :disabled="saving || !datasetForm.name.trim()"
            @click="createDataset"
          >
            <Plus :size="14" />创建数据集
          </button>
        </div>
      </section>

      <!-- 2. 数据集目录 -->
      <section class="panel list-panel">
        <div class="panel-header">
          <div class="header-left">
            <h2>数据集目录</h2>
            <span class="badge">{{ datasets.length }}</span>
          </div>
        </div>
        <div class="dataset-list">
          <button
            v-for="dataset in datasets"
            :key="dataset.dataset_id"
            type="button"
            class="dataset-row"
            :class="{ selected: dataset.dataset_id === selectedDatasetId }"
            @click="
              selectedDatasetId = dataset.dataset_id;
              loadVersions();
            "
          >
            <div class="dataset-meta">
              <strong class="dataset-title">{{ dataset.name }}</strong>
              <small class="dataset-desc">{{ dataset.description || "未填写说明" }}</small>
            </div>
            <span class="badge status-badge" :class="statusClass(dataset.status)">
              {{ statusLabel(dataset.status) }}
            </span>
          </button>
          <div v-if="!datasets.length" class="empty-tip">还没有数据集</div>
        </div>
      </section>
    </div>

    <!-- 3. 选定数据集的版本治理 -->
    <section v-if="selectedDataset" class="panel version-panel">
      <div class="panel-header">
        <div class="header-left">
          <h2>{{ selectedDataset.name }} · 版本治理</h2>
          <span class="badge">{{ versions.length }} 个版本</span>
        </div>
        <p class="header-desc">{{ selectedDataset.description || "未填写说明" }}</p>
      </div>

      <div class="version-layout">
        <!-- 资产选择器 -->
        <div class="asset-picker-box">
          <div class="subhead">
            <strong>选择资产</strong>
            <span class="muted-text">{{ selectedAssets.length }} 项已选</span>
          </div>
          <div class="asset-scroll">
            <label
              v-for="asset in assets"
              :key="asset.asset_id"
              class="asset-option"
            >
              <input
                type="checkbox"
                class="checkbox-input"
                :checked="selectedAssetIds.includes(asset.asset_id)"
                @change="toggleAsset(asset.asset_id)"
              />
              <div class="asset-info">
                <span class="asset-name">{{ asset.filename || asset.asset_id }}</span>
                <small class="asset-sub">{{ asset.kind }} · {{ asset.asset_id }}</small>
              </div>
            </label>
            <div v-if="!assets.length" class="empty-tip">
              请先在数据资产中上传文件
            </div>
          </div>
        </div>

        <!-- 版本创建表单 -->
        <div class="version-form-box">
          <div class="subhead"><strong>创建新版本</strong></div>
          <div class="form-stack">
            <label class="form-field">
              <span class="field-label">版本号</span>
              <input
                v-model="versionForm.version"
                class="field-input"
                placeholder="例如：2026.08.03"
              />
            </label>
            <label class="form-field">
              <span class="field-label">Manifest SHA-256 摘要</span>
              <input
                v-model="versionForm.manifest_sha256"
                class="field-input mono"
                minlength="64"
                maxlength="64"
                placeholder="64 位十六进制摘要"
              />
            </label>
            <label class="form-field">
              <span class="field-label">质量评分 (0~1 可选)</span>
              <input
                v-model="versionForm.quality_score"
                class="field-input"
                type="number"
                min="0"
                max="1"
                step="0.01"
                placeholder="可选，0 到 1"
              />
            </label>
            <button
              class="button primary submit-btn"
              :disabled="
                saving ||
                !versionForm.version.trim() ||
                versionForm.manifest_sha256.length !== 64
              "
              @click="createVersion"
            >
              <UploadCloud :size="14" />创建版本
            </button>
          </div>
        </div>
      </div>

      <!-- 版本列表 -->
      <div class="version-list">
        <div
          v-for="version in versions"
          :key="version.version_id"
          class="version-row"
        >
          <div class="version-meta">
            <strong class="version-tag">v{{ version.version }}</strong>
            <small class="version-details">
              {{ version.item_count }} 项资产 · 质量评分
              {{
                version.quality_score === null
                  ? "未评分"
                  : version.quality_score.toFixed(2)
              }}
            </small>
          </div>
          <div class="version-actions">
            <span class="badge status-badge" :class="statusClass(version.status)">
              {{ statusLabel(version.status) }}
            </span>
            <button
              v-if="version.status === 'draft'"
              class="button secondary table-action-btn"
              :disabled="saving"
              @click="transition(version, 'validated')"
            >
              <Check :size="12" />校验
            </button>
            <button
              v-if="version.status === 'validated'"
              class="button primary table-action-btn"
              :disabled="saving"
              @click="transition(version, 'published')"
            >
              发布
            </button>
            <button
              v-if="version.status === 'published'"
              class="button secondary table-action-btn"
              :disabled="saving"
              @click="transition(version, 'retired')"
            >
              退役
            </button>
          </div>
        </div>
        <div v-if="!versions.length" class="empty-tip">尚未创建版本</div>
      </div>
    </section>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.governance-grid {
  display: grid;
  grid-template-columns: minmax(280px, 0.8fr) minmax(0, 1.2fr);
  gap: 14px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  margin-bottom: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-header h2 {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--graphite, #17211f);
  margin: 0;
}

.header-desc {
  margin: 0;
  font-size: 11.5px;
  color: var(--muted, #64716d);
}

.form-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.field-label {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--graphite, #17211f);
}

.field-input {
  height: 28px;
  line-height: 28px;
  padding: 0 8px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 5px;
  background: #ffffff;
  color: var(--graphite, #17211f);
  font-size: 11.5px;
  outline: none;
  box-sizing: border-box;
  transition: all 0.15s ease;
}

.field-input:focus {
  border-color: var(--primary, #0ea5e9);
  box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.12);
}

.field-textarea {
  min-height: 72px;
  padding: 6px 8px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 5px;
  background: #ffffff;
  color: var(--graphite, #17211f);
  font-size: 11.5px;
  outline: none;
  box-sizing: border-box;
  resize: vertical;
  transition: all 0.15s ease;
}

.field-textarea:focus {
  border-color: var(--primary, #0ea5e9);
  box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.12);
}

.submit-btn {
  height: 28px;
  padding: 0 12px;
  font-size: 11.5px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* 数据集目录列表 */
.dataset-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 280px;
  overflow-y: auto;
}

.dataset-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 5px;
  background: #ffffff;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s ease;
}

.dataset-row:hover {
  background: #fafbfb;
  border-color: #cbd5e1;
}

.dataset-row.selected {
  background: var(--teal-soft, #e0f2fe);
  border-color: var(--primary, #0ea5e9);
}

.dataset-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.dataset-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--graphite, #17211f);
}

.dataset-desc {
  font-size: 11px;
  color: var(--muted, #64716d);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 版本治理区域 */
.version-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(260px, 0.8fr);
  gap: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  margin-bottom: 14px;
}

.subhead {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--graphite, #17211f);
  margin-bottom: 8px;
}

.asset-scroll {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 240px;
  overflow-y: auto;
  padding-right: 4px;
}

.asset-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.12s ease;
}

.asset-option:hover {
  background: #f1f5f4;
}

.asset-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.asset-name {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--graphite, #17211f);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-sub {
  font-size: 10.5px;
  color: var(--muted, #64716d);
}

.checkbox-input {
  cursor: pointer;
}

/* 版本列表 */
.version-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.version-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #ffffff;
}

.version-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.version-tag {
  font-size: 12px;
  font-weight: 600;
  color: var(--graphite, #17211f);
}

.version-details {
  font-size: 11px;
  color: var(--muted, #64716d);
}

.version-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 18px;
  line-height: 18px;
  padding: 0 6px;
  font-size: 10.5px;
  white-space: nowrap;
}

.table-action-btn {
  height: 20px !important;
  min-height: 20px !important;
  padding: 0 6px !important;
  font-size: 10.5px !important;
  line-height: 1 !important;
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.empty-tip {
  font-size: 11.5px;
  color: var(--muted, #64716d);
  padding: 14px;
  text-align: center;
}

@media (max-width: 850px) {
  .governance-grid,
  .version-layout {
    grid-template-columns: 1fr;
  }
}
</style>
