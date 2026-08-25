<script setup lang="ts">
import {
  Activity,
  ChevronDown,
  ChevronRight,
  Eye,
  Play,
  Plus,
  Trash2,
  Upload,
  Video,
  X,
} from "@lucide/vue";
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import type { Router } from "vue-router";
import { api, apiBlob, userFacingError } from "../api";
import { labelMediaKind } from "../labels";
import DataTable from "../components/DataTable.vue";
import type { MediaAsset, MediaSource, MediaSourceProbe, TableColumn } from "../types";

type AssetKindFilter = "" | "image" | "video" | "document";

const assetColumns: TableColumn<MediaAsset>[] = [
  { key: "select", label: "", width: "32px", class: "check-col", headerClass: "check-col" },
  { key: "asset_id", label: "标识", class: "mono truncate" },
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
const expandedAssets = reactive<Set<string>>(new Set());
const selectedForDelete = reactive<Set<string>>(new Set());

const filteredAssets = computed(() =>
  kindFilter.value
    ? assets.value.filter((item) => item.kind === kindFilter.value)
    : assets.value,
);

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

    <section class="panel asset-panel">
      <div class="panel-header">
        <div class="header-left">
          <h2>文件资产</h2>
          <div class="filter-row">
            <div class="segmented" role="group" aria-label="类型筛选">
              <button
                :class="{ active: kindFilter === '' }"
                @click="kindFilter = ''"
              >
                全部
              </button>
              <button
                :class="{ active: kindFilter === 'image' }"
                @click="kindFilter = 'image'"
              >
                图片
              </button>
              <button
                :class="{ active: kindFilter === 'video' }"
                @click="kindFilter = 'video'"
              >
                视频
              </button>
              <button
                :class="{ active: kindFilter === 'document' }"
                @click="kindFilter = 'document'"
              >
                文档
              </button>
            </div>
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
        :items="filteredAssets"
        :row-class="(asset: MediaAsset) => ({ 'selected-row': selectedForDelete.has(asset.asset_id) })"
        :empty-text="kindFilter ? `没有 ${labelMediaKind(kindFilter)} 类型的资产` : '暂无文件资产'"
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
                  expandedAssets.has(row.asset_id)
                    ? ChevronDown
                    : ChevronRight
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
          <tr
            v-if="expandedAssets.has(row.asset_id)"
            class="metadata-row"
          >
            <td :colspan="totalColspan">
              <dl class="metadata-list">
                <div
                  v-for="[label, value] in metadataItems(row)"
                  :key="label"
                >
                  <dt>{{ label }}</dt>
                  <dd>{{ value }}</dd>
                </div>
              </dl>
            </td>
          </tr>
        </template>
      </DataTable>
    </section>

    <section class="panel source-panel">
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
          <span
            v-if="probeText(row.source_id)"
            class="badge completed"
          >{{ probeText(row.source_id) }}</span>
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
.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}
.filter-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
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
.asset-panel .table-scroll {
  height: 380px;
  overflow-y: auto;
  scrollbar-width: thin;
}
.source-panel {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
}
.source-panel .table-scroll {
  height: 240px;
  overflow-y: auto;
  scrollbar-width: thin;
}
.table-scroll thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--color-table-header);
  box-shadow: inset 0 -1px 0 var(--line);
}
.table-scroll .empty {
  height: calc(100% - 34px);
  min-height: 140px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
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
