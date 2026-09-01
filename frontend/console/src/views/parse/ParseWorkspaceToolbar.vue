<script setup lang="ts">
import {
  Clock3,
  FileImage,
  FileText,
  Pause,
  Play,
  Radio,
  Search,
  Square,
  Video,
} from "@lucide/vue";
import type { MediaMode } from "../../composables/useDomainCatalog";
import { labelPipeline } from "../../labels";
import type {
  Domain,
  DomainManifest,
  MediaKind,
  Pipeline,
  Run,
} from "../../types";

const domainSearch = defineModel<string>("domainSearch", { required: true });
const pipelineId = defineModel<string>("pipelineId", { required: true });

defineProps<{
  availableDomains: DomainManifest[];
  domain: Domain;
  domainPipelines: Pipeline[];
  hasResult: boolean;
  inputReady: boolean;
  isDomainScoped: boolean;
  loading: boolean;
  mode: MediaMode;
  run: Run | null;
  supportedMediaKinds: MediaKind[];
  transitioning: boolean;
}>();

const emit = defineEmits<{
  execute: [];
  openResult: [];
  openRuns: [];
  resetResult: [];
  selectDomain: [domain: Domain];
  selectMode: [mode: MediaMode];
  transitionRun: [action: "pause" | "resume" | "cancel"];
}>();

function selectDomain(event: Event): void {
  emit("selectDomain", (event.target as HTMLSelectElement).value);
}
</script>

<template>
  <div class="workbench-config">
    <div v-if="!isDomainScoped">
      <span class="control-label">解析能力</span>
      <div
        v-if="availableDomains.length <= 4"
        class="segmented capability-modes"
        role="group"
        aria-label="解析能力"
      >
        <button
          v-for="item in availableDomains"
          :key="item.domain_id"
          :class="{ active: domain === item.domain_id }"
          :aria-pressed="domain === item.domain_id"
          @click="emit('selectDomain', item.domain_id)"
        >
          {{ item.display_name }}
        </button>
      </div>
      <div v-else class="domain-search-picker">
        <div class="search-field">
          <Search :size="15" />
          <input
            v-model.trim="domainSearch"
            type="search"
            placeholder="搜索领域名称或标识"
            aria-label="搜索领域"
          />
        </div>
        <select :value="domain" aria-label="解析领域" @change="selectDomain">
          <option
            v-for="item in availableDomains"
            :key="item.domain_id"
            :value="item.domain_id"
          >
            {{ item.display_name }} · {{ item.domain_id }}
          </option>
        </select>
      </div>
    </div>
    <div class="segmented media-modes" role="tablist" aria-label="数据类型">
      <button
        v-if="supportedMediaKinds.includes('image')"
        :class="{ active: mode === 'image' }"
        role="tab"
        :aria-selected="mode === 'image'"
        @click="emit('selectMode', 'image')"
      >
        <FileImage :size="16" />图片
      </button>
      <button
        v-if="supportedMediaKinds.includes('document')"
        :class="{ active: mode === 'document' }"
        role="tab"
        :aria-selected="mode === 'document'"
        @click="emit('selectMode', 'document')"
      >
        <FileText :size="16" />文档
      </button>
      <button
        v-if="supportedMediaKinds.includes('video')"
        :class="{ active: mode === 'video' }"
        role="tab"
        :aria-selected="mode === 'video'"
        @click="emit('selectMode', 'video')"
      >
        <Video :size="16" />视频
      </button>
      <button
        v-if="supportedMediaKinds.includes('stream')"
        :class="{ active: mode === 'stream' }"
        role="tab"
        :aria-selected="mode === 'stream'"
        @click="emit('selectMode', 'stream')"
      >
        <Radio :size="16" />视频流
      </button>
    </div>
    <label class="pipeline-picker">
      <span class="control-label">流水线</span>
      <select
        v-model="pipelineId"
        :disabled="!domainPipelines.length"
        @change="emit('resetResult')"
      >
        <option v-if="!domainPipelines.length" value="">暂无可用流水线</option>
        <option
          v-for="item in domainPipelines"
          :key="item.pipeline_id + ':' + item.version"
          :value="item.pipeline_id"
        >
          {{ labelPipeline(item.pipeline_id) }} · {{ item.version }}
        </option>
      </select>
    </label>
    <nav class="parse-context-nav" aria-label="解析工作区操作">
      <button
        v-if="run && !['completed', 'failed', 'cancelled'].includes(run.status)"
        class="button danger"
        :disabled="transitioning"
        @click="emit('transitionRun', 'cancel')"
      >
        <Square :size="15" />{{
          run.status === "cancelling" ? "强制取消" : "取消运行"
        }}
      </button>
      <button
        v-if="run?.status === 'running'"
        class="button secondary"
        :disabled="transitioning"
        @click="emit('transitionRun', 'pause')"
      >
        <Pause :size="15" />暂停
      </button>
      <button
        v-if="run?.status === 'paused'"
        class="button secondary"
        :disabled="transitioning"
        @click="emit('transitionRun', 'resume')"
      >
        <Play :size="15" />恢复
      </button>
      <button
        class="button primary"
        :disabled="!inputReady || loading"
        @click="emit('execute')"
      >
        <Play :size="16" />{{ loading ? "运行中" : "开始解析" }}
      </button>
      <button class="button secondary" @click="emit('openRuns')">
        <Clock3 :size="16" />查看历史运行
      </button>
      <button
        v-if="hasResult && run"
        class="button secondary"
        @click="emit('openResult')"
      >
        <FileText :size="16" />查看结构化结果
      </button>
    </nav>
  </div>
</template>

<style scoped>
.workbench-config {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--line);
  flex-wrap: wrap;
}
.workbench-config > div:not(.media-modes),
.pipeline-picker {
  display: grid;
  gap: 6px;
}
.control-label {
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}
.capability-modes {
  width: fit-content;
}
.capability-modes button,
.media-modes button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.pipeline-picker {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1 1 200px;
  max-width: 380px;
  min-width: 180px;
}
.media-modes {
  display: inline-flex;
  align-items: center;
  flex-direction: row;
  width: fit-content;
  margin-bottom: 0;
}
.parse-context-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-left: auto;
}
.parse-context-nav a {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 5px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 650;
  text-decoration: none;
  background: var(--surface);
}
.domain-search-picker {
  display: grid;
  gap: 7px;
  min-width: min(100%, 420px);
}
.search-field {
  display: flex;
  align-items: center;
  gap: 7px;
  min-height: 34px;
  padding: 0 9px;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--muted);
}
.search-field input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
}
@media (max-width: 520px) {
  .workbench-config {
    display: grid;
    align-items: stretch;
  }
  .parse-context-nav {
    width: 100%;
    overflow-x: auto;
    flex-wrap: nowrap;
    justify-content: flex-start;
    padding-bottom: 2px;
  }
  .parse-context-nav a {
    flex: 0 0 auto;
  }
  .pipeline-picker {
    max-width: none;
  }
  .domain-search-picker {
    min-width: 0;
  }
  .capability-modes {
    width: 100%;
  }
  .capability-modes button {
    flex: 1;
  }
  .media-modes {
    width: 100%;
  }
  .media-modes button {
    flex: 1;
    min-width: 0;
  }
}
</style>
