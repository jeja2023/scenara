<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { Check, Plus, UploadCloud } from "@lucide/vue";
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

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page">
    <p v-if="error" class="callout error">{{ error }}</p>
    <p v-if="message" class="callout success">{{ message }}</p>
    <div class="governance-grid">
      <section class="panel create-panel">
        <div class="panel-header">
          <h2>新建数据集</h2>
        </div>
        <div class="panel-body form-stack">
          <label
            >名称<input
              v-model="datasetForm.name"
              maxlength="120"
              placeholder="例如：2026 年园区人像样本"
          /></label>
          <label
            >说明<textarea
              v-model="datasetForm.description"
              maxlength="1000"
              placeholder="记录数据用途和授权边界"
            />
          </label>
          <button
            class="button primary"
            :disabled="saving || !datasetForm.name.trim()"
            @click="createDataset"
          >
            <Plus :size="16" />创建数据集
          </button>
        </div>
      </section>
      <section class="panel">
        <div class="panel-header">
          <h2>数据集目录</h2>
          <span class="muted">{{ datasets.length }} 个</span>
        </div>
        <div class="dataset-list">
          <button
            v-for="dataset in datasets"
            :key="dataset.dataset_id"
            class="dataset-row"
            :class="{ selected: dataset.dataset_id === selectedDatasetId }"
            @click="
              selectedDatasetId = dataset.dataset_id;
              loadVersions();
            "
          >
            <span
              ><strong>{{ dataset.name }}</strong
              ><small>{{ dataset.description || "未填写说明" }}</small></span
            >
            <em :class="['status', dataset.status]">{{
              statusLabel(dataset.status)
            }}</em>
          </button>
          <div v-if="!datasets.length" class="empty">还没有数据集</div>
        </div>
      </section>
    </div>
    <section v-if="selectedDataset" class="panel">
      <div class="panel-header">
        <div>
          <h2>{{ selectedDataset.name }} · 版本治理</h2>
          <p>{{ selectedDataset.description || "未填写说明" }}</p>
        </div>
        <span class="muted">{{ versions.length }} 个版本</span>
      </div>
      <div class="version-layout">
        <div class="asset-picker">
          <div class="subhead">
            <strong>选择资产</strong
            ><span>{{ selectedAssets.length }} 已选</span>
          </div>
          <label
            v-for="asset in assets"
            :key="asset.asset_id"
            class="asset-option"
          >
            <input
              type="checkbox"
              :checked="selectedAssetIds.includes(asset.asset_id)"
              @change="toggleAsset(asset.asset_id)"
            />
            <span
              >{{ asset.filename || asset.asset_id
              }}<small>{{ asset.kind }} · {{ asset.asset_id }}</small></span
            >
          </label>
          <div v-if="!assets.length" class="empty">
            请先在数据资产中上传文件
          </div>
        </div>
        <div class="version-form form-stack">
          <label
            >版本号<input
              v-model="versionForm.version"
              placeholder="例如：2026.08.03"
          /></label>
          <label
            >Manifest SHA-256<input
              v-model="versionForm.manifest_sha256"
              minlength="64"
              maxlength="64"
              placeholder="64 位十六进制摘要"
          /></label>
          <label
            >质量评分<input
              v-model="versionForm.quality_score"
              type="number"
              min="0"
              max="1"
              step="0.01"
              placeholder="可选，0 到 1"
          /></label>
          <button
            class="button primary"
            :disabled="
              saving ||
              !versionForm.version.trim() ||
              versionForm.manifest_sha256.length !== 64
            "
            @click="createVersion"
          >
            <UploadCloud :size="16" />创建版本
          </button>
        </div>
      </div>
      <div class="version-list">
        <div
          v-for="version in versions"
          :key="version.version_id"
          class="version-row"
        >
          <div>
            <strong>v{{ version.version }}</strong
            ><small
              >{{ version.item_count }} 项资产 · 质量
              {{
                version.quality_score === null
                  ? "未评分"
                  : version.quality_score.toFixed(2)
              }}</small
            >
          </div>
          <div class="version-actions">
            <em :class="['status', version.status]">{{
              statusLabel(version.status)
            }}</em
            ><button
              v-if="version.status === 'draft'"
              class="button tiny"
              :disabled="saving"
              @click="transition(version, 'validated')"
            >
              <Check :size="14" />校验</button
            ><button
              v-if="version.status === 'validated'"
              class="button tiny primary"
              :disabled="saving"
              @click="transition(version, 'published')"
            >
              发布</button
            ><button
              v-if="version.status === 'published'"
              class="button tiny"
              :disabled="saving"
              @click="transition(version, 'retired')"
            >
              退役
            </button>
          </div>
        </div>
        <div v-if="!versions.length" class="empty">尚未创建版本</div>
      </div>
    </section>
  </section>
</template>

<style scoped>
.governance-grid {
  display: grid;
  grid-template-columns: minmax(260px, 0.8fr) minmax(0, 1.2fr);
  gap: 16px;
}
.panel-header h2 {
  display: flex;
  align-items: center;
  gap: 8px;
}
.form-stack {
  display: grid;
  gap: 12px;
}
label {
  display: grid;
  gap: 6px;
  font-size: 13px;
  color: var(--muted);
}
input,
textarea {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 9px 10px;
  font: inherit;
  color: var(--text);
  background: var(--surface);
}
textarea {
  min-height: 80px;
  resize: vertical;
}
.dataset-list,
.version-list {
  display: grid;
  gap: 1px;
  background: var(--line);
}
.dataset-row,
.version-row {
  border: 0;
  background: var(--surface);
  padding: 13px 15px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  text-align: left;
  gap: 12px;
}
.dataset-row {
  cursor: pointer;
}
.dataset-row.selected {
  background: var(--color-accent-soft);
  box-shadow: inset 3px 0 var(--teal);
}
.dataset-row span,
.version-row > div:first-child {
  display: grid;
  gap: 4px;
  min-width: 0;
}
small {
  color: var(--muted);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.status {
  font-size: 12px;
  font-style: normal;
  white-space: nowrap;
  padding: 3px 7px;
  border-radius: 4px;
  background: #eef1f2;
  color: var(--muted);
}
.status.active,
.status.published {
  color: #0b7557;
  background: #e4f5ed;
}
.status.validated {
  color: #2264a6;
  background: #e8f1fb;
}
.status.archived,
.status.retired {
  color: #7c8386;
  background: #f0f1f1;
}
.version-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 0.8fr);
  gap: 20px;
  padding: 18px;
  border-bottom: 1px solid var(--line);
}
.asset-picker {
  display: grid;
  align-content: start;
  gap: 7px;
  max-height: 270px;
  overflow: auto;
}
.subhead {
  display: flex;
  justify-content: space-between;
  color: var(--muted);
  font-size: 13px;
  margin-bottom: 5px;
}
.asset-option {
  display: flex;
  grid-template-columns: auto 1fr;
  align-items: start;
  grid-template-rows: auto;
  gap: 8px;
  padding: 8px;
  background: #f7f9f9;
  border-radius: 5px;
}
.asset-option input {
  width: auto;
  margin-top: 3px;
}
.asset-option span {
  display: grid;
  gap: 2px;
}
.asset-option small {
  white-space: normal;
}
.version-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.button.tiny {
  min-height: 30px;
  padding: 5px 9px;
  font-size: 12px;
}
.muted {
  color: var(--muted);
  font-size: 12px;
}
.empty {
  padding: 22px;
  color: var(--muted);
  text-align: center;
  background: var(--surface);
}
@media (max-width: 850px) {
  .governance-grid,
  .version-layout {
    grid-template-columns: 1fr;
  }
  .version-row {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
