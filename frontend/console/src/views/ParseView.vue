<script setup lang="ts">
import { FileImage, Play, RefreshCw } from "@lucide/vue";
import { computed, ref, watch } from "vue";
import { api, idempotencyKey } from "../api";
import { labelDomain, labelPipeline, labelRunStatus } from "../labels";
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
    if (parsed.run.status !== "completed") error.value = parsed.run.termination_reason || parsed.run.error_code || labelRunStatus(parsed.run.status);
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
      <div><h1>{{ labelDomain(domain) }}解析</h1><p>{{ labelPipeline(pipeline) }} · 版本 0.1.0</p></div>
      <div class="toolbar"><label class="button secondary file-button"><FileImage :size="16" />选择图片<input type="file" accept="image/*" @change="selectFile" /></label><button class="button primary" :disabled="!file || loading" @click="execute"><Play :size="16" />运行</button></div>
    </div>
    <p v-if="error" class="callout error">{{ error }}</p>
    <div class="two-column parse-grid">
      <section class="panel"><div class="panel-header"><h2>输入</h2><span class="badge">{{ file?.name || "未选择" }}</span></div><div class="preview">
        <img v-if="imageUrl" :src="imageUrl" alt="" />
        <svg v-if="imageUrl && persons.length && unit" class="overlay" :viewBox="`0 0 ${unit.width} ${unit.height}`" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
          <rect v-for="person in persons" :key="person.object_id" class="box" :x="person.bbox?.x" :y="person.bbox?.y" :width="person.bbox?.width" :height="person.bbox?.height" />
        </svg>
        <div v-if="!imageUrl" class="empty">等待图片</div>
      </div></section>
      <section class="panel"><div class="panel-header"><h2>结果</h2><RefreshCw v-if="loading" :size="16" class="spin" /></div><div class="panel-body result-body">
        <template v-if="result"><div class="stats mini"><div class="stat teal"><span>对象</span><strong>{{ persons.length || ocrBlocks.length }}</strong></div><div class="stat green"><span>模型</span><strong>{{ result.models.length }}</strong></div></div>
          <div v-if="domain === 'portrait'" class="table-scroll"><table class="data-table"><thead><tr><th>标识</th><th>分数</th><th>边框</th></tr></thead><tbody><tr v-for="person in persons" :key="person.object_id"><td class="mono">{{ person.object_id }}</td><td>{{ person.score?.toFixed(3) }}</td><td class="mono">{{ person.bbox }}</td></tr></tbody></table></div>
          <textarea v-else readonly :value="ocrText"></textarea><details><summary>原始 JSON</summary><pre>{{ JSON.stringify(result, null, 2) }}</pre></details>
        </template><div v-else class="empty">暂无结果</div>
      </div></section>
    </div>
  </section>
</template>

<style scoped>
.file-button { position: relative; overflow: hidden; }.file-button input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.parse-grid { grid-template-columns: minmax(0, 1.2fr) minmax(340px, .8fr); }.preview { position: relative; min-height: 430px; display: grid; place-items: center; background: #f0f3f2; overflow: hidden; }.preview img, .overlay { position: absolute; width: 100%; height: 100%; object-fit: contain; }.overlay { pointer-events: none; }.box { fill: none; stroke: var(--coral); stroke-width: 2; vector-effect: non-scaling-stroke; }.mini { grid-template-columns: repeat(2, minmax(0, 1fr)); margin-bottom: 12px; }.result-body textarea { min-height: 190px; }pre { max-height: 320px; overflow: auto; padding: 12px; background: #101816; color: #dbe6e2; border-radius: 4px; font-size: 11px; }.spin { animation: spin .9s linear infinite; }@keyframes spin { to { transform: rotate(360deg); } }
</style>
