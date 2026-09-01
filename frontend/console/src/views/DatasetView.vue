<script setup lang="ts">
import {
  Archive,
  Check,
  CheckCircle2,
  Database,
  FileText,
  FolderArchive,
  Layers,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  UploadCloud,
  Video,
} from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";

import { api, userFacingError } from "../api";
import DataTable from "../components/DataTable.vue";
import type {
  DatasetRecord,
  DatasetVersion,
  MediaAsset,
  TableColumn,
} from "../types";

const versionColumns: TableColumn<DatasetVersion>[] = [
  { key: "version", label: "版本号", width: "120px" },
  { key: "item_count", label: "包含资产数", width: "120px" },
  {
    key: "manifest_sha256",
    label: "Manifest 指纹 (SHA256)",
    class: "mono",
    width: "190px",
  },
  {
    key: "quality_score",
    label: "质量评分",
    width: "110px",
    align: "center",
    headerAlign: "center",
  },
  {
    key: "status",
    label: "准入状态",
    width: "110px",
    align: "center",
    headerAlign: "center",
  },
  { key: "updated_at", label: "更新时间", width: "150px" },
  {
    key: "actions",
    label: "生命周期流转",
    width: "130px",
    align: "right",
    headerAlign: "right",
  },
];

const datasets = ref<DatasetRecord[]>([]);
const versions = ref<DatasetVersion[]>([]);
const assets = ref<MediaAsset[]>([]);
const selectedDatasetId = ref("");
const selectedAssetIds = ref<string[]>([]);

const loading = ref(false);
const saving = ref(false);
const error = ref("");
const message = ref("");

// 搜索与过滤
const datasetSearchQuery = ref("");
const datasetStatusFilter = ref<string>("all");
const assetSearchQuery = ref("");

// 模态弹窗控制
const showCreateDatasetModal = ref(false);
const showCreateVersionModal = ref(false);

const datasetForm = reactive({ name: "", description: "" });
const versionForm = reactive({
  version: "",
  manifest_sha256: "",
  quality_score: "",
});

const versionPageSize = ref(10);

const selectedDataset = computed(
  () =>
    datasets.value.find(
      (item) => item.dataset_id === selectedDatasetId.value,
    ) ?? null,
);

const activeDatasetsCount = computed(
  () => datasets.value.filter((d) => d.status === "active").length,
);

const draftDatasetsCount = computed(
  () => datasets.value.filter((d) => d.status === "draft").length,
);

const archivedDatasetsCount = computed(
  () => datasets.value.filter((d) => d.status === "archived").length,
);

const filteredDatasets = computed(() => {
  return datasets.value.filter((item) => {
    if (
      datasetStatusFilter.value !== "all" &&
      item.status !== datasetStatusFilter.value
    ) {
      return false;
    }
    if (datasetSearchQuery.value.trim()) {
      const q = datasetSearchQuery.value.trim().toLowerCase();
      const matchName = String(item.name || "")
        .toLowerCase()
        .includes(q);
      const matchId = String(item.dataset_id || "")
        .toLowerCase()
        .includes(q);
      const matchDesc = String(item.description || "")
        .toLowerCase()
        .includes(q);
      return matchName || matchId || matchDesc;
    }
    return true;
  });
});

const filteredAssets = computed(() => {
  if (!assetSearchQuery.value.trim()) return assets.value;
  const q = assetSearchQuery.value.trim().toLowerCase();
  return assets.value.filter((a) => {
    const matchName = String(a.filename || "")
      .toLowerCase()
      .includes(q);
    const matchId = String(a.asset_id || "")
      .toLowerCase()
      .includes(q);
    const matchKind = String(a.kind || "")
      .toLowerCase()
      .includes(q);
    return matchName || matchId || matchKind;
  });
});

function clearFeedback(): void {
  error.value = "";
  message.value = "";
}

function notifySuccess(msg: string): void {
  message.value = msg;
  setTimeout(() => {
    message.value = "";
  }, 3500);
}

async function loadVersions(): Promise<void> {
  if (!selectedDatasetId.value) {
    versions.value = [];
    return;
  }
  try {
    const page = await api<{ items: DatasetVersion[] }>(
      `/api/v1/datasets/${encodeURIComponent(selectedDatasetId.value)}/versions?limit=200`,
    );
    versions.value = page.items;
  } catch (caught) {
    error.value = userFacingError(caught, "加载数据集版本列表失败");
  }
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

    if (!selectedDatasetId.value && datasets.value.length) {
      selectedDatasetId.value = datasets.value[0]?.dataset_id ?? "";
    }
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
    showCreateDatasetModal.value = false;
    notifySuccess(`数据集「${created.name}」创建成功`);
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught, "数据集创建失败");
  } finally {
    saving.value = false;
  }
}

function generateRandomSha256(): void {
  const chars = "0123456789abcdef";
  let hash = "";
  for (let i = 0; i < 64; i++) {
    hash += chars[Math.floor(Math.random() * chars.length)];
  }
  versionForm.manifest_sha256 = hash;
}

function openCreateVersionModal(): void {
  versionForm.version = "";
  versionForm.manifest_sha256 = "";
  versionForm.quality_score = "";
  selectedAssetIds.value = [];
  assetSearchQuery.value = "";
  generateRandomSha256();
  showCreateVersionModal.value = true;
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
    showCreateVersionModal.value = false;
    notifySuccess("数据集新版本已构建就绪，等待校验");
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
    notifySuccess(
      status === "published"
        ? `版本 v${version.version} 已正式发布`
        : `版本状态已流转至 ${statusLabel(status)}`,
    );
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

function toggleSelectAllAssets(): void {
  if (selectedAssetIds.value.length === filteredAssets.value.length) {
    selectedAssetIds.value = [];
  } else {
    selectedAssetIds.value = filteredAssets.value.map((a) => a.asset_id);
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case "draft":
      return "草稿 (Draft)";
    case "active":
      return "使用中 (Active)";
    case "archived":
      return "已归档 (Archived)";
    case "validated":
      return "已校验 (Validated)";
    case "published":
      return "已发布 (Published)";
    case "retired":
      return "已退役 (Retired)";
    default:
      return status || "-";
  }
}

function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let val = bytes;
  let unitIndex = 0;
  while (val >= 1024 && unitIndex < units.length - 1) {
    val /= 1024;
    unitIndex++;
  }
  return `${val.toFixed(1)} ${units[unitIndex]}`;
}

function formatTime(epoch: number): string {
  if (!epoch) return "-";
  const d = new Date(epoch * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  const year = d.getFullYear();
  const month = pad(d.getMonth() + 1);
  const day = pad(d.getDate());
  const hours = pad(d.getHours());
  const minutes = pad(d.getMinutes());
  const seconds = pad(d.getSeconds());
  return `${year}/${month}/${day} ${hours}:${minutes}:${seconds}`;
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page dataset-page">
    <p v-if="error" class="error-banner">{{ error }}</p>
    <p v-if="message" class="success-banner">{{ message }}</p>

    <!-- 1. 顶部数据统计卡片 -->
    <section class="stats">
      <article class="stat teal">
        <div class="stat-top-row">
          <span class="stat-title">管理数据集</span>
          <div class="stat-icon-badge">
            <Database :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{ datasets.length }} 个</strong>
        <small class="stat-desc">全生命周期版本与授权隔离</small>
      </article>

      <article class="stat green">
        <div class="stat-top-row">
          <span class="stat-title">活跃使用中</span>
          <div class="stat-icon-badge">
            <CheckCircle2 :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{ activeDatasetsCount }} 个</strong>
        <small class="stat-desc"
          >{{ draftDatasetsCount }} 个草稿 ·
          {{ archivedDatasetsCount }} 个已归档</small
        >
      </article>

      <article class="stat amber">
        <div class="stat-top-row">
          <span class="stat-title">版本化构建</span>
          <div class="stat-icon-badge">
            <Layers :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{ versions.length }} 个版本</strong>
        <small class="stat-desc">{{
          selectedDataset ? `当前: ${selectedDataset.name}` : "未选择数据集"
        }}</small>
      </article>

      <article class="stat teal">
        <div class="stat-top-row">
          <span class="stat-title">就绪数据资产</span>
          <div class="stat-icon-badge">
            <FolderArchive :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{ assets.length }} 项</strong>
        <small class="stat-desc">可打包构建版本的文件与视频流</small>
      </article>
    </section>

    <!-- 2. 工作台左右两栏联动布局 -->
    <div class="dataset-workbench-layout">
      <!-- 左侧：数据集目录与导航 -->
      <aside class="dataset-sidebar">
        <!-- 侧边栏工具条 -->
        <div class="sidebar-header-box">
          <div class="sidebar-title-row">
            <div class="header-left">
              <Database :size="14" class="header-icon" />
              <h3>数据集目录</h3>
            </div>
            <button
              class="button primary tiny-btn"
              title="新建数据集"
              @click="showCreateDatasetModal = true"
            >
              <Plus :size="13" />
              <span>新建</span>
            </button>
          </div>

          <div class="sidebar-filters-row">
            <div class="search-box search-sm">
              <Search :size="12" class="search-icon" />
              <input
                v-model="datasetSearchQuery"
                placeholder="搜索数据集..."
                class="search-input"
              />
            </div>

            <select v-model="datasetStatusFilter" class="sidebar-status-select">
              <option value="all">全部状态</option>
              <option value="active">使用中 (Active)</option>
              <option value="draft">草稿 (Draft)</option>
              <option value="archived">已归档 (Archived)</option>
            </select>
          </div>
        </div>

        <!-- 数据集卡片滚动列表 -->
        <div class="dataset-cards-scroll">
          <button
            v-for="dataset in filteredDatasets"
            :key="dataset.dataset_id"
            type="button"
            class="dataset-card-item"
            :class="{ selected: dataset.dataset_id === selectedDatasetId }"
            @click="
              selectedDatasetId = dataset.dataset_id;
              loadVersions();
            "
          >
            <div class="card-top-row">
              <strong class="card-name" :title="dataset.name">{{
                dataset.name
              }}</strong>
              <span
                class="badge status-badge"
                :class="
                  dataset.status === 'active'
                    ? 'active'
                    : dataset.status === 'archived'
                      ? 'error-badge'
                      : 'warn-badge'
                "
              >
                <span
                  class="status-dot"
                  :class="
                    dataset.status === 'active'
                      ? 'dot-active'
                      : dataset.status === 'archived'
                        ? 'dot-error'
                        : 'dot-warn'
                  "
                />
                {{
                  dataset.status === "active"
                    ? "使用中"
                    : dataset.status === "archived"
                      ? "已归档"
                      : "草稿"
                }}
              </span>
            </div>

            <p class="card-desc" :title="dataset.description">
              {{ dataset.description || "暂无说明" }}
            </p>

            <div class="card-footer-row">
              <span class="mono card-id">{{ dataset.dataset_id }}</span>
              <span class="card-time">{{
                formatTime(dataset.updated_at)
              }}</span>
            </div>
          </button>

          <div v-if="!filteredDatasets.length" class="empty-sidebar-state">
            <Database :size="28" class="empty-icon" />
            <p>暂无匹配的数据集</p>
          </div>
        </div>
      </aside>

      <!-- 右侧：选定数据集的版本治理工作区 -->
      <main class="version-workspace">
        <template v-if="selectedDataset">
          <!-- 工作区头部 -->
          <div class="workspace-header">
            <div class="workspace-title-box">
              <div class="dataset-heading-row">
                <h2>{{ selectedDataset.name }}</h2>
                <span
                  class="badge status-badge"
                  :class="
                    selectedDataset.status === 'active'
                      ? 'active'
                      : 'warn-badge'
                  "
                >
                  <span
                    class="status-dot"
                    :class="
                      selectedDataset.status === 'active'
                        ? 'dot-active'
                        : 'dot-warn'
                    "
                  />
                  {{ statusLabel(selectedDataset.status) }}
                </span>
                <span class="mono dataset-id-tag"
                  >ID: {{ selectedDataset.dataset_id }}</span
                >
              </div>
              <p class="dataset-lead-desc">
                {{ selectedDataset.description || "未填写用途与授权边界说明" }}
              </p>
            </div>

            <div class="workspace-actions">
              <button
                class="button secondary tiny-btn"
                :disabled="loading"
                @click="refresh"
              >
                <RefreshCw :size="12" :class="{ spinning: loading }" />
                <span>刷新</span>
              </button>
              <button
                class="button primary tiny-btn"
                @click="openCreateVersionModal"
              >
                <UploadCloud :size="13" />
                <span>构建新版本</span>
              </button>
            </div>
          </div>

          <!-- 版本迭代列表面板 -->
          <section class="panel version-table-panel">
            <div class="panel-header">
              <div class="header-left">
                <Layers :size="14" class="header-icon" />
                <h3>数据集版本准入与生命周期流转</h3>
                <span class="badge count-badge"
                  >{{ versions.length }} 个版本</span
                >
              </div>
            </div>

            <DataTable
              :columns="versionColumns"
              :items="versions"
              :page-size="versionPageSize"
              :page-size-options="[10, 20, 50]"
              table-class="dataset-table"
              wrapper-class="dataset-table-wrapper"
              empty-text="当前数据集尚未构建任何版本，请点击右上角「构建新版本」"
            >
              <!-- 1. 版本号 -->
              <template #version="{ row }">
                <strong class="mono version-pill">v{{ row.version }}</strong>
              </template>

              <!-- 2. 包含资产数 -->
              <template #item_count="{ row }">
                <span class="bold"
                  >{{
                    row.item_count || (row.asset_ids ? row.asset_ids.length : 0)
                  }}
                  项资产</span
                >
              </template>

              <!-- 3. Manifest SHA256 -->
              <template #manifest_sha256="{ row }">
                <span class="mono sha-text" :title="row.manifest_sha256">
                  {{
                    row.manifest_sha256
                      ? row.manifest_sha256.slice(0, 20) + "…"
                      : "-"
                  }}
                </span>
              </template>

              <!-- 4. 质量评分 -->
              <template #quality_score="{ row }">
                <span
                  v-if="
                    row.quality_score !== null &&
                    row.quality_score !== undefined
                  "
                  class="quality-badge"
                >
                  {{ row.quality_score.toFixed(2) }}
                </span>
                <span v-else class="text-muted">未评分</span>
              </template>

              <!-- 5. 准入状态 -->
              <template #status="{ row }">
                <span
                  class="badge status-badge"
                  :class="
                    row.status === 'published'
                      ? 'active'
                      : row.status === 'retired'
                        ? 'error-badge'
                        : 'warn-badge'
                  "
                >
                  <span
                    class="status-dot"
                    :class="
                      row.status === 'published'
                        ? 'dot-active'
                        : row.status === 'retired'
                          ? 'dot-error'
                          : 'dot-warn'
                    "
                  />
                  {{ statusLabel(row.status) }}
                </span>
              </template>

              <!-- 6. 更新时间 -->
              <template #updated_at="{ row }">
                <span class="mono time-text">{{
                  formatTime(row.updated_at || row.created_at)
                }}</span>
              </template>

              <!-- 7. 操作 -->
              <template #actions="{ row }">
                <div class="table-actions-row">
                  <button
                    v-if="row.status === 'draft'"
                    class="button secondary tiny-btn"
                    :disabled="saving"
                    title="校验该版本数据完整性与 Manifest 指纹"
                    @click="transition(row, 'validated')"
                  >
                    <Check :size="11" />校验
                  </button>
                  <button
                    v-if="row.status === 'validated'"
                    class="button primary tiny-btn"
                    :disabled="saving"
                    title="正式发布至生产与训练流"
                    @click="transition(row, 'published')"
                  >
                    <UploadCloud :size="11" />发布
                  </button>
                  <button
                    v-if="row.status === 'published'"
                    class="button secondary tiny-btn retire-btn"
                    :disabled="saving"
                    title="下线退役该版本"
                    @click="transition(row, 'retired')"
                  >
                    <Archive :size="11" />退役
                  </button>
                  <span v-if="row.status === 'retired'" class="text-muted"
                    >已归档退役</span
                  >
                </div>
              </template>
            </DataTable>
          </section>
        </template>

        <!-- 未选择数据集时 -->
        <div v-else class="panel empty-workspace">
          <Database :size="42" class="empty-icon" />
          <h3>未选定数据集</h3>
          <p>请从左侧目录中选择或新建一个数据集以进行版本治理与生命周期管理</p>
          <button
            class="button primary tiny-btn"
            style="margin-top: 8px"
            @click="showCreateDatasetModal = true"
          >
            <Plus :size="13" />创建第一个数据集
          </button>
        </div>
      </main>
    </div>

    <!-- ==================== 模态弹窗 1：新建数据集 ==================== -->
    <div
      v-if="showCreateDatasetModal"
      class="modal-overlay"
      @click.self="showCreateDatasetModal = false"
    >
      <div class="modal-dialog modal-dialog-md" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div class="modal-title-box">
            <Database :size="17" class="modal-title-icon" />
            <div>
              <h3>新建数据集</h3>
              <p>创建新的数据集命名空间，定义数据用途、标注规范与授权边界</p>
            </div>
          </div>
        </div>
        <form @submit.prevent="createDataset">
          <div class="modal-body">
            <label class="form-field">
              <span class="field-label"
                >数据集名称 <em class="required">*</em></span
              >
              <input
                v-model="datasetForm.name"
                placeholder="例如: 2026年园区人像与行为特征样本库"
                class="field-input"
                required
                autofocus
              />
            </label>

            <label class="form-field" style="margin-top: 12px">
              <span class="field-label"
                >用途与授权边界详细说明 <em class="required">*</em></span
              >
              <textarea
                v-model="datasetForm.description"
                placeholder="请清晰记录该数据集的业务用途、标注规范、合规授权来源与使用边界说明..."
                class="field-input field-textarea"
                rows="4"
                required
              ></textarea>
            </label>
          </div>

          <div class="modal-actions">
            <button
              type="button"
              class="button secondary tiny-btn"
              @click="showCreateDatasetModal = false"
            >
              取消
            </button>
            <button
              type="submit"
              class="button primary tiny-btn"
              :disabled="saving || !datasetForm.name.trim()"
            >
              <Plus :size="13" />确认创建数据集
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- ==================== 模态弹窗 2：构建数据集新版本 ==================== -->
    <div
      v-if="showCreateVersionModal"
      class="modal-overlay"
      @click.self="showCreateVersionModal = false"
    >
      <div class="modal-dialog modal-dialog-lg" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div class="modal-title-box">
            <UploadCloud :size="17" class="modal-title-icon" />
            <div>
              <h3>构建数据集新版本 · {{ selectedDataset?.name }}</h3>
              <p>
                从数据资产库中勾选关联资产，打包并生成 Manifest SHA256 校验指纹
              </p>
            </div>
          </div>
        </div>
        <form @submit.prevent="createVersion">
          <div class="modal-body">
            <div class="form-grid-2col">
              <label class="form-field">
                <span class="field-label"
                  >版本号 (Version) <em class="required">*</em></span
                >
                <input
                  v-model="versionForm.version"
                  placeholder="例如: 2026.09.01 或 1.0.0"
                  class="field-input mono"
                  required
                />
              </label>

              <label class="form-field">
                <span class="field-label">质量评分 (0.00 ~ 1.00 可选)</span>
                <input
                  v-model="versionForm.quality_score"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  placeholder="例如: 0.95"
                  class="field-input mono"
                />
              </label>
            </div>

            <label class="form-field" style="margin-top: 10px">
              <div class="field-label-row">
                <span class="field-label"
                  >Manifest SHA-256 校验指纹 <em class="required">*</em></span
                >
                <button
                  type="button"
                  class="text-action-link"
                  @click="generateRandomSha256"
                >
                  <Sparkles :size="11" />重新自动生成摘要
                </button>
              </div>
              <input
                v-model="versionForm.manifest_sha256"
                minlength="64"
                maxlength="64"
                placeholder="64 位十六进制 SHA256 校验摘要"
                class="field-input mono"
                required
              />
            </label>

            <!-- 资产选择器 -->
            <div class="asset-selector-panel" style="margin-top: 12px">
              <div class="asset-selector-toolbar">
                <div class="selector-left">
                  <strong>选择要打包关联的数据资产：</strong>
                  <span class="badge count-badge"
                    >已选 {{ selectedAssetIds.length }} /
                    {{ filteredAssets.length }} 项</span
                  >
                </div>
                <div class="selector-right">
                  <div class="search-box search-sm">
                    <Search :size="12" class="search-icon" />
                    <input
                      v-model="assetSearchQuery"
                      placeholder="筛选资产..."
                      class="search-input"
                    />
                  </div>
                  <button
                    type="button"
                    class="button secondary tiny-btn select-toggle-btn"
                    :disabled="!filteredAssets.length"
                    @click="toggleSelectAllAssets"
                  >
                    {{
                      selectedAssetIds.length === filteredAssets.length &&
                      filteredAssets.length > 0
                        ? "取消全选"
                        : "全选"
                    }}
                  </button>
                </div>
              </div>

              <div
                v-if="filteredAssets.length"
                class="asset-selection-scroll-list"
              >
                <label
                  v-for="asset in filteredAssets"
                  :key="asset.asset_id"
                  class="asset-checkbox-item"
                >
                  <input
                    type="checkbox"
                    class="checkbox-input"
                    :checked="selectedAssetIds.includes(asset.asset_id)"
                    @change="toggleAsset(asset.asset_id)"
                  />
                  <div class="asset-type-icon">
                    <Video
                      v-if="asset.kind === 'video' || asset.kind === 'stream'"
                      :size="13"
                    />
                    <FileText v-else :size="13" />
                  </div>
                  <div class="asset-item-content">
                    <strong
                      class="asset-filename"
                      :title="asset.filename || asset.asset_id"
                    >
                      {{ asset.filename || asset.asset_id }}
                    </strong>
                    <small class="asset-meta-text">
                      <span class="mono">{{ asset.asset_id }}</span>
                      <span class="dot-sep">·</span>
                      <span>{{ asset.kind }}</span>
                      <span class="dot-sep">·</span>
                      <span>{{ formatBytes(asset.size_bytes) }}</span>
                    </small>
                  </div>
                </label>
              </div>
              <div v-else class="empty-selection-tip">
                暂无符合筛选条件的可用数据资产（可在「数据资产」页面上传新文件）
              </div>
            </div>
          </div>

          <div class="modal-actions">
            <button
              type="button"
              class="button secondary tiny-btn"
              @click="showCreateVersionModal = false"
            >
              取消
            </button>
            <button
              type="submit"
              class="button primary tiny-btn"
              :disabled="
                saving ||
                !versionForm.version.trim() ||
                versionForm.manifest_sha256.length !== 64
              "
            >
              <UploadCloud :size="13" />确认构建新版本 (关联
              {{ selectedAssetIds.length }} 项资产)
            </button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<style scoped>
.dataset-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.error-banner {
  padding: 8px 12px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  border-radius: 4px;
  font-size: 12px;
  margin: 0;
}

.success-banner {
  padding: 8px 12px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
  border-radius: 4px;
  font-size: 12px;
  margin: 0;
}

/* 顶部统计卡片 */
.stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 2px;
}

@media (max-width: 900px) {
  .stats {
    grid-template-columns: repeat(2, 1fr);
  }
}

.stat {
  padding: 10px 12px;
  background: #fff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  transition: all 0.15s ease;
}

.stat:hover {
  transform: translateY(-1px);
  border-color: var(--line-strong, #b7c2bd);
  box-shadow: 0 3px 8px rgba(0, 0, 0, 0.04);
}

.stat-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.stat-title {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--muted, #64716d);
}

.stat-icon-badge {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat.teal .stat-icon-badge {
  background: #f0fdfa;
  color: var(--color-accent, #087682);
  border: 1px solid #ccfbf1;
}

.stat.green .stat-icon-badge {
  background: #f0fdf4;
  color: #16a34a;
  border: 1px solid #dcfce7;
}

.stat.amber .stat-icon-badge {
  background: #fffbeb;
  color: #d97706;
  border: 1px solid #fef3c7;
}

.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--graphite, #17211f);
  line-height: 1.2;
  margin: 2px 0 1px;
}

.stat-desc {
  font-size: 10.5px;
  color: #8c9b97;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 工作台左右联动结构 */
.dataset-workbench-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 12px;
  align-items: start;
}

@media (max-width: 950px) {
  .dataset-workbench-layout {
    grid-template-columns: 1fr;
  }
}

/* 左侧侧边栏 */
.dataset-sidebar {
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header-box {
  padding: 10px 12px;
  background: #fafbfb;
  border-bottom: 1px solid var(--line, #e2e8e6);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sidebar-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.header-icon {
  color: var(--color-accent, #087682);
}

.sidebar-title-row h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: var(--graphite, #17211f);
}

.sidebar-filters-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sidebar-status-select {
  height: 22px;
  min-height: 22px;
  line-height: 20px;
  padding: 0 4px 0 6px;
  font-size: 11px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 3px;
  background: #ffffff;
  color: var(--graphite, #17211f);
  cursor: pointer;
  max-width: 105px;
  flex: 1;
  outline: none;
}
.sidebar-status-select:focus {
  border-color: var(--color-accent, #087682);
}

.dataset-cards-scroll {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  max-height: calc(100vh - 280px);
  min-height: 380px;
  overflow-y: auto;
}

.dataset-card-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s ease;
}

.dataset-card-item:hover {
  background: #ffffff;
  border-color: var(--line-strong, #b7c2bd);
}

.dataset-card-item.selected {
  background: var(--color-accent-soft, #e4f1f1);
  border-color: var(--color-accent, #087682);
  box-shadow: 0 1px 4px rgba(8, 118, 130, 0.1);
}

.card-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.card-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--graphite, #17211f);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-desc {
  margin: 0;
  font-size: 11px;
  color: var(--muted, #64716d);
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-footer-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 2px;
  font-size: 10px;
}

.card-id {
  color: #8c9b97;
}

.card-time {
  color: var(--muted, #64716d);
}

.empty-sidebar-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 12px;
  color: var(--muted, #64716d);
  gap: 6px;
}

/* 右侧工作区 */
.version-workspace {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.workspace-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  padding: 12px 14px;
}

.workspace-title-box {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dataset-heading-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.dataset-heading-row h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--graphite, #17211f);
}

.dataset-id-tag {
  font-size: 11px;
  color: var(--muted, #64716d);
  background: #eef2f1;
  padding: 1px 6px;
  border-radius: 4px;
}

.dataset-lead-desc {
  margin: 0;
  font-size: 11.5px;
  color: var(--muted, #64716d);
  line-height: 1.4;
}

.workspace-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* 面板通用 */
.panel {
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  background: #fafbfb;
}

.panel-header h3 {
  margin: 0;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--graphite, #17211f);
}

.count-badge {
  background: #edf2f0;
  color: #45534f;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
}

/* 数据表格深度规范 */
:deep(.dataset-table td),
:deep(.dataset-table th) {
  white-space: nowrap !important;
  vertical-align: middle;
  padding: 3px 8px !important;
  height: 28px !important;
  min-height: 28px !important;
  box-sizing: border-box;
  font-size: 11.5px;
}

:deep(.dataset-table th) {
  background: #fafbfb;
  font-weight: 600;
  color: var(--muted, #64716d);
}

.version-pill {
  color: var(--color-accent-hover, #065e67);
  font-size: 12px;
}

.bold {
  font-weight: 600;
}

.sha-text {
  color: var(--graphite, #17211f);
}

.quality-badge {
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  font-weight: 600;
  color: #166534;
  background: #dcfce7;
  padding: 1px 6px;
  border-radius: 3px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10.5px;
}
.status-badge.active {
  background: #dcfce7;
  color: #166534;
}
.status-badge.warn-badge {
  background: #fef3c7;
  color: #92400e;
}
.status-badge.error-badge {
  background: #fee2e2;
  color: #991b1b;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.dot-active {
  background: #16a34a;
}
.dot-warn {
  background: #d97706;
}
.dot-error {
  background: #dc2626;
}

.table-actions-row {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
}

.retire-btn {
  color: #d97706;
}

.time-text {
  font-size: 11px;
  color: var(--muted, #64716d);
}

.text-muted {
  color: var(--muted, #64716d);
}

.mono {
  font-family: var(--font-mono, monospace);
  font-size: 11.5px;
}

.empty-workspace {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 56px 16px;
  gap: 8px;
  text-align: center;
  color: var(--muted, #64716d);
}

.empty-workspace h3 {
  margin: 4px 0 0;
  font-size: 14px;
  color: var(--graphite, #17211f);
}

.empty-workspace p {
  margin: 0;
  font-size: 12px;
}

.empty-icon {
  color: #b7c2bd;
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  100% {
    transform: rotate(360deg);
  }
}

/* 模态弹窗 */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(17, 26, 24, 0.45);
  display: grid;
  place-items: center;
  z-index: 1000;
  padding: 16px;
}

.modal-dialog {
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 8px;
  box-shadow: 0 20px 50px rgba(15, 23, 21, 0.22);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-dialog-md {
  width: min(600px, 95vw);
}

.modal-dialog-lg {
  width: min(760px, 95vw);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  background: #fafbfb;
}

.modal-title-box {
  display: flex;
  align-items: center;
  gap: 10px;
}

.modal-title-icon {
  color: var(--color-accent, #087682);
}

.modal-title-box h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--graphite, #17211f);
}

.modal-title-box p {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--muted, #64716d);
}

.modal-body {
  padding: 16px 18px;
}

.form-grid-2col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.field-label {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--graphite, #17211f);
}

.text-action-link {
  background: none;
  border: none;
  color: var(--color-accent, #087682);
  font-size: 11px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 0;
}
.text-action-link:hover {
  text-decoration: underline;
}

.required {
  color: #dc2626;
  font-style: normal;
}

.field-input {
  height: 28px;
  padding: 0 8px;
  font-size: 11.5px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #ffffff;
  color: var(--graphite, #17211f);
  box-sizing: border-box;
  width: 100%;
}
.field-input:focus {
  border-color: var(--color-accent, #087682);
  outline: none;
}

.field-textarea {
  height: auto;
  padding: 6px 8px;
  line-height: 1.4;
  resize: vertical;
}

.asset-selector-panel {
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  padding: 10px 12px;
}

.asset-selector-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.selector-left {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11.5px;
  color: var(--graphite, #17211f);
}

.selector-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.select-toggle-btn {
  height: 26px !important;
  padding: 0 8px !important;
  font-size: 11px !important;
}

.asset-selection-scroll-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 180px;
  overflow-y: auto;
}

.asset-checkbox-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.12s ease;
}
.asset-checkbox-item:hover {
  background: #f8faf9;
  border-color: var(--line-strong, #b7c2bd);
}

.asset-type-icon {
  color: var(--color-accent, #087682);
  display: flex;
  align-items: center;
}

.asset-item-content {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  flex: 1;
}

.asset-filename {
  font-size: 11.5px;
  color: var(--graphite, #17211f);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-meta-text {
  font-size: 10.5px;
  color: var(--muted, #64716d);
}

.dot-sep {
  margin: 0 4px;
  opacity: 0.5;
}

.empty-selection-tip {
  font-size: 11px;
  color: var(--muted, #64716d);
  padding: 12px 0;
  text-align: center;
}

.modal-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid var(--line, #e2e8e6);
  background: #fafbfb;
}
</style>
