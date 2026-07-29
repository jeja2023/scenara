<script setup lang="ts">
import { FileImage, Play, RefreshCw } from "@lucide/vue";
import { computed, ref, watch } from "vue";
import { api, idempotencyKey } from "../api";
import type { Domain, ResultEnvelope, Run } from "../types";

const props = defineProps<{ domain: Domain }>();
const file = ref<File | null>(null);
const imageUrl = ref("");
const loading = ref(false);
const error = ref("");
const run = ref<Run | null>(null);
const result = ref<ResultEnvelope | null>(null);
const pipeline = computed(() => props.domain === "portrait" ? "portrait.person-detection" : "ocr.document");
const persons = computed(() => result.value?.domain_payload.domain === "portrait" ? result.value.domain_payload.persons : []);
const ocrBlocks = computed(() => result.value?.domain_payload.domain === "ocr" ? result.value.domain_payload.blocks : []);
const ocrText = computed(() => result.value?.domain_payload.domain === "ocr" ? result.value.domain_payload.text : "");
const unit = computed(() => result.value?.units[0]);

watch(() => props.domain, () => { run.value = null; result.value = null; error.value = ""; });

function selectFile(event: Event): void {
  const selected = (event.target as HTMLInputElement).files?.[0] ?? null;
  file.value = selected;
  if (imageUrl.value) URL.revokeObjectURL(imageUrl.value);
  imageUrl.value = selected ? URL.createObjectURL(selected) : "";
  run.value = null;
  result.value = null;
  error.value = "";
}

async function execute(): Promise<void> {
  if (!file.value) return;
  loading.value = true;
  error.value = "";
  try {
    const form = new FormData();
    form.append("file", file.value);
    form.append("domain", props.domain);
    form.append("pipeline_id", pipeline.value);
    const parsed = await api<{ run: Run; result: ResultEnvelope | null }>("/api/v1/parse/image", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey(props.domain) },
      body: form,
    });
    run.value = parsed.run;
    result.value = parsed.result;
    if (parsed.run.status !== "completed") error.value = parsed.run.termination_reason || parsed.run.error_code || parsed.run.status;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : String(caught);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div><h1>{{ domain === "portrait" ? "Portrait" : "OCR / Document" }}</h1><p>{{ pipeline }}@0.1.0</p></div>
      <div class="toolbar"><label class="button secondary file-button"><FileImage :size="16" />选择图片<input type="file" accept="image/*" @change="selectFile" /></label><button class="button primary" :disabled="!file || loading" @click="execute"><Play :size="16" />运行</button></div>
    </div>
    <p v-if="error" class="callout error">{{ error }}</p>
    <div class="two-column parse-grid">
      <section class="panel"><div class="panel-header"><h2>输入</h2><span class="badge">{{ file?.name || "未选择" }}</span></div><div class="preview">
        <img v-if="imageUrl" :src="imageUrl" alt="" />
        <div v-if="imageUrl && persons.length && unit" class="overlay"><span v-for="person in persons" :key="person.object_id" class="box" :style="person.bbox ? { left: `${(person.bbox.x / unit.width) * 100}%`, top: `${(person.bbox.y / unit.height) * 100}%`, width: `${(person.bbox.width / unit.width) * 100}%`, height: `${(person.bbox.height / unit.height) * 100}%` } : {}"></span></div>
        <div v-if="!imageUrl" class="empty">等待图片</div>
      </div></section>
      <section class="panel"><div class="panel-header"><h2>结果</h2><RefreshCw v-if="loading" :size="16" class="spin" /></div><div class="panel-body result-body">
        <template v-if="result"><div class="stats mini"><div class="stat teal"><span>Objects</span><strong>{{ persons.length || ocrBlocks.length }}</strong></div><div class="stat green"><span>Models</span><strong>{{ result.models.length }}</strong></div></div>
          <div v-if="domain === 'portrait'" class="table-scroll"><table class="data-table"><thead><tr><th>ID</th><th>Score</th><th>BBox</th></tr></thead><tbody><tr v-for="person in persons" :key="person.object_id"><td class="mono">{{ person.object_id }}</td><td>{{ person.score?.toFixed(3) }}</td><td class="mono">{{ person.bbox }}</td></tr></tbody></table></div>
          <textarea v-else readonly :value="ocrText"></textarea><details><summary>Raw JSON</summary><pre>{{ JSON.stringify(result, null, 2) }}</pre></details>
        </template><div v-else class="empty">暂无结果</div>
      </div></section>
    </div>
  </section>
</template>

<style scoped>
.file-button { position: relative; overflow: hidden; }.file-button input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.parse-grid { grid-template-columns: minmax(0, 1.2fr) minmax(340px, .8fr); }.preview { position: relative; min-height: 430px; display: grid; place-items: center; background: #f0f3f2; overflow: hidden; }.preview img { max-width: 100%; max-height: 70vh; object-fit: contain; }.overlay { position: absolute; inset: 0; pointer-events: none; }.box { position: absolute; border: 2px solid var(--coral); box-shadow: 0 0 0 1px #fff inset; }.mini { grid-template-columns: repeat(2, minmax(0, 1fr)); margin-bottom: 12px; }.result-body textarea { min-height: 190px; }pre { max-height: 320px; overflow: auto; padding: 12px; background: #101816; color: #dbe6e2; border-radius: 4px; font-size: 11px; }.spin { animation: spin .9s linear infinite; }@keyframes spin { to { transform: rotate(360deg); } }
</style>
