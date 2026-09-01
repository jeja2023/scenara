<script setup lang="ts">
import {
  Activity,
  ChevronDown,
  ChevronRight,
  Eye,
  FileText,
  Filter,
  Play,
  Plus,
  RotateCcw,
  Trash2,
  Upload,
  Video,
  X,
} from "@lucide/vue";
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import { useRefresh } from "../composables/useRefresh";
import { useRouter, type Router } from "vue-router";
import { api, apiBlob, userFacingError } from "../api";
import { labelMediaKind } from "../labels";
import DataTable from "../components/DataTable.vue";
import type {
  MediaAsset,
  MediaSource,
  MediaSourceProbe,
  TableColumn,
} from "../types";

type AssetKindFilter = "" | "image" | "video" | "document";
type AssetDomainFilter = "" | "fashion" | "portrait" | "behavior" | "ocr";
type MediaTab = "files" | "streams";

const PAGE_SIZE = 20;

const assetColumns: TableColumn<MediaAsset>[] = [
  {
    key: "select",
    label: "",
    width: "32px",
    class: "check-col",
    headerClass: "check-col",
  },
  { key: "asset_id", label: "标识", class: "mono truncate" },
  { key: "domain", label: "所属领域" },
  { key: "kind", label: "类型" },
  { key: "filename", label: "文件名", class: "truncate" },
  { key: "size_bytes", label: "大小" },
  { key: "created_at", label: "创建时间" },
  { key: "actions", label: "操作" },
];

const sourceColumns: TableColumn<MediaSource>[] = [
  { key: "source_id", label: "标识", class: "mono truncate" },
  { key: "name", label: "名称" },
  { key: "masked_url", label: "脱敏地址", class: "mono truncate" },
  { key: "status", label: "连接状态" },
  { key: "actions", label: "操作" },
];

const activeTab = ref<MediaTab>("files");
const loading = ref(false);
const uploading = ref(false);
const error = ref("");
const message = ref("");
const router: Router = useRouter();
const assets = ref<MediaAsset[]>([]);
const sources = ref<MediaSource[]>([]);
const probes = reactive<Record<string, MediaSourceProbe>>({});
const sourceForm = reactive({ name: "", url: "" });
const selectedAsset = ref<MediaAsset | null>(null);
const previewUrl = ref("");
const previewDialog = ref<HTMLDialogElement | null>(null);
const kindFilter = ref<AssetKindFilter>("");
const domainFilter = ref<AssetDomainFilter>("");
const offset = ref(0);
const expandedAssets = reactive<Set<string>>(new Set());
const selectedForDelete = reactive<Set<string>>(new Set());

const filteredAssets = computed(() =>
  assets.value.filter((item) => {
    const matchKind = !kindFilter.value || item.kind === kindFilter.value;
    const matchDomain =
      !domainFilter.value || item.domain === domainFilter.value;
    return matchKind && matchDomain;
  }),
);

const paginatedAssets = computed(() =>
  filteredAssets.value.slice(offset.value, offset.value + PAGE_SIZE),
);

function onPageChange(newOffset: number): void {
  offset.value = Math.max(0, newOffset);
}

watch([kindFilter, domainFilter], () => {
  offset.value = 0;
});

function resetFilters(): void {
  domainFilter.value = "";
  kindFilter.value = "";
  offset.value = 0;
}

const totalSizeBytes = computed(() =>
  filteredAssets.value.reduce((sum, item) => sum + item.size_bytes, 0),
);

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MiB`;
}

function readBlobAsDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") resolve(reader.result);
      else reject(new Error("media preview did not produce a data URL"));
    };
    reader.onerror = () =>
      reject(reader.error ?? new Error("无法读取媒体预览"));
    reader.readAsDataURL(blob);
  });
}

function revokePreviewUrl(): void {
  if (previewUrl.value.startsWith("blob:"))
    URL.revokeObjectURL(previewUrl.value);
}

function clearFeedback(): void {
  error.value = "";
  message.value = "";
}

async function refresh(): Promise<void> {
  loading.value = true;
  clearFeedback();
  try {
    const [assetPage, sourcePage] = await Promise.all([
      api<{ items: MediaAsset[] }>("/api/v1/media/assets?limit=200"),
      api<{ items: MediaSource[] }>("/api/v1/media/sources?limit=200"),
    ]);
    assets.value = assetPage.items;
    sources.value = sourcePage.items;
  } catch (caught) {
    error.value = userFacingError(caught, "数据资产加载失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}

async function upload(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const selected = Array.from(input.files ?? []);
  if (!selected.length) return;
  uploading.value = true;
  clearFeedback();
  try {
    for (const file of selected) {
      const form = new FormData();
      form.append("file", file);
      let kind: string;
      if (file.type.startsWith("image/")) kind = "image";
      else if (
        file.type === "application/pdf" ||
        file.name.toLowerCase().endsWith(".pdf")
      )
        kind = "document";
      else kind = "video";
      form.append("kind", kind);
      if (domainFilter.value) {
        form.append("domain", domainFilter.value);
      }
      await api<MediaAsset>("/api/v1/media/assets", {
        method: "POST",
        body: form,
      });
    }
    await refresh();
    message.value = `已上传 ${selected.length} 个文件资产`;
  } catch (caught) {
    error.value = userFacingError(
      caught,
      "文件上传失败，请确认文件有效且未超过大小限制",
    );
  } finally {
    uploading.value = false;
    input.value = "";
  }
}

async function createSource(): Promise<void> {
  clearFeedback();
  try {
    await api<MediaSource>("/api/v1/media/sources", {
      method: "POST",
      body: JSON.stringify({ name: sourceForm.name, url: sourceForm.url }),
    });
    sourceForm.name = "";
    sourceForm.url = "";
    await refresh();
    message.value = "视频流源已登记";
  } catch (caught) {
    error.value = userFacingError(
      caught,
      "视频流源登记失败，请检查地址和网络策略",
    );
  }
}

async function preview(asset: MediaAsset): Promise<void> {
  closePreview();
  clearFeedback();
  try {
    const blob = await apiBlob(
      `/api/v1/media/assets/${encodeURIComponent(asset.asset_id)}/preview`,
    );
    previewUrl.value = await readBlobAsDataUrl(blob);
    selectedAsset.value = asset;
    previewDialog.value?.showModal();
  } catch (caught) {
    error.value = userFacingError(caught, "文件预览加载失败");
  }
}

function closePreview(): void {
  revokePreviewUrl();
  previewUrl.value = "";
  selectedAsset.value = null;
  previewDialog.value?.close();
}

async function deleteAsset(asset: MediaAsset): Promise<void> {
  if (
    !window.confirm(`确认删除文件资产"${asset.filename || asset.asset_id}"？`)
  )
    return;
  clearFeedback();
  try {
    await api<void>(
      `/api/v1/media/assets/${encodeURIComponent(asset.asset_id)}`,
      { method: "DELETE" },
    );
    selectedForDelete.delete(asset.asset_id);
    await refresh();
    message.value = "文件资产已删除";
  } catch (caught) {
    error.value = userFacingError(
      caught,
      "文件资产删除失败，请检查关联运行状态",
    );
  }
}

async function deleteSelected(): Promise<void> {
  if (!selectedForDelete.size) return;
  if (!window.confirm(`确认删除选中的 ${selectedForDelete.size} 个文件资产？`))
    return;
  clearFeedback();
  let succeeded = 0;
  let failed = 0;
  for (const id of [...selectedForDelete]) {
    try {
      await api<void>(`/api/v1/media/assets/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      selectedForDelete.delete(id);
      succeeded++;
    } catch {
      failed++;
    }
  }
  await refresh();
  if (failed) {
    error.value = `已删除 ${succeeded} 个，${failed} 个因关联运行无法删除`;
  } else {
    message.value = `已删除 ${succeeded} 个文件资产`;
  }
}

async function probeSource(source: MediaSource): Promise<void> {
  clearFeedback();
  try {
    probes[source.source_id] = await api<MediaSourceProbe>(
      `/api/v1/media/sources/${encodeURIComponent(source.source_id)}/probe`,
      { method: "POST" },
    );
    message.value = "视频流连接正常";
  } catch (caught) {
    error.value = userFacingError(
      caught,
      "视频流探测失败，请检查源状态和网络策略",
    );
  }
}

async function deleteSource(source: MediaSource): Promise<void> {
  if (!window.confirm(`确认删除视频流源"${source.name}"？`)) return;
  clearFeedback();
  try {
    await api<void>(
      `/api/v1/media/sources/${encodeURIComponent(source.source_id)}`,
      { method: "DELETE" },
    );
    delete probes[source.source_id];
    await refresh();
    message.value = "视频流源已删除";
  } catch (caught) {
    error.value = userFacingError(
      caught,
      "视频流源删除失败，请检查关联运行状态",
    );
  }
}

function launch(resource: MediaAsset | MediaSource): void {
  const isSource = "source_id" in resource;
  void router.push({
    path: "/parse",
    query: isSource
      ? { source: (resource as MediaSource).source_id }
      : { asset: (resource as MediaAsset).asset_id },
  });
}

function toggleExpand(assetId: string): void {
  if (expandedAssets.has(assetId)) expandedAssets.delete(assetId);
  else expandedAssets.add(assetId);
}

function toggleSelect(assetId: string): void {
  if (selectedForDelete.has(assetId)) selectedForDelete.delete(assetId);
  else selectedForDelete.add(assetId);
}

function metadataItems(asset: MediaAsset): Array<[string, string]> {
  const data = asset.metadata;
  const result: Array<[string, string]> = [];
  if (data.width && data.height)
    result.push(["尺寸", `${data.width} × ${data.height}`]);
  if (data.duration_ms)
    result.push(["时长", `${(data.duration_ms / 1000).toFixed(1)} 秒`]);
  if (data.fps) result.push(["帧率", `${data.fps.toFixed(2)} fps`]);
  if (data.codec || data.format)
    result.push(["编码", data.codec || data.format || ""]);
  if (data.frame_count) result.push(["帧数", String(data.frame_count)]);
  if (data.page_count) result.push(["页数", String(data.page_count)]);
  result.push(["SHA-256", asset.sha256.slice(0, 16) + "…"]);
  return result;
}

function probeText(sourceId: string): string {
  const probe = probes[sourceId];
  return probe ? `可连接 · ${probe.latency_ms} 毫秒` : "";
}

onMounted(refresh);
onBeforeUnmount(closePreview);
useRefresh(refresh);
</script>

<template>
  <section class="page">
    <p v-if="error" class="callout error">{{ error }}</p>
    <p v-if="message" class="callout success">{{ message }}</p>

    <div class="tabs-header-bar">
      <div class="domain-tabs" role="tablist" aria-label="数据资产类型切换">
        <button
          type="button"
          class="domain-tab-btn"
          :class="{ active: activeTab === 'files' }"
          role="tab"
          :aria-selected="activeTab === 'files'"
          @click="activeTab = 'files'"
        >
          <FileText :size="13" />
          <span>文件资产</span>
          <span class="tab-badge">{{ assets.length }}</span>
        </button>
        <button
          type="button"
          class="domain-tab-btn"
          :class="{ active: activeTab === 'streams' }"
          role="tab"
          :aria-selected="activeTab === 'streams'"
          @click="activeTab = 'streams'"
        >
          <Video :size="13" />
          <span>视频流源</span>
          <span class="tab-badge">{{ sources.length }}</span>
        </button>
      </div>
    </div>

    <section v-if="activeTab === 'files'" class="panel asset-panel">
      <div class="panel-header">
        <div class="header-left">
          <h2>文件资产</h2>
          <div class="filter-controls">
            <div class="filter-heading">
              <Filter :size="14" />
              <span>筛选记录</span>
            </div>
            <select v-model="domainFilter" aria-label="所属领域筛选">
              <option value="">全部领域</option>
              <option value="fashion">服饰风格</option>
              <option value="portrait">人像解析</option>
              <option value="behavior">行为分析</option>
              <option value="ocr">文字识别</option>
            </select>
            <select v-model="kindFilter" aria-label="类型筛选">
              <option value="">全部类型</option>
              <option value="image">图片</option>
              <option value="video">视频</option>
              <option value="document">文档</option>
            </select>
            <button class="button secondary reset-btn" @click="resetFilters">
              <RotateCcw :size="13" />重置
            </button>
            <span class="badge">{{ filteredAssets.length }}</span>
            <span class="size-total">{{ formatBytes(totalSizeBytes) }}</span>
          </div>
        </div>
        <div class="header-actions">
          <button
            v-if="selectedForDelete.size"
            class="button danger header-btn"
            @click="deleteSelected"
          >
            <Trash2 :size="13" />批量删除 {{ selectedForDelete.size }} 个
          </button>
          <label class="button primary file-button header-btn">
            <Upload :size="13" />{{ uploading ? "上传中" : "上传文件" }}
            <input
              type="file"
              multiple
              accept="image/*,video/*,.mkv,.avi,.mov,.mp4,.webm,application/pdf,.pdf"
              :disabled="uploading"
              @change="upload"
            />
          </label>
        </div>
      </div>
      <DataTable
        :columns="assetColumns"
        :items="paginatedAssets"
        :loading="loading"
        :total="filteredAssets.length"
        :offset="offset"
        :page-size="PAGE_SIZE"
        :index-offset="offset"
        :row-class="
          (asset: MediaAsset) => ({
            'selected-row': selectedForDelete.has(asset.asset_id),
          })
        "
        :empty-text="
          kindFilter || domainFilter
            ? '没有符合当前筛选条件的资产'
            : '暂无文件资产'
        "
        @page-change="onPageChange"
      >
        <template #header-select>
          <span class="check-col"></span>
        </template>
        <template #select="{ row }">
          <input
            type="checkbox"
            :checked="selectedForDelete.has(row.asset_id)"
            :aria-label="`选择 ${row.filename || row.asset_id}`"
            @change="toggleSelect(row.asset_id)"
          />
        </template>
        <template #domain="{ row }">
          <span
            v-if="row.domain === 'fashion'"
            class="badge domain-badge-fashion"
            >服饰风格</span
          >
          <span
            v-else-if="row.domain === 'portrait'"
            class="badge domain-badge-portrait"
            >人像解析</span
          >
          <span
            v-else-if="row.domain === 'behavior'"
            class="badge domain-badge-behavior"
            >行为分析</span
          >
          <span v-else-if="row.domain === 'ocr'" class="badge domain-badge-ocr"
            >文字识别</span
          >
          <span v-else class="badge domain-badge-general">通用公共</span>
        </template>
        <template #kind="{ row }">
          <span class="badge" :class="row.kind">{{
            labelMediaKind(row.kind)
          }}</span>
        </template>
        <template #filename="{ row }">
          {{ row.filename || "未命名" }}
          <span v-if="row.temporary" class="badge">临时</span>
        </template>
        <template #size_bytes="{ row }">
          {{ formatBytes(row.size_bytes) }}
        </template>
        <template #created_at="{ row }">
          {{ new Date(row.created_at * 1000).toLocaleString() }}
        </template>
        <template #actions="{ row }">
          <div class="toolbar compact">
            <button
              class="icon-button"
              :title="`${expandedAssets.has(row.asset_id) ? '收起' : '展开'}元数据`"
              :aria-label="`${expandedAssets.has(row.asset_id) ? '收起' : '展开'}元数据`"
              @click="toggleExpand(row.asset_id)"
            >
              <component
                :is="
                  expandedAssets.has(row.asset_id) ? ChevronDown : ChevronRight
                "
                :size="13"
              />
            </button>
            <button
              class="icon-button"
              title="预览"
              aria-label="预览"
              @click="preview(row)"
            >
              <Eye :size="13" />
            </button>
            <button
              v-if="row.kind === 'video'"
              class="icon-button"
              title="预览视频首帧"
              aria-label="预览视频首帧"
              @click="preview(row)"
            >
              <Video :size="13" />
            </button>
            <button class="button secondary" @click="launch(row)">
              <Play :size="12" />解析
            </button>
            <button
              class="icon-button danger-icon"
              title="删除"
              aria-label="删除"
              @click="deleteAsset(row)"
            >
              <Trash2 :size="13" />
            </button>
          </div>
        </template>
        <template #subrow="{ row, totalColspan }">
          <tr v-if="expandedAssets.has(row.asset_id)" class="metadata-row">
            <td :colspan="totalColspan">
              <dl class="metadata-list">
                <div v-for="[label, value] in metadataItems(row)" :key="label">
                  <dt>{{ label }}</dt>
                  <dd>{{ value }}</dd>
                </div>
              </dl>
            </td>
          </tr>
        </template>
      </DataTable>
    </section>

    <section v-else-if="activeTab === 'streams'" class="panel source-panel">
      <div class="panel-header">
        <div class="header-left">
          <h2>视频流源</h2>
          <span class="badge">{{ sources.length }}</span>
        </div>
      </div>
      <div class="source-create-bar">
        <div class="source-input-group">
          <span class="field-label">源名称</span>
          <input
            v-model.trim="sourceForm.name"
            maxlength="256"
            placeholder="例如：主入口监控"
            @keyup.enter="createSource"
          />
        </div>
        <div class="source-input-group url-group">
          <span class="field-label">RTSP 地址</span>
          <input
            v-model.trim="sourceForm.url"
            maxlength="4096"
            placeholder="rtsp://host:port/path"
            @keyup.enter="createSource"
          />
        </div>
        <button
          class="button primary source-btn"
          :disabled="!sourceForm.name || !sourceForm.url"
          @click="createSource"
        >
          <Plus :size="13" />登记视频流
        </button>
      </div>
      <DataTable
        :columns="sourceColumns"
        :items="sources"
        empty-text="暂无视频流源"
      >
        <template #status="{ row }">
          <span v-if="probeText(row.source_id)" class="badge completed">{{
            probeText(row.source_id)
          }}</span>
          <span v-else class="muted">未探测</span>
        </template>
        <template #actions="{ row }">
          <div class="toolbar compact">
            <button
              class="icon-button"
              title="探测连接"
              aria-label="探测连接"
              @click="probeSource(row)"
            >
              <Activity :size="13" />
            </button>
            <button class="button secondary" @click="launch(row)">
              <Play :size="12" />解析
            </button>
            <button
              class="icon-button danger-icon"
              title="删除"
              aria-label="删除"
              @click="deleteSource(row)"
            >
              <Trash2 :size="13" />
            </button>
          </div>
        </template>
      </DataTable>
    </section>

    <dialog ref="previewDialog" class="modal preview-modal">
      <div class="modal-header">
        <div>
          <h2>{{ selectedAsset?.filename || selectedAsset?.asset_id }}</h2>
          <p>
            {{
              selectedAsset
                ? formatBytes(selectedAsset.size_bytes) +
                  " · " +
                  labelMediaKind(selectedAsset.kind)
                : ""
            }}
          </p>
        </div>
        <button
          class="icon-button"
          title="关闭"
          aria-label="关闭"
          @click="closePreview"
        >
          <X :size="18" />
        </button>
      </div>
      <img
        v-if="previewUrl"
        :src="previewUrl"
        alt="文件预览"
        class="preview-media"
      />
    </dialog>
  </section>
</template>

<style scoped>
.tabs-header-bar {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}

.domain-tabs {
  display: inline-flex;
  align-items: center;
  background: #eef2f1;
  padding: 3px;
  border-radius: 6px;
  gap: 3px;
  flex-wrap: wrap;
}

.domain-tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: var(--muted, #64716d);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.domain-tab-btn:hover {
  color: var(--graphite, #17211f);
  background: rgba(255, 255, 255, 0.6);
}

.domain-tab-btn.active {
  color: var(--color-accent-hover, #065e67);
  background: var(--color-accent-soft, #e4f1f1);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  font-weight: 600;
}

.tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 16px;
  min-width: 16px;
  padding: 0 5px;
  border-radius: 10px;
  font-size: 10.5px;
  background: rgba(0, 0, 0, 0.06);
  color: inherit;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}
.filter-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.filter-heading {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 650;
  color: var(--color-text);
  margin-right: 2px;
  white-space: nowrap;
}
.filter-heading svg {
  color: var(--teal);
}
.filter-controls select {
  width: 140px;
  min-width: 110px;
  height: 28px;
  min-height: 28px;
  padding: 0 8px;
  font-size: 12px;
  border: 1px solid var(--line, #cbd3d0);
  border-radius: 4px;
  background-color: var(--color-surface, #fff);
  color: var(--color-text, #17211f);
}
.filter-controls .reset-btn {
  height: 28px;
  min-height: 28px;
  padding: 0 8px;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.size-total {
  color: var(--muted);
  font-size: 12px;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.header-btn {
  height: 28px;
  min-height: 28px;
  padding: 0 10px;
  font-size: 12px;
  gap: 5px;
  border-radius: 4px;
}
.file-button {
  position: relative;
  overflow: hidden;
}
.file-button input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
.asset-panel {
  display: flex;
  flex-direction: column;
}
.asset-panel :deep(.data-table-container) {
  display: flex;
  flex-direction: column;
}
.asset-panel :deep(.table-scroll) {
  height: 560px;
  min-height: 560px;
  max-height: 560px;
  overflow-y: auto;
  scrollbar-width: thin;
  background: #fff;
}
.source-panel {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
}
.source-panel :deep(.data-table-container) {
  display: flex;
  flex-direction: column;
}
.source-panel :deep(.table-scroll) {
  height: 220px;
  min-height: 220px;
  max-height: 220px;
  overflow-y: auto;
  scrollbar-width: thin;
  background: #fff;
}
:deep(.table-scroll thead th) {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--color-table-header, #fafbfb);
  box-shadow: inset 0 -1px 0 var(--line);
}
:deep(.table-empty-cell) {
  height: 180px;
  vertical-align: middle;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}
.source-create-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: var(--surface-soft);
  border-bottom: 1px solid var(--line);
  flex-wrap: wrap;
}
@media (max-width: 900px) {
  .header-btn,
  .source-btn,
  .source-input-group input {
    min-height: 44px;
    height: 44px;
  }
  .compact .button,
  .compact .icon-button {
    min-height: 44px;
    height: 44px;
  }
  .compact .icon-button {
    width: 44px;
    min-width: 44px;
  }
}
.source-input-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 1 220px;
}
.source-input-group.url-group {
  flex: 1 1 320px;
}
.field-label {
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}
.source-input-group input {
  height: 30px;
  min-height: 30px;
  padding: 0 10px;
  font-size: 12.5px;
  border-radius: 4px;
  border: 1px solid var(--line);
  background: var(--color-surface);
  width: 100%;
}
.source-btn {
  height: 30px;
  min-height: 30px;
  padding: 0 12px;
  font-size: 12.5px;
  white-space: nowrap;
  flex-shrink: 0;
  border-radius: 4px;
}
.compact {
  gap: 4px;
  flex-wrap: nowrap;
}
.danger-icon {
  color: var(--danger);
}
.check-col {
  width: 32px;
  padding: 0 6px;
  text-align: center;
}
.selected-row td {
  background: var(--color-selection);
}
.metadata-row td {
  padding: 8px 12px;
  background: var(--surface-soft);
  border-top: 1px solid var(--line);
}
.metadata-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0 24px;
  margin: 0;
}
.metadata-list div {
  display: grid;
  gap: 2px;
  min-width: 120px;
}
.metadata-list dt {
  color: var(--muted);
  font-size: 11px;
}
.metadata-list dd {
  font-size: 12px;
  font-weight: 700;
  overflow-wrap: anywhere;
  margin: 0;
}
.preview-modal {
  width: min(820px, calc(100% - 32px));
}
.preview-media {
  display: block;
  max-width: 100%;
  max-height: 72vh;
  margin: auto;
  object-fit: contain;
  background: #101816;
}
.spin {
  animation: spin 0.9s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.domain-badge-fashion {
  background: rgba(139, 92, 246, 0.12);
  color: #8b5cf6;
  border: 1px solid rgba(139, 92, 246, 0.28);
  font-weight: 600;
}
.domain-badge-portrait {
  background: rgba(59, 130, 246, 0.12);
  color: #3b82f6;
  border: 1px solid rgba(59, 130, 246, 0.28);
  font-weight: 600;
}
.domain-badge-behavior {
  background: rgba(245, 158, 11, 0.12);
  color: #f59e0b;
  border: 1px solid rgba(245, 158, 11, 0.28);
  font-weight: 600;
}
.domain-badge-ocr {
  background: rgba(16, 185, 129, 0.12);
  color: #10b981;
  border: 1px solid rgba(16, 185, 129, 0.28);
  font-weight: 600;
}
.domain-badge-general {
  background: var(--surface-soft, rgba(148, 163, 184, 0.12));
  color: var(--muted, #94a3b8);
  border: 1px solid var(--line, rgba(148, 163, 184, 0.2));
}
@media (max-width: 760px) {
  .source-create-bar {
    flex-direction: column;
    align-items: stretch;
  }
  .source-input-group,
  .source-input-group.url-group {
    flex: 1 1 auto;
  }
}
</style>
