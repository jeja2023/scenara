<script setup lang="ts">
import { AlertTriangle } from "@lucide/vue";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api, idempotencyKey, userFacingError } from "../api";
import {
  useDomainCatalog,
  type MediaMode,
} from "../composables/useDomainCatalog";
import { useMediaPreview } from "../composables/useMediaPreview";
import { useRefresh } from "../composables/useRefresh";
import {
  labelDomain,
  labelPipeline,
  labelRunError,
  labelRunStatus,
  labelTerminationReason,
  labelWarning,
} from "../labels";
import type {
  Domain,
  MediaAsset,
  MediaSource,
  ResultEnvelope,
  Run,
  RunPage,
} from "../types";
import ResultDetailDrawer from "../components/ResultDetailDrawer.vue";
import ParseHistoryPanel from "./parse/ParseHistoryPanel.vue";
import ParseInputControls from "./parse/ParseInputControls.vue";
import ParseMediaPreview from "./parse/ParseMediaPreview.vue";
import ParseWorkspaceToolbar from "./parse/ParseWorkspaceToolbar.vue";
import { useParseMediaInput } from "./parse/useParseMediaInput";
import { useParseParameters } from "./parse/useParseParameters";
import { useRoiSelection } from "./parse/useRoiSelection";
import { useResultPreview } from "./parse/useResultPreview";
import { useRunTracker } from "./parse/useRunTracker";

type InputOrigin = "library" | "upload";
const props = defineProps<{ initialDomain?: Domain }>();
const route = useRoute();
const router = useRouter();

function queryValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function isMediaMode(value: string): value is MediaMode {
  return ["image", "video", "document", "stream"].includes(value);
}

function resolveInitialDomain(): Domain {
  const routeDomain = queryValue(route.params?.domain);
  const queryDomain = queryValue(route.query.domain);
  return props.initialDomain ?? (routeDomain || queryDomain || "portrait");
}

function resolveInitialMode(): MediaMode {
  const routeMode = queryValue(route.params?.mediaKind);
  const queryMode = queryValue(route.query.mediaKind);
  if (isMediaMode(routeMode)) return routeMode;
  if (isMediaMode(queryMode)) return queryMode;
  return "image";
}

const domain = ref<Domain>(resolveInitialDomain());
const mode = ref<MediaMode>(resolveInitialMode());
const inputOrigin = ref<InputOrigin>("upload");
const file = ref<File | null>(null);
const domainSearch = ref("");
const assets = ref<MediaAsset[]>([]);
const assetId = ref("");
const pipelineId = ref("");
const pipelineParameters = ref<Record<string, unknown>>({});
const pipelineParameterDefaults = ref<Record<string, unknown>>({});
const sources = ref<MediaSource[]>([]);
const sourceId = ref("");
const sourceName = ref("");
const sourceUrl = ref("");

// 抽样参数

const loading = ref(false);
const transitioning = ref(false);
const loadingSources = ref(false);
const error = ref("");
const run = ref<Run | null>(null);
const result = ref<ResultEnvelope | null>(null);
const selectedUnitIndex = ref(0);
const followLatestUnit = ref(true);
const progressDetail = ref("");
const showWarnings = ref(false);
const historyRuns = ref<Run[]>([]);
const loadingHistory = ref(false);

function syncRunToHistory(r: Run): void {
  if (!r?.run_id || !Array.isArray(historyRuns.value)) return;
  const index = historyRuns.value.findIndex((item) => item.run_id === r.run_id);
  if (index >= 0) {
    historyRuns.value = historyRuns.value.map((item, idx) =>
      idx === index
        ? {
            ...item,
            status: r.status,
            progress: r.progress,
            completed_at: r.completed_at ?? item.completed_at,
            termination_reason: r.termination_reason ?? item.termination_reason,
            error_code: r.error_code ?? item.error_code,
          }
        : item,
    );
  } else {
    historyRuns.value = [{ ...r }, ...historyRuns.value];
  }
}
const {
  domainPipelines,
  availableDomains,
  selectedDomainManifest,
  supportedMediaKinds,
  selectedPipeline,
  parameterEntries,
  filteredAssets,
  selectedAsset,
  selectedSource,
  refreshSources,
  refreshWorkspaceResources,
  syncPipelineSelection,
  syncPipelineParameterDefaults,
  ensureSupportedMode,
} = useDomainCatalog({
  domain,
  mode,
  domainSearch,
  assetId,
  sourceId,
  pipelineId,
  pipelineParameters,
  pipelineParameterDefaults,
  assets,
  sources,
  loadingSources,
  error,
  onModeChange: selectMode,
});

const {
  mediaUrl,
  serverPreviewUrl,
  streamPreviewUrl,
  videoPlaybackFailed,
  clearMediaUrl,
  handleImageError,
  handleVideoError,
  loadServerPreview,
  loadStreamPreview,
} = useMediaPreview(file);

const {
  ensureSource,
  previewNewStream,
  selectAssetById,
  selectFile,
  selectLibraryAsset,
  uploadSelectedAsset,
} = useParseMediaInput({
  assetId,
  assets,
  clearMediaUrl,
  domain,
  file,
  inputOrigin,
  loadServerPreview,
  loadStreamPreview,
  mediaUrl,
  mode,
  onPreviewError: (caught) => {
    error.value = userFacingError(
      caught,
      "获取视频流首帧预览失败，请检查流地址与网络连通性",
    );
  },
  resetResult,
  serverPreviewUrl,
  sourceId,
  sourceName,
  sourceUrl,
  sources,
});

const selectedUnit = computed(
  () => result.value?.units[selectedUnitIndex.value] ?? result.value?.units[0],
);

const {
  clearRoi,
  disposeRoiSelection,
  getMediaContentBounds,
  handleRoiMouseDown,
  isDrawingRoi,
  mediaStageRef,
  onStageResize,
  roiCurrent,
  roiStart,
  selectedRoi,
  setMediaStage,
  stageRectVersion,
  toggleRoiDrawing,
} = useRoiSelection(pipelineParameters, selectedUnit);

const {
  applyRunParameters,
  booleanParameterEntries,
  compactFieldEntriesCount,
  connectTimeoutMs,
  fieldParameterEntries,
  formatOptionLabel,
  frameMaxEdge,
  isParameterWide,
  maxReconnectAttempts,
  pageScale,
  readTimeoutMs,
  runParameters,
  sampleEndMs,
  sampleIntervalMs,
  sampleStartMs,
  sampleStrategy,
  samplingValid,
  sceneChangeThreshold,
  STRATEGY_LABELS,
} = useParseParameters({
  mode,
  parameterEntries,
  pipelineParameterDefaults,
  pipelineParameters,
  selectedPipeline,
  selectedRoi,
});

const inputReady = computed(() => {
  const hasInput =
    mode.value === "stream"
      ? !!sourceId.value || (!!sourceName.value && !!sourceUrl.value)
      : inputOrigin.value === "library"
        ? !!assetId.value
        : !!file.value;
  return (
    hasInput &&
    !!selectedPipeline.value &&
    (mode.value === "image" || samplingValid.value)
  );
});

const {
  clearOverlay,
  displayedMediaUrl,
  handleResultFrameLoaded,
  handleVideoPause,
  handleVideoPlaybackError,
  handleVideoPlay,
  handleVideoSeeked,
  overlayReady,
  overlayStatus,
  prefersResultFramePreview,
  resetResultPreview,
  resultFrameUrl,
  setOverlayCanvas,
  setVideoElement,
  shouldUseResultFrame,
  syncSelectedMediaFrame,
  syncVideoToSelectedUnit,
  videoElement,
  videoPlaying,
} = useResultPreview({
  followLatestUnit,
  handleVideoError,
  mediaUrl,
  mode,
  result,
  run,
  selectedUnit,
  selectedUnitIndex,
  serverPreviewUrl,
  videoPlaybackFailed,
});

const roiBoxStyle = computed(() => {
  void stageRectVersion.value;
  const coordinates: [number, number, number, number] | null =
    isDrawingRoi.value && roiStart.value && roiCurrent.value
      ? [
          Math.min(roiStart.value.x, roiCurrent.value.x),
          Math.min(roiStart.value.y, roiCurrent.value.y),
          Math.max(roiStart.value.x, roiCurrent.value.x),
          Math.max(roiStart.value.y, roiCurrent.value.y),
        ]
      : selectedRoi.value;
  if (!coordinates) return null;
  const [x1, y1, x2, y2] = coordinates;

  const stageEl = mediaStageRef.value;
  if (stageEl) {
    const bounds = getMediaContentBounds(stageEl);
    const left = bounds.renderLeft + x1 * bounds.renderWidth;
    const top = bounds.renderTop + y1 * bounds.renderHeight;
    const width = (x2 - x1) * bounds.renderWidth;
    const height = (y2 - y1) * bounds.renderHeight;
    return {
      left: `${left.toFixed(1)}px`,
      top: `${top.toFixed(1)}px`,
      width: `${width.toFixed(1)}px`,
      height: `${height.toFixed(1)}px`,
    };
  }

  return {
    left: `${(x1 * 100).toFixed(2)}%`,
    top: `${(y1 * 100).toFixed(2)}%`,
    width: `${((x2 - x1) * 100).toFixed(2)}%`,
    height: `${((y2 - y1) * 100).toFixed(2)}%`,
  };
});

const isTerminal = computed(
  () =>
    !!run.value &&
    ["completed", "failed", "cancelled"].includes(run.value.status),
);
const progressPercent = computed(() => {
  const rounded = Math.round((run.value?.progress ?? 0) * 100);
  return isTerminal.value ? rounded : Math.min(99, rounded);
});
const warnings = computed(() => result.value?.warnings ?? []);
const informationalWarningCodes = new Set([
  "media_termination:source_ended",
  "media_termination:segment_window_completed",
]);
const isInformationalWarning = (value: string): boolean =>
  informationalWarningCodes.has(value);
const actionableWarnings = computed(() =>
  warnings.value.filter((item) => !isInformationalWarning(item)),
);
const hasActionableWarnings = computed(
  () => actionableWarnings.value.length > 0,
);
const warningPanelTitle = computed(() => {
  if (hasActionableWarnings.value) return "解析警告";
  const hasInformational = warnings.value.some(isInformationalWarning);
  if (hasInformational && hasActionableWarnings.value) return "解析提示与警告";
  return hasInformational ? "解析提示" : "解析警告";
});
const hasResult = computed(() => !!result.value);

const currentDomainLabel = computed(
  () => selectedDomainManifest.value?.display_name || labelDomain(domain.value),
);
const isDomainScoped = computed(() =>
  Boolean(route.params?.domain || props.initialDomain || domain.value),
);
const scopedHistoryRuns = computed(() => historyRuns.value);

function resetResult(): void {
  resetRunTracking();
  run.value = null;
  result.value = null;
  selectedUnitIndex.value = 0;
  followLatestUnit.value = true;
  resetResultPreview();
  progressDetail.value = "";
  error.value = "";
  clearOverlay();
}

function workspacePath(
  nextDomain = domain.value,
  nextMode = mode.value,
): string {
  return `/parse/${encodeURIComponent(nextDomain)}/${nextMode}`;
}

function navigateWorkspace(
  nextDomain = domain.value,
  nextMode = mode.value,
  clearRun = true,
): void {
  const query = { ...route.query };
  delete query.domain;
  delete query.mediaKind;
  if (clearRun) {
    delete query.run;
    delete query.asset;
    delete query.source;
  }
  void router.replace({ path: workspacePath(nextDomain, nextMode), query });
}

function selectMode(value: MediaMode): void {
  if (!supportedMediaKinds.value.includes(value)) return;
  mode.value = value;
  file.value = null;
  assetId.value = "";
  clearRoi();
  clearMediaUrl();
  resetResult();
  if (value === "stream") {
    void refreshSources().then(() => {
      if (sources.value.length && !sourceId.value) {
        sourceId.value = sources.value[0]?.source_id ?? "";
      }
      if (sourceId.value) {
        void loadStreamPreview(sourceId.value);
      }
    });
  }
  navigateWorkspace(domain.value, value);
}

function selectOrigin(value: InputOrigin): void {
  inputOrigin.value = value;
  file.value = null;
  assetId.value = "";
  clearRoi();
  clearMediaUrl();
  resetResult();
}

function selectDomain(value: Domain): void {
  if (domain.value === value) return;
  domain.value = value;
  clearRoi();
  assetId.value = "";
  file.value = null;
  inputOrigin.value = "upload";
  clearMediaUrl();
  pipelineId.value = "";
  domainSearch.value = "";
  resetResult();
  syncPipelineSelection();
  ensureSupportedMode();
  navigateWorkspace(value, mode.value);
  void refreshHistory();
}

function handleVideoLoadedData(): void {
  const video = videoElement.value;
  if (video && video.currentTime === 0) {
    try {
      video.currentTime = 0.001;
    } catch {
      // Seeking may be rejected until enough media data has buffered.
    }
  }
}

async function refreshHistory(): Promise<void> {
  if (!domain.value) return;
  loadingHistory.value = true;
  try {
    const page = await api<RunPage>(
      `/api/v1/runs?domain=${encodeURIComponent(domain.value)}&limit=12`,
    );
    historyRuns.value = Array.isArray(page?.items) ? page.items : [];
  } catch {
    historyRuns.value = [];
  } finally {
    loadingHistory.value = false;
  }
}

async function execute(): Promise<void> {
  if (!inputReady.value || !selectedPipeline.value) return;
  resetResult();
  loading.value = true;
  try {
    let selectedAssetId: string | null = null;
    let selectedSourceId: string | null = null;
    if (mode.value === "stream") {
      selectedSourceId = await ensureSource();
    } else if (inputOrigin.value === "upload") {
      selectedAssetId = (await uploadSelectedAsset()).asset_id;
    } else {
      selectedAssetId = assetId.value;
    }

    const created = await api<Run>("/api/v1/runs", {
      method: "POST",
      headers: {
        "Idempotency-Key": idempotencyKey(`${domain.value}_${mode.value}`),
      },
      body: JSON.stringify({
        domain: domain.value,
        pipeline: {
          pipeline_id: selectedPipeline.value.pipeline_id,
          version: selectedPipeline.value.version,
        },
        asset_id: selectedAssetId,
        source_id: selectedSourceId,
        parameters: runParameters(),
      }),
    });
    run.value = created;
    syncRunToHistory(created);
    await router.replace({
      path: workspacePath(domain.value, mode.value),
      query: {
        ...route.query,
        run: created.run_id,
        domain: undefined,
        mediaKind: undefined,
      },
    });
    void refreshHistory();
    if (created.status === "completed") await loadResult(created.run_id);
    else if (!isTerminal.value) await pollRun(created);
    if (run.value && ["failed", "cancelled"].includes(run.value.status)) {
      error.value = run.value.termination_reason
        ? labelTerminationReason(run.value.termination_reason)
        : run.value.error_code
          ? labelRunError(run.value.error_code)
          : labelRunStatus(run.value.status);
    }
  } catch (caught) {
    error.value = userFacingError(
      caught,
      "解析失败，请检查输入和模型状态后重试",
    );
  } finally {
    loading.value = false;
  }
}

async function loadExistingRun(runId: string): Promise<void> {
  resetResult();
  loading.value = true;
  try {
    const existing = await api<Run>(
      `/api/v1/runs/${encodeURIComponent(runId)}`,
    );
    domain.value = existing.domain;
    syncPipelineSelection(existing.pipeline.pipeline_id);
    pipelineId.value = existing.pipeline.pipeline_id;
    applyRunParameters(existing.parameters);
    if (existing.asset_id) {
      await selectAssetById(existing.asset_id);
    } else if (existing.source_id) {
      mode.value = "stream";
      sourceId.value = existing.source_id;
      await loadStreamPreview(existing.source_id);
    }
    await router.replace({
      path: workspacePath(existing.domain, mode.value),
      query: {
        ...route.query,
        run: existing.run_id,
        domain: undefined,
        mediaKind: undefined,
      },
    });
    run.value = existing;
    await refreshHistory();
    if (existing.status === "completed" || existing.status === "cancelled") {
      await loadResult(existing.run_id, true);
    } else if (existing.status !== "failed") {
      void loadResult(existing.run_id, true).catch(() => undefined);
      followRun(existing);
    }
  } catch (caught) {
    error.value = userFacingError(caught, "运行加载失败，请检查运行标识");
  } finally {
    loading.value = false;
  }
}

async function restoreRouteSelection(): Promise<void> {
  const runId = queryValue(route.query.run);
  if (runId) {
    await loadExistingRun(runId);
    assetId.value = "";
    inputOrigin.value = "upload";
    return;
  }
  const asset = queryValue(route.query.asset);
  if (asset) {
    await selectAssetById(asset);
    navigateWorkspace(domain.value, mode.value, false);
    return;
  }
  const source = queryValue(route.query.source);
  if (source) {
    mode.value = "stream";
    sourceId.value = source;
    await loadStreamPreview(source);
    navigateWorkspace(domain.value, mode.value, false);
  }
}

async function transitionRun(
  action: "pause" | "resume" | "cancel",
): Promise<void> {
  if (
    !run.value ||
    transitioning.value ||
    (action === "cancel" && isTerminal.value)
  )
    return;
  const current = run.value;
  transitioning.value = true;
  try {
    resetRunTracking();
    const updated = await api<Run>(
      "/api/v1/runs/" + encodeURIComponent(current.run_id) + "/" + action,
      { method: "POST" },
    );
    run.value = updated;
    syncRunToHistory(updated);
    if (action === "cancel") {
      await loadResult(current.run_id, true);
      void refreshHistory();
    } else if (!["completed", "failed", "cancelled"].includes(updated.status)) {
      followRun(updated);
    } else {
      void refreshHistory();
    }
  } catch (caught) {
    error.value = userFacingError(caught, "运行状态更新失败，请刷新后重试");
  } finally {
    transitioning.value = false;
  }
}

function formatTime(milliseconds?: number | null): string {
  if (milliseconds == null) return "-";
  const seconds = milliseconds / 1000;
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;
}

function formatRunDate(value: number): string {
  return new Date(value * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const { followRun, loadResult, pollRun, resetRunTracking } = useRunTracker({
  followLatestUnit,
  formatTime,
  loadStreamPreview,
  mode,
  onError: (caught) => {
    error.value = userFacingError(caught, "运行状态跟踪失败，请稍后重试");
  },
  onRefreshHistory: () => {
    void refreshHistory();
  },
  onRunChange: syncRunToHistory,
  prefersResultFramePreview,
  progressDetail,
  result,
  run,
  selectedUnitIndex,
  sourceId,
});

const detailRunId = ref<string | null>(null);
const isDetailOpen = ref(false);

function openHistoryDetail(runItem: Run): void {
  detailRunId.value = runItem.run_id;
  isDetailOpen.value = true;
}

watch(
  () => props.initialDomain,
  (value) => {
    if (value) selectDomain(value);
  },
);
watch(
  () => queryValue(route.query.run),
  (runId) => {
    if (runId && runId !== run.value?.run_id) void loadExistingRun(runId);
  },
);
watch(
  () => [
    queryValue(route.params?.domain) || queryValue(route.query.domain),
    queryValue(route.params?.mediaKind) || queryValue(route.query.mediaKind),
  ],
  ([nextDomain, nextMode]) => {
    const nextDomainValue = typeof nextDomain === "string" ? nextDomain : "";
    const nextModeValue = typeof nextMode === "string" ? nextMode : "";
    const normalizedMode = isMediaMode(nextModeValue)
      ? nextModeValue
      : mode.value;
    const domainChanged = !!nextDomainValue && nextDomainValue !== domain.value;
    const modeChanged = normalizedMode !== mode.value;
    if (!domainChanged && !modeChanged) return;
    if (domainChanged) {
      domain.value = nextDomainValue;
      pipelineId.value = "";
      syncPipelineSelection();
    }
    if (modeChanged) {
      mode.value = normalizedMode;
      if (normalizedMode === "stream") void refreshSources();
    }
    assetId.value = "";
    file.value = null;
    inputOrigin.value = "upload";
    clearRoi();
    clearMediaUrl();
    resetResult();
    void refreshHistory();
  },
);
watch(domain, () => {
  void refreshHistory();
});
watch(pipelineId, () => syncPipelineParameterDefaults());
watch(selectedUnitIndex, syncSelectedMediaFrame);
watch(
  () => [mode.value, sourceId.value],
  ([currentMode, currentSourceId]) => {
    if (currentMode === "stream" && currentSourceId) {
      void loadStreamPreview(currentSourceId);
    }
  },
  { immediate: true },
);
watch(
  () => [
    run.value?.run_id ?? "",
    selectedUnit.value?.unit_id ?? "",
    selectedUnit.value?.frame_artifact_id ?? "",
    mode.value,
    mediaUrl.value,
    videoPlaybackFailed.value,
  ],
  syncSelectedMediaFrame,
);
watch(
  () => [run.value?.run_id, run.value?.status, run.value?.progress],
  ([, newStatus]) => {
    if (run.value) {
      syncRunToHistory(run.value);
      if (
        newStatus &&
        ["completed", "failed", "cancelled"].includes(newStatus as string)
      ) {
        void refreshHistory();
      }
    }
  },
  { deep: true },
);
onMounted(async () => {
  window.addEventListener("resize", onStageResize);
  await refreshWorkspaceResources();
  await restoreRouteSelection();
  await refreshHistory();
});
useRefresh(async () => {
  await Promise.all([refreshWorkspaceResources(), refreshHistory()]);
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", onStageResize);
  disposeRoiSelection();
  resetRunTracking();
  clearMediaUrl();
});
</script>

<template>
  <section class="page parse-workbench">
    <ParseWorkspaceToolbar
      v-model:domain-search="domainSearch"
      v-model:pipeline-id="pipelineId"
      :available-domains="availableDomains"
      :domain="domain"
      :domain-pipelines="domainPipelines"
      :has-result="hasResult"
      :input-ready="inputReady"
      :is-domain-scoped="isDomainScoped"
      :loading="loading"
      :mode="mode"
      :run="run"
      :supported-media-kinds="supportedMediaKinds"
      :transitioning="transitioning"
      @execute="execute"
      @open-result="run && openHistoryDetail(run)"
      @open-runs="router.push({ path: '/runs', query: { domain } })"
      @reset-result="resetResult"
      @select-domain="selectDomain"
      @select-mode="selectMode"
      @transition-run="transitionRun"
    />

    <p v-if="error" class="callout error">{{ error }}</p>

    <section class="panel input-panel">
      <div class="panel-header">
        <h2>输入与采样</h2>
        <span class="badge">{{
          mode === "image"
            ? "单帧"
            : mode === "document"
              ? "全部页面"
              : mode === "stream"
                ? "自动连续分段"
                : "处理至视频结束"
        }}</span>
      </div>
      <div class="panel-body input-layout">
        <ParseMediaPreview
          :displayed-media-url="displayedMediaUrl"
          :file="file"
          :handle-image-error="handleImageError"
          :handle-result-frame-loaded="handleResultFrameLoaded"
          :handle-video-loaded-data="handleVideoLoadedData"
          :handle-video-pause="handleVideoPause"
          :handle-video-playback-error="handleVideoPlaybackError"
          :handle-video-play="handleVideoPlay"
          :handle-video-seeked="handleVideoSeeked"
          :has-result="hasResult"
          :is-drawing-roi="isDrawingRoi"
          :media-url="mediaUrl"
          :mode="mode"
          :on-stage-resize="onStageResize"
          :overlay-ready="overlayReady"
          :overlay-status="overlayStatus"
          :result-frame-url="resultFrameUrl"
          :roi-box-style="roiBoxStyle"
          :selected-asset="selectedAsset"
          :selected-roi="selectedRoi"
          :selected-source="selectedSource"
          :server-preview-url="serverPreviewUrl"
          :set-media-stage="setMediaStage"
          :set-overlay-canvas="setOverlayCanvas"
          :set-video-element="setVideoElement"
          :should-use-result-frame="shouldUseResultFrame"
          :source-name="sourceName"
          :source-url="sourceUrl"
          :stream-preview-url="streamPreviewUrl"
          :sync-video-to-selected-unit="syncVideoToSelectedUnit"
          :video-playing="videoPlaying"
          :video-playback-failed="videoPlaybackFailed"
          @clear-roi="clearRoi"
          @mouse-down="handleRoiMouseDown"
          @toggle-roi="toggleRoiDrawing"
        />

        <ParseInputControls
          v-model:asset-id="assetId"
          v-model:connect-timeout-ms="connectTimeoutMs"
          v-model:frame-max-edge="frameMaxEdge"
          v-model:input-origin="inputOrigin"
          v-model:max-reconnect-attempts="maxReconnectAttempts"
          v-model:page-scale="pageScale"
          v-model:pipeline-parameters="pipelineParameters"
          v-model:read-timeout-ms="readTimeoutMs"
          v-model:sample-end-ms="sampleEndMs"
          v-model:sample-interval-ms="sampleIntervalMs"
          v-model:sample-start-ms="sampleStartMs"
          v-model:sample-strategy="sampleStrategy"
          v-model:scene-change-threshold="sceneChangeThreshold"
          v-model:source-id="sourceId"
          v-model:source-name="sourceName"
          v-model:source-url="sourceUrl"
          :boolean-parameter-entries="booleanParameterEntries"
          :compact-field-entries-count="compactFieldEntriesCount"
          :field-parameter-entries="fieldParameterEntries"
          :file="file"
          :filtered-assets="filteredAssets"
          :format-option-label="formatOptionLabel"
          :has-parameters="parameterEntries.length > 0"
          :is-parameter-wide="isParameterWide"
          :loading-sources="loadingSources"
          :mode="mode"
          :sources="sources"
          :strategy-labels="STRATEGY_LABELS"
          @preview-stream="previewNewStream"
          @refresh-sources="refreshSources"
          @refresh-workspace="refreshWorkspaceResources"
          @select-file="selectFile"
          @select-library-asset="selectLibraryAsset"
          @select-origin="selectOrigin"
          @select-source="loadStreamPreview"
        />
      </div>
    </section>

    <section v-if="run" class="run-strip" aria-live="polite">
      <div>
        <span class="badge" :class="run.status">{{
          labelRunStatus(run.status)
        }}</span
        ><strong class="mono">{{ run.run_id }}</strong>
      </div>
      <div
        class="progress-track"
        role="progressbar"
        :aria-valuenow="progressPercent"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <span :style="{ width: `${progressPercent}%` }" />
      </div>
      <span class="progress-value"
        ><strong>{{ progressPercent }}%</strong
        ><small v-if="progressDetail">{{ progressDetail }}</small></span
      >
    </section>

    <section v-if="actionableWarnings.length" class="panel warning-panel">
      <div class="panel-header">
        <h2><AlertTriangle :size="16" />{{ warningPanelTitle }}</h2>
        <button class="button secondary" @click="showWarnings = !showWarnings">
          {{ showWarnings ? "收起" : `查看 ${actionableWarnings.length} 条` }}
        </button>
      </div>
      <ul v-if="showWarnings" class="panel-body warning-list">
        <li v-for="item in actionableWarnings" :key="item">
          {{ labelWarning(item) }}
        </li>
      </ul>
    </section>

    <ParseHistoryPanel
      :domain="domain"
      :domain-label="currentDomainLabel"
      :format-run-date="formatRunDate"
      :items="scopedHistoryRuns"
      :label-pipeline="labelPipeline"
      :label-run-status="labelRunStatus"
      :loading="loadingHistory"
      @detail="openHistoryDetail"
      @refresh="refreshHistory"
    />

    <ResultDetailDrawer v-model:open="isDetailOpen" :run-id="detailRunId" />
  </section>
</template>

<style src="./parse/parse-workbench.css" scoped></style>
