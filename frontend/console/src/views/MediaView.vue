<script setup lang="ts">
import { RefreshCw, Upload } from "@lucide/vue";
import { onMounted, reactive, ref } from "vue";
import { api, userFacingError } from "../api";
import { labelMediaKind } from "../labels";
import type { MediaAsset, MediaSource } from "../types";

const loading = ref(false);
const error = ref("");
const assets = ref<MediaAsset[]>([]);
const sources = ref<MediaSource[]>([]);
const sourceForm = reactive({ name: "", url: "" });

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [assetPage, sourcePage] = await Promise.all([
      api<{ items: MediaAsset[] }>("/api/v1/media/assets"),
      api<{ items: MediaSource[] }>("/api/v1/media/sources"),
    ]);
    assets.value = assetPage.items;
    sources.value = sourcePage.items;
  } catch (caught) {
    error.value = userFacingError(caught, "媒体数据加载失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}

async function upload(event: Event): Promise<void> {
  const selected = Array.from((event.target as HTMLInputElement).files ?? []);
  for (const file of selected) {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", file.type.startsWith("image/") ? "image" : file.type === "application/pdf" ? "document" : "video");
    await api<MediaAsset>("/api/v1/media/assets", { method: "POST", body: form });
  }
  await refresh();
}

async function createSource(): Promise<void> {
  await api<MediaSource>("/api/v1/media/sources", {
    method: "POST",
    body: JSON.stringify({ name: sourceForm.name, url: sourceForm.url }),
  });
  sourceForm.name = "";
  sourceForm.url = "";
  await refresh();
}

onMounted(refresh);
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div><h1>媒体</h1><p>资产与流源。</p></div>
      <div class="toolbar"><label class="button primary file-button"><Upload :size="16" />上传<input type="file" multiple @change="upload" /></label><button class="button secondary" :disabled="loading" @click="refresh"><RefreshCw :size="16" />刷新</button></div>
    </div>
    <p v-if="error" class="callout error">{{ error }}</p>
    <div class="two-column">
      <section class="panel"><div class="panel-header"><h2>资产</h2><span class="badge">{{ assets.length }}</span></div><div class="table-scroll"><table class="data-table"><thead><tr><th>标识</th><th>类型</th><th>文件</th><th>大小</th><th>创建时间</th></tr></thead><tbody>
        <tr v-for="asset in assets" :key="asset.asset_id"><td class="mono">{{ asset.asset_id }}</td><td>{{ labelMediaKind(asset.kind) }}</td><td class="truncate">{{ asset.filename }}</td><td>{{ (asset.size_bytes / 1024).toFixed(1) }} KB</td><td>{{ new Date(asset.created_at * 1000).toLocaleString() }}</td></tr>
      </tbody></table><div v-if="!assets.length" class="empty">暂无资产</div></div></section>
      <section class="panel"><div class="panel-header"><h2>源</h2><span class="badge">{{ sources.length }}</span></div><div class="panel-body">
        <div class="form-grid"><label><span>名称</span><input v-model="sourceForm.name" /></label><label><span>地址</span><input v-model="sourceForm.url" /></label></div>
        <button class="button primary source-submit" :disabled="!sourceForm.name || !sourceForm.url" @click="createSource">登记</button>
        <div class="table-scroll"><table class="data-table"><tbody><tr v-for="source in sources" :key="source.source_id"><td class="mono">{{ source.source_id }}</td><td>{{ source.name }}</td><td class="truncate">{{ source.masked_url }}</td></tr></tbody></table></div>
      </div></section>
    </div>
  </section>
</template>

<style scoped>
.file-button { position: relative; overflow: hidden; }.file-button input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }.source-submit { margin: 12px 0 16px; }
</style>
