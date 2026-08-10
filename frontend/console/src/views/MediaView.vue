<script setup lang="ts">
import {
  Activity,
  ChevronDown,
  ChevronRight,
  Eye,
  Play,
  RefreshCw,
  Trash2,
  Upload,
  Video,
  X,
} from "@lucide/vue";
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { api, apiBlob, userFacingError } from "../api";
import { labelMediaKind } from "../labels";
import type { MediaAsset, MediaSource, MediaSourceProbe } from "../types";

type AssetKindFilter = "" | "image" | "video" | "document";

const loading = ref(false);
const uploading = ref(false);
const error = ref("");
const message = ref("");
const router = useRouter();
const assets = ref<MediaAsset[]>([]);
const sources = ref<MediaSource[]>([]);
const probes = reactive<Record<string, MediaSourceProbe>>({});
const sourceForm = reactive({ name: "", url: "" });
const selectedAsset = ref<MediaAsset | null>(null);
const previewUrl = ref("");
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
  } catch (caught) {
    error.value = userFacingError(caught, "文件预览加载失败");
  }
}

function closePreview(): void {
  revokePreviewUrl();
  previewUrl.value = "";
  selectedAsset.value = null;
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
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div>
        <h1>数据资产</h1>
        <p>统一管理可重复使用的图片、视频、文档文件与视频流来源。</p>
      </div>
      <div class="toolbar">
        <button
          v-if="selectedForDelete.size"
          class="button danger"
          @click="deleteSelected"
        >
          批量删除 {{ selectedForDelete.size }} 个
        </button>
        <label class="button primary file-button"
          ><Upload :size="16" />{{ uploading ? "上传中" : "上传文件"
          }}<input
            type="file"
            multiple
            accept="image/*,video/*,.mkv,.avi,.mov,.mp4,.webm,application/pdf,.pdf"
            :disabled="uploading"
            @change="upload"
        /></label>
        <button class="button secondary" :disabled="loading" @click="refresh">
          <RefreshCw :size="16" :class="{ spin: loading }" />刷新
        </button>
      </div>
    </div>
    <p v-if="error" class="callout error">{{ error }}</p>
    <p v-if="message" class="callout success">{{ message }}</p>

    <section class="panel">
      <div class="panel-header">
        <div class="header-row">
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
      </div>
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th class="check-col"></th>
              <th style="width: 50px">序号</th>
              <th>标识</th>
              <th>类型</th>
              <th>文件名</th>
              <th>大小</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <template
              v-for="(asset, index) in filteredAssets"
              :key="asset.asset_id"
            >
              <tr
                :class="{
                  'selected-row': selectedForDelete.has(asset.asset_id),
                }"
              >
                <td class="check-col">
                  <input
                    type="checkbox"
                    :checked="selectedForDelete.has(asset.asset_id)"
                    :aria-label="`选择 ${asset.filename || asset.asset_id}`"
                    @change="toggleSelect(asset.asset_id)"
                  />
                </td>
                <td class="muted">{{ index + 1 }}</td>
                <td class="mono truncate">{{ asset.asset_id }}</td>
                <td>
                  <span class="badge" :class="asset.kind">{{
                    labelMediaKind(asset.kind)
                  }}</span>
                </td>
                <td class="truncate">
                  {{ asset.filename || "未命名" }}
                  <span v-if="asset.temporary" class="badge">临时</span>
                </td>
                <td>{{ formatBytes(asset.size_bytes) }}</td>
                <td>
                  {{ new Date(asset.created_at * 1000).toLocaleString() }}
                </td>
                <td>
                  <div class="toolbar compact">
                    <button
                      class="icon-button"
                      :title="`${expandedAssets.has(asset.asset_id) ? '收起' : '展开'}元数据`"
                      :aria-label="`${expandedAssets.has(asset.asset_id) ? '收起' : '展开'}元数据`"
                      @click="toggleExpand(asset.asset_id)"
                    >
                      <component
                        :is="
                          expandedAssets.has(asset.asset_id)
                            ? ChevronDown
                            : ChevronRight
                        "
                        :size="15"
                      />
                    </button>
                    <button
                      class="icon-button"
                      title="预览"
                      aria-label="预览"
                      @click="preview(asset)"
                    >
                      <Eye :size="15" />
                    </button>
                    <button
                      v-if="asset.kind === 'video'"
                      class="icon-button"
                      title="预览视频首帧"
                      aria-label="预览视频首帧"
                      @click="preview(asset)"
                    >
                      <Video :size="15" />
                    </button>
                    <button class="button secondary" @click="launch(asset)">
                      <Play :size="14" />解析
                    </button>
                    <button
                      class="icon-button danger-icon"
                      title="删除"
                      aria-label="删除"
                      @click="deleteAsset(asset)"
                    >
                      <Trash2 :size="15" />
                    </button>
                  </div>
                </td>
              </tr>
              <tr
                v-if="expandedAssets.has(asset.asset_id)"
                class="metadata-row"
              >
                <td colspan="8">
                  <dl class="metadata-list">
                    <div
                      v-for="[label, value] in metadataItems(asset)"
                      :key="label"
                    >
                      <dt>{{ label }}</dt>
                      <dd>{{ value }}</dd>
                    </div>
                  </dl>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
        <div v-if="!filteredAssets.length" class="empty">
          {{
            kindFilter
              ? `没有 ${labelMediaKind(kindFilter)} 类型的资产`
              : "暂无文件资产"
          }}
        </div>
      </div>
    </section>

    <section class="panel source-panel">
      <div class="panel-header">
        <h2>视频流源</h2>
        <span class="badge">{{ sources.length }}</span>
      </div>
      <div class="panel-body source-create">
        <label
          ><span>名称</span
          ><input v-model.trim="sourceForm.name" maxlength="256"
        /></label>
        <label
          ><span>地址</span
          ><input
            v-model.trim="sourceForm.url"
            maxlength="4096"
            placeholder="rtsp://host/path"
        /></label>
        <button
          class="button primary"
          :disabled="!sourceForm.name || !sourceForm.url"
          @click="createSource"
        >
          登记
        </button>
      </div>
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width: 50px">序号</th>
              <th>标识</th>
              <th>名称</th>
              <th>脱敏地址</th>
              <th>连接状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(source, index) in sources" :key="source.source_id">
              <td class="muted">{{ index + 1 }}</td>
              <td class="mono">{{ source.source_id }}</td>
              <td>{{ source.name }}</td>
              <td class="mono truncate">{{ source.masked_url }}</td>
              <td>
                <span
                  v-if="probeText(source.source_id)"
                  class="badge completed"
                  >{{ probeText(source.source_id) }}</span
                ><span v-else class="muted">未探测</span>
              </td>
              <td>
                <div class="toolbar compact">
                  <button
                    class="icon-button"
                    title="探测连接"
                    aria-label="探测连接"
                    @click="probeSource(source)"
                  >
                    <Activity :size="15" /></button
                  ><button class="button secondary" @click="launch(source)">
                    <Play :size="14" />解析</button
                  ><button
                    class="icon-button danger-icon"
                    title="删除"
                    aria-label="删除"
                    @click="deleteSource(source)"
                  >
                    <Trash2 :size="15" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!sources.length" class="empty">暂无视频流源</div>
      </div>
    </section>

    <dialog :open="!!selectedAsset" class="modal preview-modal">
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
.header-row {
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
.source-panel {
  margin-top: 14px;
}
.source-create {
  display: grid;
  grid-template-columns: minmax(180px, 0.5fr) minmax(280px, 1.5fr) auto;
  align-items: end;
  gap: 10px;
  border-bottom: 1px solid var(--line);
}
.source-create label {
  display: grid;
  gap: 5px;
}
.source-create label span {
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}
.compact {
  gap: 5px;
  flex-wrap: nowrap;
}
.danger-icon {
  color: var(--danger);
}
.check-col {
  width: 36px;
  padding: 0 8px;
}
.selected-row td {
  background: #f0f9f6;
}
.metadata-row td {
  padding: 10px 14px 12px;
  background: #f8faf9;
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
  .source-create {
    grid-template-columns: 1fr;
  }
}
</style>
