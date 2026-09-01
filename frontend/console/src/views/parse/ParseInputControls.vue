<script setup lang="ts">
import { Eye, Library, RefreshCw, Upload } from "@lucide/vue";
import { ref } from "vue";
import type { MediaMode } from "../../composables/useDomainCatalog";
import type {
  MediaAsset,
  MediaSource,
  PipelineParameterDefinition,
} from "../../types";

type InputOrigin = "library" | "upload";
type SampleStrategy = "interval" | "keyframe" | "scene_change" | "uniform";

const assetId = defineModel<string>("assetId", { required: true });
const connectTimeoutMs = defineModel<number>("connectTimeoutMs", {
  required: true,
});
const frameMaxEdge = defineModel<number | null>("frameMaxEdge", {
  required: true,
});
const inputOrigin = defineModel<InputOrigin>("inputOrigin", { required: true });
const maxReconnectAttempts = defineModel<number>("maxReconnectAttempts", {
  required: true,
});
const pageScale = defineModel<number>("pageScale", { required: true });
const pipelineParameters = defineModel<Record<string, unknown>>(
  "pipelineParameters",
  { required: true },
);
const readTimeoutMs = defineModel<number>("readTimeoutMs", { required: true });
const sampleEndMs = defineModel<number | null>("sampleEndMs", {
  required: true,
});
const sampleIntervalMs = defineModel<number>("sampleIntervalMs", {
  required: true,
});
const sampleStartMs = defineModel<number>("sampleStartMs", { required: true });
const sampleStrategy = defineModel<SampleStrategy>("sampleStrategy", {
  required: true,
});
const sceneChangeThreshold = defineModel<number>("sceneChangeThreshold", {
  required: true,
});
const sourceId = defineModel<string>("sourceId", { required: true });
const sourceName = defineModel<string>("sourceName", { required: true });
const sourceUrl = defineModel<string>("sourceUrl", { required: true });

defineProps<{
  booleanParameterEntries: [string, PipelineParameterDefinition][];
  compactFieldEntriesCount: number;
  fieldParameterEntries: [string, PipelineParameterDefinition][];
  file: File | null;
  filteredAssets: MediaAsset[];
  formatOptionLabel: (key: string, option: string) => string;
  hasParameters: boolean;
  isParameterWide: (
    key: string,
    definition: PipelineParameterDefinition,
  ) => boolean;
  loadingSources: boolean;
  mode: MediaMode;
  sources: MediaSource[];
  strategyLabels: Record<SampleStrategy, string>;
}>();

const emit = defineEmits<{
  previewStream: [];
  refreshSources: [];
  refreshWorkspace: [];
  selectFile: [event: Event];
  selectLibraryAsset: [];
  selectOrigin: [origin: InputOrigin];
  selectSource: [sourceId: string];
}>();

function selectSource(): void {
  emit("selectSource", sourceId.value);
}

const showAdvancedParameters = ref(false);
</script>

<template>
  <div class="input-controls">
    <template v-if="mode !== 'stream'">
      <div class="input-origin">
        <span class="control-label">数据来源</span>
        <div class="segmented origin-modes" role="group" aria-label="数据来源">
          <button
            :class="{ active: inputOrigin === 'upload' }"
            :aria-pressed="inputOrigin === 'upload'"
            @click="emit('selectOrigin', 'upload')"
          >
            <Upload :size="15" />当前上传
          </button>
          <button
            :class="{ active: inputOrigin === 'library' }"
            :aria-pressed="inputOrigin === 'library'"
            @click="emit('selectOrigin', 'library')"
          >
            <Library :size="15" />资产库
          </button>
        </div>
      </div>

      <label v-if="inputOrigin === 'upload'" class="file-picker">
        <span>{{
          mode === "image"
            ? "图片文件"
            : mode === "document"
              ? "PDF 文档"
              : "视频文件"
        }}</span>
        <input
          type="file"
          :accept="
            mode === 'image'
              ? 'image/*'
              : mode === 'document'
                ? 'application/pdf,.pdf'
                : 'video/*,.mkv,.avi,.mov,.mp4,.webm'
          "
          @change="emit('selectFile', $event)"
        />
        <small v-if="file" class="file-info-hint"
          >已就绪 · {{ (file.size / (1024 * 1024)).toFixed(2) }} MB</small
        >
      </label>

      <div v-else class="library-picker-row">
        <label>
          <span>文件资产</span>
          <select v-model="assetId" @change="emit('selectLibraryAsset')">
            <option value="">
              选择{{
                mode === "image"
                  ? "图片"
                  : mode === "document"
                    ? "文档"
                    : "视频"
              }}
            </option>
            <option
              v-for="asset in filteredAssets"
              :key="asset.asset_id"
              :value="asset.asset_id"
            >
              {{ asset.filename || asset.asset_id
              }}{{ asset.temporary ? " · 临时" : "" }}
            </option>
          </select>
        </label>
        <button
          class="icon-button source-refresh"
          :disabled="loadingSources"
          title="刷新资产库"
          aria-label="刷新资产库"
          @click="emit('refreshWorkspace')"
        >
          <RefreshCw :size="16" :class="{ spin: loadingSources }" />
        </button>
      </div>
    </template>

    <template v-else>
      <div class="library-picker-row">
        <label>
          <span>已登记视频流</span>
          <select v-model="sourceId" @change="selectSource">
            <option value="">登记新视频流</option>
            <option
              v-for="source in sources"
              :key="source.source_id"
              :value="source.source_id"
            >
              {{ source.name }} · {{ source.masked_url }}
            </option>
          </select>
        </label>
        <button
          class="icon-button source-refresh"
          :disabled="loadingSources"
          title="刷新视频流"
          aria-label="刷新视频流"
          @click="emit('refreshSources')"
        >
          <RefreshCw :size="16" :class="{ spin: loadingSources }" />
        </button>
      </div>
      <template v-if="!sourceId">
        <label>
          <span>视频流名称</span>
          <input
            v-model.trim="sourceName"
            maxlength="256"
            placeholder="例如：东门摄像头"
          />
        </label>
        <label>
          <span>视频流地址</span>
          <div class="stream-url-field">
            <input
              v-model.trim="sourceUrl"
              maxlength="4096"
              placeholder="rtsp://host/path"
            />
            <button
              type="button"
              class="button small secondary stream-preview-btn"
              :disabled="!sourceUrl"
              title="立即从视频流拉取首帧画面作为底图预览"
              @click="emit('previewStream')"
            >
              <Eye :size="13" /><span>预览首帧</span>
            </button>
          </div>
        </label>
      </template>
    </template>

    <div v-if="mode === 'document'" class="parameter-grid">
      <label
        ><span>渲染倍率</span
        ><input
          v-model.number="pageScale"
          type="number"
          min="0.5"
          max="4"
          step="0.5"
      /></label>
    </div>

    <template v-else-if="mode !== 'image'">
      <div class="parameter-grid">
        <label>
          <span>采样策略</span>
          <select v-model="sampleStrategy">
            <option
              v-for="(text, value) in strategyLabels"
              :key="value"
              :value="value"
            >
              {{ text }}
            </option>
          </select>
        </label>
        <label
          ><span>采样间隔（毫秒）</span
          ><input
            v-model.number="sampleIntervalMs"
            type="number"
            min="1"
            max="3600000"
            step="100"
            :disabled="sampleStrategy !== 'interval'"
        /></label>
      </div>
      <button
        type="button"
        class="button secondary advanced-parameters-toggle"
        :aria-expanded="showAdvancedParameters"
        @click="showAdvancedParameters = !showAdvancedParameters"
      >
        {{ showAdvancedParameters ? "收起高级参数" : "展开高级参数" }}
      </button>
      <div v-if="showAdvancedParameters" class="parameter-grid">
        <label
          ><span>{{
            mode === "stream" ? "开始后跳过（毫秒）" : "起始时间（毫秒）"
          }}</span
          ><input
            v-model.number="sampleStartMs"
            type="number"
            min="0"
            step="1000"
        /></label>
        <label
          ><span>{{
            mode === "stream" ? "最大分析时长（毫秒）" : "结束时间（毫秒）"
          }}</span
          ><input
            v-model.number="sampleEndMs"
            type="number"
            min="0"
            step="1000"
            placeholder="不限"
        /></label>
        <label v-if="sampleStrategy === 'scene_change'"
          ><span>场景切换阈值</span
          ><input
            v-model.number="sceneChangeThreshold"
            type="number"
            min="0.01"
            max="1"
            step="0.05"
        /></label>
        <label
          ><span>帧最大边长（像素）</span
          ><input
            v-model.number="frameMaxEdge"
            type="number"
            min="64"
            max="8192"
            step="64"
            placeholder="原始尺寸"
        /></label>
        <template v-if="mode === 'stream'">
          <label
            ><span>最大重连次数</span
            ><input
              v-model.number="maxReconnectAttempts"
              type="number"
              min="0"
              max="20"
          /></label>
          <label
            ><span>连接超时（毫秒）</span
            ><input
              v-model.number="connectTimeoutMs"
              type="number"
              min="100"
              max="120000"
              step="100"
          /></label>
          <label
            ><span>读取超时（毫秒）</span
            ><input
              v-model.number="readTimeoutMs"
              type="number"
              min="100"
              max="120000"
              step="100"
          /></label>
        </template>
      </div>
    </template>

    <div v-if="hasParameters" class="domain-parameters">
      <span class="control-label domain-params-heading">领域参数配置</span>
      <div
        v-if="booleanParameterEntries.length"
        class="domain-switches-row"
        role="group"
        aria-label="领域参数选项"
      >
        <button
          v-for="[key, definition] in booleanParameterEntries"
          :key="key"
          type="button"
          class="switch-pill"
          :class="{ active: Boolean(pipelineParameters[key]) }"
          :aria-pressed="Boolean(pipelineParameters[key])"
          :title="definition.description"
          @click="pipelineParameters[key] = !Boolean(pipelineParameters[key])"
        >
          {{ definition.label }}
        </button>
      </div>
      <div
        v-if="fieldParameterEntries.length"
        class="parameter-grid"
        :class="{
          'cols-3': compactFieldEntriesCount === 3,
          'cols-2': compactFieldEntriesCount === 2,
        }"
      >
        <label
          v-for="[key, definition] in fieldParameterEntries"
          :key="key"
          :class="{ 'parameter-wide': isParameterWide(key, definition) }"
        >
          <span>{{ definition.label }}</span>
          <input
            v-if="['integer', 'number'].includes(definition.control)"
            v-model.number="pipelineParameters[key]"
            type="number"
            :min="definition.minimum ?? undefined"
            :max="definition.maximum ?? undefined"
            :step="definition.step ?? undefined"
          />
          <select
            v-else-if="definition.control === 'select'"
            v-model="pipelineParameters[key]"
          >
            <option
              v-for="option in definition.options ?? []"
              :key="option"
              :value="option"
            >
              {{ formatOptionLabel(key, option) }}
            </option>
          </select>
          <input
            v-else
            v-model="pipelineParameters[key]"
            type="text"
            :placeholder="definition.placeholder ?? undefined"
          />
        </label>
      </div>
    </div>
  </div>
</template>

<style scoped>
.input-controls {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.input-controls label,
.file-picker {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.input-origin {
  display: grid;
  gap: 6px;
}
.input-controls label > span,
.control-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--muted);
}
.origin-modes {
  width: fit-content;
}
.origin-modes button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.file-picker input[type="file"] {
  display: flex;
  align-items: center;
  height: 36px;
  min-height: 36px;
  padding: 4px 6px;
  border: 1px solid var(--line, #cbd5e1);
  border-radius: 4px;
  background: var(--surface, #fff);
  font-size: 12px;
  color: var(--muted, #64748b);
  cursor: pointer;
  box-sizing: border-box;
}
.file-picker input[type="file"]::file-selector-button {
  height: 26px;
  line-height: 24px;
  padding: 0 12px;
  margin-right: 10px;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  background: #f8fafc;
  color: #334155;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.file-info-hint {
  color: #047857;
  font-weight: 600;
  font-size: 11.5px;
}
.library-picker-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 34px;
  gap: 8px;
  align-items: end;
}
.library-picker-row .source-refresh {
  position: static;
  height: 34px;
  width: 34px;
  min-height: 34px;
  min-width: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: var(--surface);
}
.stream-url-field {
  display: flex;
  gap: 8px;
  align-items: center;
}
.stream-url-field input {
  flex: 1;
  min-width: 0;
}
.stream-preview-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.parameter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 8px 10px;
  align-items: end;
}
.parameter-grid label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.parameter-grid label > span {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.parameter-grid input:not([type="checkbox"]):not([type="radio"]),
.parameter-grid select {
  height: 32px;
  min-height: 32px;
  padding: 4px 8px;
  font-size: 12.5px;
  border-radius: 4px;
}
.domain-parameters {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 6px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
}
.domain-params-heading {
  display: block;
}
.parameter-wide {
  grid-column: 1 / -1;
}
.domain-parameters .parameter-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 10px;
}
.domain-parameters .parameter-grid.cols-3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.domain-parameters .parameter-grid.cols-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.domain-switches-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 8px;
  align-items: center;
  margin-bottom: 6px;
}
.switch-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 5px 12px;
  background: var(--surface, #fff);
  border: 1px solid var(--line, #cbd5e1);
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-soft, #475569);
  cursor: pointer;
}
.switch-pill.active {
  background: #ecfdf5;
  border-color: #10b981;
  color: #047857;
  font-weight: 600;
}
.spin {
  animation: spin 0.9s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
@media (max-width: 520px) {
  .input-controls {
    margin-top: 12px;
  }
  .origin-modes {
    width: 100%;
  }
  .origin-modes button {
    flex: 1;
  }
  .parameter-grid {
    grid-template-columns: 1fr;
  }
}
</style>
