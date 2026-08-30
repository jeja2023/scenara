<script setup lang="ts">
import {
  AlertTriangle,
  Clock3,
  Crop,
  Eye,
  FileImage,
  FileText,
  Info,
  Library,
  Pause,
  Play,
  Radio,
  RefreshCw,
  Search,
  Square,
  Upload,
  Video,
  X,
} from "@lucide/vue";
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ApiError,
  api,
  apiImageDataUrl,
  apiStream,
  idempotencyKey,
  streamJsonEvents,
  userFacingError,
} from "../api";
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
  MediaUnitResult,
  PipelineParameterDefinition,
  ResultEnvelope,
  ResultPage,
  Run,
  RunPage,
  TableColumn,
  VisionObject,
} from "../types";
import DataTable from "../components/DataTable.vue";
import ResultDetailDrawer from "../components/ResultDetailDrawer.vue";

const historyRunColumns: TableColumn<Run>[] = [
  { key: "run_id", label: "任务 ID", class: "mono truncate" },
  { key: "pipeline", label: "流水线", class: "truncate" },
  { key: "asset_source", label: "资产 / 来源", class: "mono truncate" },
  { key: "status", label: "状态" },
  { key: "created_at", label: "提交时间", class: "muted" },
  { key: "actions", label: "操作", width: "80px" },
];

type InputOrigin = "library" | "upload";
type SampleStrategy = "interval" | "keyframe" | "scene_change" | "uniform";

const STRATEGY_LABELS: Record<SampleStrategy, string> = {
  interval: "固定间隔",
  keyframe: "关键帧",
  scene_change: "场景切换",
  uniform: "均匀分布",
};

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
const videoElement = ref<HTMLVideoElement | null>(null);
const overlayCanvas = ref<HTMLCanvasElement | null>(null);
const resultFrameUrl = ref("");
const resultFrameUnitId = ref("");
const resultFrameLoading = ref(false);
const resultFrameUnavailable = ref(false);
const videoFrameUnitId = ref("");
const videoPlaying = ref(false);
const sources = ref<MediaSource[]>([]);
const sourceId = ref("");
const sourceName = ref("");
const sourceUrl = ref("");

// 抽样参数
const sampleIntervalMs = ref(1000);
const sampleStrategy = ref<SampleStrategy>("interval");
const sampleStartMs = ref(0);
const sampleEndMs = ref<number | null>(null);
const sceneChangeThreshold = ref(0.35);
const frameMaxEdge = ref<number | null>(null);
const pageScale = ref(1.5);
const maxReconnectAttempts = ref(3);
const connectTimeoutMs = ref(10_000);
const readTimeoutMs = ref(10_000);

// 识别区域 (ROI) 圈选
const mediaStageRef = ref<HTMLElement | null>(null);
const stageRectVersion = ref(0);
const isDrawingRoi = ref(false);
const roiStart = ref<{ x: number; y: number } | null>(null);
const roiCurrent = ref<{ x: number; y: number } | null>(null);
const selectedRoi = ref<[number, number, number, number] | null>(null);

function onStageResize(): void {
  stageRectVersion.value += 1;
}

function toggleRoiDrawing(): void {
  isDrawingRoi.value = !isDrawingRoi.value;
  if (isDrawingRoi.value) {
    roiStart.value = null;
    roiCurrent.value = null;
  }
}

function clearRoi(): void {
  selectedRoi.value = null;
  isDrawingRoi.value = false;
  roiStart.value = null;
  roiCurrent.value = null;
  if (pipelineParameters.value.roi) {
    delete pipelineParameters.value.roi;
  }
}

interface MediaBounds {
  renderLeft: number;
  renderTop: number;
  renderWidth: number;
  renderHeight: number;
}

function getMediaContentBounds(stageEl: HTMLElement): MediaBounds {
  const stage = stageEl.getBoundingClientRect();
  const img = stageEl.querySelector("img") as HTMLImageElement | null;
  const video = stageEl.querySelector("video") as HTMLVideoElement | null;
  let naturalW = 0;
  let naturalH = 0;
  if (img && img.naturalWidth > 0 && img.naturalHeight > 0) {
    naturalW = img.naturalWidth;
    naturalH = img.naturalHeight;
  } else if (video && video.videoWidth > 0 && video.videoHeight > 0) {
    naturalW = video.videoWidth;
    naturalH = video.videoHeight;
  } else if (selectedUnit.value?.width && selectedUnit.value?.height) {
    naturalW = selectedUnit.value.width;
    naturalH = selectedUnit.value.height;
  }

  if (!naturalW || !naturalH || stage.width <= 0 || stage.height <= 0) {
    return {
      renderLeft: 0,
      renderTop: 0,
      renderWidth: stage.width || 1,
      renderHeight: stage.height || 1,
    };
  }

  const stageRatio = stage.width / stage.height;
  const naturalRatio = naturalW / naturalH;
  let renderWidth: number;
  let renderHeight: number;
  let renderLeft: number;
  let renderTop: number;

  if (naturalRatio > stageRatio) {
    renderWidth = stage.width;
    renderHeight = stage.width / naturalRatio;
    renderLeft = 0;
    renderTop = (stage.height - renderHeight) / 2;
  } else {
    renderHeight = stage.height;
    renderWidth = stage.height * naturalRatio;
    renderLeft = (stage.width - renderWidth) / 2;
    renderTop = 0;
  }

  return { renderLeft, renderTop, renderWidth, renderHeight };
}

function handleRoiMouseDown(e: MouseEvent): void {
  if (!isDrawingRoi.value || e.button !== 0) return;
  e.preventDefault();
  e.stopPropagation();
  const stageEl = mediaStageRef.value;
  if (!stageEl) return;
  const stage = stageEl.getBoundingClientRect();
  const bounds = getMediaContentBounds(stageEl);
  const clientXRel = e.clientX - stage.left;
  const clientYRel = e.clientY - stage.top;
  const x = Math.max(0, Math.min(1, (clientXRel - bounds.renderLeft) / bounds.renderWidth));
  const y = Math.max(0, Math.min(1, (clientYRel - bounds.renderTop) / bounds.renderHeight));
  roiStart.value = { x, y };
  roiCurrent.value = { x, y };

  window.addEventListener("mousemove", handleRoiMouseMove);
  window.addEventListener("mouseup", handleRoiMouseUp);
}

function handleRoiMouseMove(e: MouseEvent): void {
  if (!isDrawingRoi.value || !roiStart.value) return;
  e.preventDefault();
  const stageEl = mediaStageRef.value;
  if (!stageEl) return;
  const stage = stageEl.getBoundingClientRect();
  const bounds = getMediaContentBounds(stageEl);
  const clientXRel = e.clientX - stage.left;
  const clientYRel = e.clientY - stage.top;
  const x = Math.max(0, Math.min(1, (clientXRel - bounds.renderLeft) / bounds.renderWidth));
  const y = Math.max(0, Math.min(1, (clientYRel - bounds.renderTop) / bounds.renderHeight));
  roiCurrent.value = { x, y };
}

function handleRoiMouseUp(e?: MouseEvent): void {
  window.removeEventListener("mousemove", handleRoiMouseMove);
  window.removeEventListener("mouseup", handleRoiMouseUp);
  if (!isDrawingRoi.value || !roiStart.value) return;

  if (e && mediaStageRef.value) {
    const stage = mediaStageRef.value.getBoundingClientRect();
    const bounds = getMediaContentBounds(mediaStageRef.value);
    const clientXRel = e.clientX - stage.left;
    const clientYRel = e.clientY - stage.top;
    const x = Math.max(0, Math.min(1, (clientXRel - bounds.renderLeft) / bounds.renderWidth));
    const y = Math.max(0, Math.min(1, (clientYRel - bounds.renderTop) / bounds.renderHeight));
    roiCurrent.value = { x, y };
  }

  const current = roiCurrent.value || roiStart.value;
  const minX = Math.max(0, Math.min(roiStart.value.x, current.x));
  const maxX = Math.min(1, Math.max(roiStart.value.x, current.x));
  const minY = Math.max(0, Math.min(roiStart.value.y, current.y));
  const maxY = Math.min(1, Math.max(roiStart.value.y, current.y));

  if (maxX - minX > 0.005 && maxY - minY > 0.005) {
    selectedRoi.value = [
      Math.round(minX * 1000) / 1000,
      Math.round(minY * 1000) / 1000,
      Math.round(maxX * 1000) / 1000,
      Math.round(maxY * 1000) / 1000,
    ];
    pipelineParameters.value.roi = `[${selectedRoi.value.join(", ")}]`;
  }
  isDrawingRoi.value = false;
  roiStart.value = null;
  roiCurrent.value = null;
}

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
let pollGeneration = 0;
let resultLoadSequence = 0;
let sseAbort: AbortController | null = null;
let resultFrameLoadSequence = 0;
const resultFrameCache = new Map<string, string>();
const POLL_NETWORK_RETRY_DELAYS_MS = [250, 500, 1000, 2000] as const;
const RESULT_FRAME_CACHE_LIMIT = 8;

const {
  domainPipelines,
  availableDomains,
  filteredDomains,
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

function optionalNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

const samplingValid = computed(() => {
  const endMs = optionalNumber(sampleEndMs.value);
  const maxEdge = optionalNumber(frameMaxEdge.value);
  if (mode.value === "document")
    return pageScale.value >= 0.5 && pageScale.value <= 4;
  if (
    !Number.isInteger(sampleIntervalMs.value) ||
    sampleIntervalMs.value < 1 ||
    sampleIntervalMs.value > 3_600_000
  )
    return false;
  if (!Number.isInteger(sampleStartMs.value) || sampleStartMs.value < 0)
    return false;
  if (
    endMs != null &&
    (!Number.isInteger(endMs) || endMs <= sampleStartMs.value)
  )
    return false;
  if (mode.value === "stream" && endMs != null && endMs < 1_000) return false;
  if (
    sampleStrategy.value === "scene_change" &&
    (sceneChangeThreshold.value < 0.01 || sceneChangeThreshold.value > 1)
  )
    return false;
  if (
    maxEdge != null &&
    (!Number.isInteger(maxEdge) || maxEdge < 64 || maxEdge > 8_192)
  )
    return false;
  if (mode.value !== "stream") return true;
  return (
    Number.isInteger(maxReconnectAttempts.value) &&
    maxReconnectAttempts.value >= 0 &&
    maxReconnectAttempts.value <= 20 &&
    Number.isInteger(connectTimeoutMs.value) &&
    connectTimeoutMs.value >= 100 &&
    connectTimeoutMs.value <= 120_000 &&
    Number.isInteger(readTimeoutMs.value) &&
    readTimeoutMs.value >= 100 &&
    readTimeoutMs.value <= 120_000
  );
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

const selectedUnit = computed(
  () => result.value?.units[selectedUnitIndex.value] ?? result.value?.units[0],
);
const selectedObjects = computed(() => selectedUnit.value?.objects ?? []);

const roiBoxStyle = computed(() => {
  void stageRectVersion.value;
  let x1 = 0;
  let y1 = 0;
  let x2 = 0;
  let y2 = 0;
  if (isDrawingRoi.value && roiStart.value && roiCurrent.value) {
    x1 = Math.min(roiStart.value.x, roiCurrent.value.x);
    x2 = Math.max(roiStart.value.x, roiCurrent.value.x);
    y1 = Math.min(roiStart.value.y, roiCurrent.value.y);
    y2 = Math.max(roiStart.value.y, roiCurrent.value.y);
  } else if (selectedRoi.value) {
    [x1, y1, x2, y2] = selectedRoi.value;
  } else {
    return null;
  }

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

const booleanParameterEntries = computed(() =>
  parameterEntries.value.filter(([, def]) => def.control === "boolean"),
);

const fieldParameterEntries = computed(() =>
  parameterEntries.value.filter(([, def]) => def.control !== "boolean"),
);

function isParameterWide(
  key: string,
  definition: PipelineParameterDefinition,
): boolean {
  if (["custom_sensitive_words", "compliance_whitelist", "roi"].includes(key)) {
    return true;
  }
  if (
    key === "language_hint" ||
    key === "min_score" ||
    key === "max_pages"
  ) {
    return false;
  }
  if (definition.control === "text") {
    return Boolean(
      definition.placeholder?.includes("，") ||
        definition.placeholder?.includes(",") ||
        definition.placeholder?.includes("换行"),
    );
  }
  return false;
}

const compactFieldEntriesCount = computed(
  () =>
    fieldParameterEntries.value.filter(
      ([key, def]) => !isParameterWide(key, def),
    ).length,
);

const LANGUAGE_LABELS: Record<string, string> = {
  zh: "中文 / 中英 (zh)",
  en: "英文 (en)",
  ja: "日文 (ja)",
  ko: "韩文 (ko)",
  chinese_cht: "繁体中文 (cht)",
  fr: "法语 (fr)",
  de: "德语 (de)",
  ru: "俄语 (ru)",
  es: "西班牙语 (es)",
};

function formatOptionLabel(key: string, option: string): string {
  if (key === "language_hint") {
    return LANGUAGE_LABELS[option] ?? option;
  }
  if (key === "sample_strategy") {
    return STRATEGY_LABELS[option as SampleStrategy] ?? option;
  }
  return option;
}


const currentDomainLabel = computed(
  () => selectedDomainManifest.value?.display_name || labelDomain(domain.value),
);
const isDomainScoped = computed(() =>
  Boolean(route.params?.domain || props.initialDomain || domain.value),
);
const scopedHistoryRuns = computed(() => historyRuns.value);

const displayedMediaUrl = computed(
  () => serverPreviewUrl.value || mediaUrl.value,
);
const prefersResultFramePreview = computed(
  () =>
    mode.value === "document" ||
    mode.value === "stream" ||
    (mode.value === "video" && (!mediaUrl.value || videoPlaybackFailed.value)),
);
const shouldUseResultFrame = computed(() => {
  const unit = selectedUnit.value;
  const runId = run.value?.run_id;
  if (!unit || !runId) return false;
  return prefersResultFramePreview.value;
});
const overlayReady = computed(() => {
  const unit = selectedUnit.value;
  if (!unit || !selectedObjects.value.length) return false;
  if (mode.value === "image") return true;
  if (shouldUseResultFrame.value)
    return resultFrameUnitId.value === unit.unit_id && !!resultFrameUrl.value;
  return videoFrameUnitId.value === unit.unit_id;
});
const overlayStatus = computed(() => {
  if (!selectedObjects.value.length || overlayReady.value) return "";
  if (videoPlaying.value) return "";
  if (resultFrameLoading.value) return "正在同步结果帧";
  if (resultFrameUnavailable.value && shouldUseResultFrame.value)
    return "结果帧暂不可用，已暂停叠加标注";
  if (mode.value === "video") return "正在定位结果帧";
  return "正在加载结果帧";
});

function resetResult(): void {
  pollGeneration += 1;
  if (sseAbort) {
    sseAbort.abort();
    sseAbort = null;
  }
  run.value = null;
  result.value = null;
  selectedUnitIndex.value = 0;
  followLatestUnit.value = true;
  resultFrameLoadSequence += 1;
  resultFrameUrl.value = "";
  resultFrameUnitId.value = "";
  resultFrameLoading.value = false;
  resultFrameUnavailable.value = false;
  videoFrameUnitId.value = "";
  videoPlaying.value = false;
  resultFrameCache.clear();
  progressDetail.value = "";
  resultLoadSequence += 1;
  error.value = "";
  clearOverlay();
}

function clearOverlay(): void {
  const canvas = overlayCanvas.value;
  if (canvas) {
    const ctx = canvas.getContext("2d");
    if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
  }
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

function extractLocalVideoFrame(selectedFile: File): void {
  const tempVideo = document.createElement("video");
  tempVideo.preload = "auto";
  tempVideo.src = URL.createObjectURL(selectedFile);
  tempVideo.muted = true;
  tempVideo.playsInline = true;
  tempVideo.currentTime = 0.001;
  tempVideo.onloadeddata = () => {
    try {
      tempVideo.currentTime = 0.001;
    } catch {}
  };
  tempVideo.onseeked = () => {
    try {
      const canvas = document.createElement("canvas");
      canvas.width = tempVideo.videoWidth || 640;
      canvas.height = tempVideo.videoHeight || 360;
      const ctx = canvas.getContext("2d");
      if (ctx) {
        ctx.drawImage(tempVideo, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL("image/jpeg");
        if (dataUrl && !serverPreviewUrl.value) {
          serverPreviewUrl.value = dataUrl;
        }
      }
    } catch {}
    URL.revokeObjectURL(tempVideo.src);
  };
  tempVideo.onerror = () => {
    URL.revokeObjectURL(tempVideo.src);
  };
}

let preloadSequence = 0;
async function autoPreloadAsset(selectedFile: File): Promise<void> {
  const seq = ++preloadSequence;
  try {
    const form = new FormData();
    form.append("file", selectedFile);
    form.append("kind", mode.value);
    if (domain.value) form.append("domain", domain.value);
    const asset = await api<MediaAsset>("/api/v1/media/assets", {
      method: "POST",
      body: form,
    });
    if (seq !== preloadSequence || file.value !== selectedFile) return;
    assets.value = [
      asset,
      ...assets.value.filter((item) => item.asset_id !== asset.asset_id),
    ];
    await loadServerPreview(asset.asset_id);
  } catch {
    // 尽力而为预加载首帧，不阻断前端交互
  }
}

function selectFile(event: Event): void {
  const selected = (event.target as HTMLInputElement).files?.[0] ?? null;
  inputOrigin.value = "upload";
  assetId.value = "";
  file.value = selected;
  clearMediaUrl();
  resetResult();
  if (!selected) return;
  mediaUrl.value = URL.createObjectURL(selected);

  // 本地视频与文档添加后立即生成首帧预览，保障在解析前即可在底图上精准标注 ROI
  if (mode.value === "video") {
    extractLocalVideoFrame(selected);
    void autoPreloadAsset(selected);
  } else if (mode.value === "document") {
    void autoPreloadAsset(selected);
  }
}

async function previewNewStream(): Promise<void> {
  if (!sourceUrl.value) return;
  try {
    const id = await ensureSource();
    await loadStreamPreview(id);
  } catch (caught) {
    error.value = userFacingError(
      caught,
      "获取视频流首帧预览失败，请检查流地址与网络连通性",
    );
  }
}

function handleVideoLoadedData(): void {
  const video = videoElement.value;
  if (video && video.currentTime === 0) {
    try {
      video.currentTime = 0.001;
    } catch {}
  }
}

function selectLibraryAsset(): void {
  file.value = null;
  clearMediaUrl();
  resetResult();
  if (assetId.value) void loadServerPreview(assetId.value);
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

async function ensureSource(): Promise<string> {
  if (sourceId.value) return sourceId.value;
  const source = await api<MediaSource>("/api/v1/media/sources", {
    method: "POST",
    body: JSON.stringify({ name: sourceName.value, url: sourceUrl.value }),
  });
  sources.value = [source, ...sources.value];
  sourceId.value = source.source_id;
  return source.source_id;
}

async function loadResult(runId: string, ignoreMissing = false): Promise<void> {
  const loadSequence = ++resultLoadSequence;
  const pageSize = 1000;
  let first: ResultPage;
  try {
    first = await api<ResultPage>(
      `/api/v1/runs/${encodeURIComponent(runId)}/result?unit_limit=${pageSize}`,
    );
  } catch (caught) {
    if (ignoreMissing && caught instanceof ApiError && caught.status === 404)
      return;
    throw caught;
  }
  if (!first?.result) return;
  const existingUnits =
    result.value?.run_id === runId ? result.value.units : [];
  let units =
    existingUnits.length > 0 && existingUnits.length <= first.unit_total
      ? [...existingUnits, ...first.result.units.slice(existingUnits.length)]
      : [...first.result.units];
  while (units.length < first.unit_total) {
    const page = await api<ResultPage>(
      `/api/v1/runs/${encodeURIComponent(runId)}/result?unit_offset=${units.length}&unit_limit=${pageSize}`,
    );
    if (!page?.result?.units?.length) break;
    units.push(...page.result.units);
  }
  if (loadSequence !== resultLoadSequence) return;
  if (units.length > first.unit_total) units = units.slice(0, first.unit_total);
  const shouldFollowLatest = followLatestUnit.value || !result.value;
  result.value = { ...first.result, units };
  if (shouldFollowLatest && units.length) {
    selectedUnitIndex.value = preferredPreviewUnitIndex(units);
  } else if (selectedUnitIndex.value >= units.length) {
    selectedUnitIndex.value = Math.max(0, units.length - 1);
  }
  if (mode.value === "stream" && sourceId.value)
    void loadStreamPreview(sourceId.value);
  drawOverlay();
}

interface EventSubscription {
  connected: Promise<boolean>;
  completed: Promise<boolean>;
}

function subscribeEvents(runId: string): EventSubscription {
  if (sseAbort) sseAbort.abort();
  const controller = new AbortController();
  sseAbort = controller;
  let resolveConnected!: (value: boolean) => void;
  let resolveCompleted!: (value: boolean) => void;
  const connected = new Promise<boolean>((resolve) => {
    resolveConnected = resolve;
  });
  const completed = new Promise<boolean>((resolve) => {
    resolveCompleted = resolve;
  });
  void (async () => {
    try {
      const response = await apiStream(
        `/api/v1/runs/${encodeURIComponent(runId)}/events`,
        controller.signal,
      );
      resolveConnected(true);
      for await (const event of streamJsonEvents<{
        event_type?: string;
        status?: Run["status"];
        payload?: {
          progress?: number | null;
          processed_units?: number;
          expected_units?: number | null;
          unit_count?: number;
          unit_total?: number;
          latest_pts_ms?: number | null;
          next_run_id?: string;
        };
      }>(response)) {
        if (
          run.value &&
          event.status &&
          ["completed", "failed", "cancelled"].includes(event.status)
        ) {
          run.value = await api<Run>(
            "/api/v1/runs/" + encodeURIComponent(runId),
          );
          syncRunToHistory(run.value);
          void refreshHistory();
        } else if (run.value && !isTerminal.value) {
          run.value = {
            ...run.value,
            status: event.status ?? run.value.status,
            progress: event.payload?.progress ?? run.value.progress,
          };
          syncRunToHistory(run.value);
        }
        if (event.payload?.processed_units != null) {
          progressDetail.value =
            event.payload.expected_units == null
              ? `已处理 ${event.payload.processed_units} 个采样单元${event.payload.latest_pts_ms == null ? "" : ` · ${formatTime(event.payload.latest_pts_ms)}`}`
              : `${event.payload.processed_units} / ${event.payload.expected_units} 个采样单元`;
        }
        const availableUnitCount =
          event.event_type === "result.delta"
            ? event.payload?.unit_total
            : event.payload?.unit_count;
        if (
          ["result.partial", "result.delta"].includes(event.event_type ?? "") &&
          (availableUnitCount ?? 0) > (result.value?.units.length ?? 0)
        ) {
          void loadResult(runId, true).catch(() => undefined);
        }
      }
      resolveCompleted(true);
    } catch {
      resolveConnected(false);
      resolveCompleted(false);
      // 事件流断开时回退到轮询，不向用户报错
    }
  })();
  return { connected, completed };
}

function followRun(initial: Run): void {
  void pollRun(initial).catch((caught) => {
    error.value = userFacingError(caught, "运行状态跟踪失败，请稍后重试");
  });
}

async function getRunWithNetworkRetry(
  runId: string,
  generation: number,
): Promise<Run | null> {
  for (let attempt = 0; ; attempt += 1) {
    if (generation !== pollGeneration) return null;
    try {
      return await api<Run>("/api/v1/runs/" + encodeURIComponent(runId));
    } catch (caught) {
      if (generation !== pollGeneration) return null;
      const retryDelay = POLL_NETWORK_RETRY_DELAYS_MS[attempt];
      if (
        !(caught instanceof ApiError) ||
        caught.code !== "NETWORK_ERROR" ||
        retryDelay === undefined
      ) {
        throw caught;
      }
      await new Promise((resolve) => window.setTimeout(resolve, retryDelay));
    }
  }
}

async function pollRun(initial: Run): Promise<void> {
  const generation = ++pollGeneration;
  run.value = initial;
  syncRunToHistory(initial);
  const subscription = subscribeEvents(initial.run_id);
  if (await subscription.connected) {
    await subscription.completed;
  }
  if (generation !== pollGeneration) return;
  while (
    generation === pollGeneration &&
    !["completed", "failed", "cancelled"].includes(run.value.status)
  ) {
    await new Promise((resolve) => window.setTimeout(resolve, 500));
    if (generation !== pollGeneration) return;
    const refreshed = await getRunWithNetworkRetry(initial.run_id, generation);
    if (!refreshed) return;
    const progressChanged = refreshed.progress > run.value.progress;
    run.value = refreshed;
    syncRunToHistory(refreshed);
    if (progressChanged && !isTerminal.value) {
      void loadResult(initial.run_id, true).catch(() => undefined);
    }
  }
  if (sseAbort) {
    sseAbort.abort();
    sseAbort = null;
  }
  if (generation !== pollGeneration) return;
  syncRunToHistory(run.value);
  void refreshHistory();
  if (run.value.status === "completed" || run.value.status === "cancelled") {
    await loadResult(initial.run_id, true);
  }
  if (mode.value === "stream" && run.value.next_run_id) {
    const next = await api<Run>(
      "/api/v1/runs/" + encodeURIComponent(run.value.next_run_id),
    );
    followRun(next);
  }
}

function samplingParameters(): Record<string, unknown> {
  const endMs = optionalNumber(sampleEndMs.value);
  const maxEdge = optionalNumber(frameMaxEdge.value);
  const params: Record<string, unknown> = {
    sample_interval_ms: sampleIntervalMs.value,
    sample_strategy: sampleStrategy.value,
    sample_start_ms: sampleStartMs.value,
    scene_change_threshold: sceneChangeThreshold.value,
  };
  if (mode.value !== "stream" && endMs != null && endMs > sampleStartMs.value)
    params.sample_end_ms = endMs;
  if (maxEdge != null) params.frame_max_edge = maxEdge;
  if (mode.value === "stream") {
    if (endMs != null) params.stream_segment_duration_ms = endMs;
    params.max_reconnect_attempts = maxReconnectAttempts.value;
    params.connect_timeout_ms = connectTimeoutMs.value;
    params.read_timeout_ms = readTimeoutMs.value;
  }
  return params;
}

async function uploadSelectedAsset(): Promise<MediaAsset> {
  const form = new FormData();
  form.append("file", file.value as File);
  form.append("kind", mode.value);
  if (domain.value) form.append("domain", domain.value);
  const asset = await api<MediaAsset>("/api/v1/media/assets", {
    method: "POST",
    body: form,
  });
  assets.value = [
    asset,
    ...assets.value.filter((item) => item.asset_id !== asset.asset_id),
  ];
  void loadServerPreview(asset.asset_id);
  return asset;
}

function runParameters(): Record<string, unknown> {
  const params =
    mode.value === "image"
      ? {}
      : mode.value === "document"
        ? {
            page_scale: pageScale.value,
          }
        : samplingParameters();
  for (const [key, value] of Object.entries(pipelineParameters.value)) {
    if (key === "max_units") continue;
    if (
      value !== undefined &&
      value !== null &&
      value !== "" &&
      JSON.stringify(value) !==
        JSON.stringify(pipelineParameterDefaults.value[key])
    )
      params[key] = value;
  }
  if (selectedRoi.value) {
    params.roi = selectedRoi.value;
  }
  return params;
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

function applyRunParameters(parameters: Record<string, unknown>): void {
  if (parameters.sample_interval_ms != null)
    sampleIntervalMs.value = Number(parameters.sample_interval_ms);
  if (parameters.sample_strategy != null)
    sampleStrategy.value = String(parameters.sample_strategy) as SampleStrategy;
  if (parameters.sample_start_ms != null)
    sampleStartMs.value = Number(parameters.sample_start_ms);
  if (parameters.sample_end_ms != null)
    sampleEndMs.value = Number(parameters.sample_end_ms);
  if (parameters.stream_segment_duration_ms != null)
    sampleEndMs.value = Number(parameters.stream_segment_duration_ms);
  if (parameters.scene_change_threshold != null)
    sceneChangeThreshold.value = Number(parameters.scene_change_threshold);
  if (parameters.frame_max_edge != null)
    frameMaxEdge.value = Number(parameters.frame_max_edge);
  if (parameters.page_scale != null)
    pageScale.value = Number(parameters.page_scale);
  if (parameters.max_reconnect_attempts != null)
    maxReconnectAttempts.value = Number(parameters.max_reconnect_attempts);
  if (parameters.connect_timeout_ms != null)
    connectTimeoutMs.value = Number(parameters.connect_timeout_ms);
  if (parameters.roi) {
    if (Array.isArray(parameters.roi) && parameters.roi.length === 4) {
      selectedRoi.value = [
        Number(parameters.roi[0]),
        Number(parameters.roi[1]),
        Number(parameters.roi[2]),
        Number(parameters.roi[3]),
      ];
    } else if (typeof parameters.roi === "string") {
      const matches = parameters.roi.match(/[-+]?(?:\d*\.\d+|\d+)/g);
      if (matches && matches.length === 4) {
        selectedRoi.value = [
          Number(matches[0]),
          Number(matches[1]),
          Number(matches[2]),
          Number(matches[3]),
        ];
      }
    }
  }
  const schema = selectedPipeline.value?.parameter_schema ?? {};
  for (const key of Object.keys(schema)) {
    if (parameters[key] !== undefined)
      pipelineParameters.value[key] = parameters[key];
  }
}

async function ensureAssetLoaded(id: string): Promise<MediaAsset> {
  const existing = assets.value.find((item) => item.asset_id === id);
  if (existing) return existing;
  const asset = await api<MediaAsset>(
    `/api/v1/media/assets/${encodeURIComponent(id)}`,
  );
  assets.value = [asset, ...assets.value];
  return asset;
}

async function selectAssetById(id: string): Promise<void> {
  const asset = await ensureAssetLoaded(id);
  if (asset.kind === "stream") return;
  mode.value = asset.kind;
  inputOrigin.value = "library";
  assetId.value = asset.asset_id;
  file.value = null;
  await loadServerPreview(asset.asset_id);
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
    pollGeneration += 1;
    if (sseAbort) {
      sseAbort.abort();
      sseAbort = null;
    }
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

const FRAME_ALIGNMENT_TOLERANCE_SECONDS = 0.15;

function cacheResultFrame(key: string, value: string): void {
  resultFrameCache.delete(key);
  resultFrameCache.set(key, value);
  while (resultFrameCache.size > RESULT_FRAME_CACHE_LIMIT) {
    const oldest = resultFrameCache.keys().next().value;
    if (oldest === undefined) break;
    resultFrameCache.delete(oldest);
  }
}

function resultFramePath(runId: string, artifactId: string): string {
  return `/api/v1/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}`;
}

function preferredPreviewUnitIndex(units: MediaUnitResult[]): number {
  if (!prefersResultFramePreview.value) return Math.max(0, units.length - 1);
  for (let index = units.length - 1; index >= 0; index -= 1) {
    if (units[index]?.frame_artifact_id) return index;
  }
  return Math.max(0, units.length - 1);
}

function syncVideoToSelectedUnit(): void {
  videoFrameUnitId.value = "";
  clearOverlay();
  const video = videoElement.value;
  const unit = selectedUnit.value;
  if (
    shouldUseResultFrame.value ||
    mode.value !== "video" ||
    !mediaUrl.value ||
    videoPlaybackFailed.value ||
    !video ||
    unit?.pts_ms == null
  )
    return;
  if (videoPlaying.value) return;
  if (video.readyState < HTMLMediaElement.HAVE_METADATA) return;
  const targetSeconds = unit.pts_ms / 1000;
  try {
    if (!video.paused) video.pause();
    if (
      Math.abs(video.currentTime - targetSeconds) <=
      FRAME_ALIGNMENT_TOLERANCE_SECONDS
    ) {
      videoFrameUnitId.value = unit.unit_id;
      drawOverlay();
      return;
    }
    video.currentTime = targetSeconds;
  } catch {
    // Browsers may reject seeking until metadata is available; the event handler retries.
  }
}

function handleVideoSeeked(): void {
  const video = videoElement.value;
  const unit = selectedUnit.value;
  if (!video || !unit || unit.pts_ms == null) return;
  if (
    Math.abs(video.currentTime - unit.pts_ms / 1000) <=
    FRAME_ALIGNMENT_TOLERANCE_SECONDS
  ) {
    videoFrameUnitId.value = unit.unit_id;
    drawOverlay();
  } else {
    syncVideoToSelectedUnit();
  }
}

function handleVideoPlay(): void {
  videoPlaying.value = true;
  videoFrameUnitId.value = "";
  clearOverlay();
}

function handleVideoPlaybackError(): void {
  handleVideoError();
  const units = result.value?.units ?? [];
  if (!units.length) return;
  const previewIndex = preferredPreviewUnitIndex(units);
  if (previewIndex !== selectedUnitIndex.value) {
    selectedUnitIndex.value = previewIndex;
    followLatestUnit.value = true;
    return;
  }
  void loadSelectedResultFrame();
}

function handleVideoPause(): void {
  videoPlaying.value = false;
  syncVideoToSelectedUnit();
}

function handleResultFrameLoaded(): void {
  if (
    resultFrameUrl.value &&
    resultFrameUnitId.value === selectedUnit.value?.unit_id
  )
    drawOverlay();
}

async function loadSelectedResultFrame(): Promise<void> {
  const sequence = ++resultFrameLoadSequence;
  const unit = selectedUnit.value;
  const runId = run.value?.run_id;
  resultFrameUrl.value = "";
  resultFrameUnitId.value = "";
  resultFrameUnavailable.value = false;
  resultFrameLoading.value = false;
  videoFrameUnitId.value = "";
  clearOverlay();

  if (!shouldUseResultFrame.value || !unit || !runId) {
    syncVideoToSelectedUnit();
    await nextTick();
    drawOverlay();
    return;
  }
  const artifactId = unit.frame_artifact_id;
  if (!artifactId) {
    resultFrameUnavailable.value = true;
    return;
  }
  const cacheKey = `${runId}:${artifactId}`;
  const cached = resultFrameCache.get(cacheKey);
  if (cached) {
    resultFrameUrl.value = cached;
    resultFrameUnitId.value = unit.unit_id;
    await nextTick();
    handleResultFrameLoaded();
    return;
  }
  resultFrameLoading.value = true;
  try {
    const dataUrl = await apiImageDataUrl(resultFramePath(runId, artifactId));
    if (sequence !== resultFrameLoadSequence) return;
    cacheResultFrame(cacheKey, dataUrl);
    resultFrameUrl.value = dataUrl;
    resultFrameUnitId.value = unit.unit_id;
    await nextTick();
    handleResultFrameLoaded();
  } catch {
    if (sequence === resultFrameLoadSequence)
      resultFrameUnavailable.value = true;
  } finally {
    if (sequence === resultFrameLoadSequence) resultFrameLoading.value = false;
  }
}

function syncSelectedMediaFrame(): void {
  void loadSelectedResultFrame();
}

const OVERLAY_COLORS: Record<string, string> = {
  person: "#ef6c52",
  face: "#2f9e7e",
  silhouette: "#c98a17",
  text: "#2f9e7e",
  title: "#ef6c52",
  paragraph: "#4b7bd4",
  image: "#8a63c9",
  image_region: "#8a63c9",
  table: "#c98a17",
  table_region: "#c98a17",
  action: "#0284c7",
  behavior: "#0284c7",
  clothing: "#db2777",
  cosplay: "#7c3aed",
  accessory: "#d97706",
};

function formatOverlayBadge(item: VisionObject): string {
  const scoreStr = item.score != null ? ` ${item.score.toFixed(2)}` : "";
  const attrs = item.attributes as Record<string, unknown> | undefined;
  if (attrs?.action_label) return `${attrs.action_label}${scoreStr}`;
  if (attrs?.character_name && attrs?.style_label) return `${attrs.character_name} · ${attrs.style_label}${scoreStr}`;
  if (attrs?.style_label) return `${attrs.style_label}${scoreStr}`;
  if (attrs?.character_name) return `${attrs.character_name}${scoreStr}`;
  if (attrs?.accessory_label) return `${attrs.accessory_label}${scoreStr}`;
  if (attrs?.text) {
    const txt = String(attrs.text).trim();
    return `${txt.slice(0, 10)}${txt.length > 10 ? "…" : ""}${scoreStr}`;
  }
  if (item.object_type !== "person") return `${item.object_type}${scoreStr}`;
  return scoreStr ? scoreStr.trim() : "目标";
}

function drawOverlay(): void {
  const canvas = overlayCanvas.value;
  const unit = selectedUnit.value;
  if (!canvas || !unit || !overlayReady.value) {
    clearOverlay();
    return;
  }
  canvas.width = unit.width;
  canvas.height = unit.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const stroke = Math.max(1.5, Math.min(unit.width, unit.height) / 320);
  ctx.lineWidth = stroke;
  ctx.font = `${Math.max(11, Math.min(unit.width, unit.height) / 42)}px system-ui, sans-serif`;
  ctx.textBaseline = "bottom";
  for (const item of unit.objects) {
    const color = OVERLAY_COLORS[item.object_type] ?? "#4b7bd4";
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    if (item.polygon?.length && item.polygon.length >= 3) {
      ctx.beginPath();
      item.polygon.forEach((point, index) => {
        if (index === 0) ctx.moveTo(point.x, point.y);
        else ctx.lineTo(point.x, point.y);
      });
      ctx.closePath();
      ctx.stroke();
    }
    if (item.bbox) {
      ctx.strokeRect(
        item.bbox.x,
        item.bbox.y,
        item.bbox.width,
        item.bbox.height,
      );
      const text = formatOverlayBadge(item);
      const width = ctx.measureText(text).width + 8;
      const height = Math.max(16, stroke * 9.5);
      ctx.globalAlpha = 0.88;
      ctx.fillRect(
        item.bbox.x,
        Math.max(height, item.bbox.y) - height,
        width,
        height,
      );
      ctx.globalAlpha = 1;
      ctx.fillStyle = "#ffffff";
      ctx.fillText(text, item.bbox.x + 4, Math.max(height, item.bbox.y) - 3);
      ctx.fillStyle = color;
    }
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
  window.removeEventListener("mousemove", handleRoiMouseMove);
  window.removeEventListener("mouseup", handleRoiMouseUp);
  pollGeneration += 1;
  if (sseAbort) {
    sseAbort.abort();
    sseAbort = null;
  }
  clearMediaUrl();
});
</script>

<template>
  <section class="page parse-workbench">
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
            @click="selectDomain(item.domain_id)"
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
              placeholder="搜索领域名称或 ID"
              aria-label="搜索领域"
            />
          </div>
          <select
            :value="domain"
            aria-label="解析领域"
            @change="selectDomain(($event.target as HTMLSelectElement).value)"
          >
            <option
              v-for="item in filteredDomains"
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
          @click="selectMode('image')"
        >
          <FileImage :size="16" />图片
        </button>
        <button
          v-if="supportedMediaKinds.includes('document')"
          :class="{ active: mode === 'document' }"
          role="tab"
          :aria-selected="mode === 'document'"
          @click="selectMode('document')"
        >
          <FileText :size="16" />文档
        </button>
        <button
          v-if="supportedMediaKinds.includes('video')"
          :class="{ active: mode === 'video' }"
          role="tab"
          :aria-selected="mode === 'video'"
          @click="selectMode('video')"
        >
          <Video :size="16" />视频
        </button>
        <button
          v-if="supportedMediaKinds.includes('stream')"
          :class="{ active: mode === 'stream' }"
          role="tab"
          :aria-selected="mode === 'stream'"
          @click="selectMode('stream')"
        >
          <Radio :size="16" />视频流
        </button>
      </div>
      <label class="pipeline-picker">
        <span class="control-label">流水线</span>
        <select
          v-model="pipelineId"
          :disabled="!domainPipelines.length"
          @change="resetResult"
        >
          <option v-if="!domainPipelines.length" value="">
            暂无可用流水线
          </option>
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
          v-if="run && !isTerminal"
          class="button danger"
          :disabled="transitioning"
          @click="transitionRun('cancel')"
        >
          <Square :size="15" />{{
            run.status === "cancelling" ? "强制取消" : "取消运行"
          }}
        </button>
        <button
          v-if="run?.status === 'running'"
          class="button secondary"
          :disabled="transitioning"
          @click="transitionRun('pause')"
        >
          <Pause :size="15" />暂停
        </button>
        <button
          v-if="run?.status === 'paused'"
          class="button secondary"
          :disabled="transitioning"
          @click="transitionRun('resume')"
        >
          <Play :size="15" />恢复
        </button>
        <button
          class="button primary"
          :disabled="!inputReady || loading"
          @click="execute"
        >
          <Play :size="16" />{{ loading ? "运行中" : "开始解析" }}
        </button>
        <button
          class="button secondary"
          @click="router.push({ path: '/runs', query: { domain } })"
        >
          <Clock3 :size="16" />查看历史运行
        </button>
        <button
          v-if="hasResult && run"
          class="button secondary"
          @click="openHistoryDetail(run)"
        >
          <FileText :size="16" />查看结构化结果
        </button>
      </nav>
    </div>

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
        <div class="media-preview-column">
          <!-- 识别区域 (ROI) 圈选工具栏 -->
          <div class="ocr-roi-toolbar">
            <div class="roi-toolbar-left">
              <button
                type="button"
                class="button small"
                :class="isDrawingRoi ? 'primary' : 'secondary'"
                @click="toggleRoiDrawing"
              >
                <Crop :size="13" />
                {{ isDrawingRoi ? "正在拖拽圈选 (松开完成)" : (selectedRoi ? "重新圈选区域" : "圈选识别区域 (ROI)") }}
              </button>
              <span v-if="selectedRoi" class="roi-badge">
                ROI: [{{ selectedRoi.map((v) => v.toFixed(3)).join(", ") }}]
              </span>
            </div>
            <div v-if="selectedRoi" class="roi-toolbar-right">
              <button
                type="button"
                class="button small ghost text-danger"
                title="清除圈选区域，恢复全画幅识别"
                @click="clearRoi"
              >
                <X :size="13" />
                清除区域
              </button>
            </div>
          </div>

          <div
            ref="mediaStageRef"
            class="media-stage"
            :class="{ 'roi-drawing-mode': isDrawingRoi }"
            @mousedown="handleRoiMouseDown"
          >
            <!-- 圈选专用防劫持透明捕获层 -->
            <div
              v-if="isDrawingRoi"
              class="roi-drawing-layer"
            />
            <img
              v-if="mode === 'image' && displayedMediaUrl"
              :src="displayedMediaUrl"
              alt="待解析图片"
              draggable="false"
              @load="onStageResize"
              @error="handleImageError"
            />
            <template
              v-else-if="
                mode === 'video' && (displayedMediaUrl || resultFrameUrl)
              "
            >
              <img
                v-if="shouldUseResultFrame && resultFrameUrl"
                :src="resultFrameUrl"
                alt="当前解析帧"
                @load="handleResultFrameLoaded"
              />
              <img
                v-else-if="serverPreviewUrl && !result && !videoPlaying"
                :src="serverPreviewUrl"
                alt="视频首帧预览"
                draggable="false"
                @load="onStageResize"
              />
              <video
                v-else-if="mediaUrl && !videoPlaybackFailed"
                ref="videoElement"
                :src="mediaUrl"
                controls
                preload="auto"
                @loadedmetadata="syncVideoToSelectedUnit"
                @loadeddata="handleVideoLoadedData"
                @seeked="handleVideoSeeked"
                @play="handleVideoPlay"
                @pause="handleVideoPause"
                @error="handleVideoPlaybackError"
              />
              <img
                v-else-if="serverPreviewUrl"
                :src="serverPreviewUrl"
                alt="视频首帧预览"
                draggable="false"
                @load="onStageResize"
              />
              <div v-else class="empty">
                视频文件无法在浏览器中播放，解析后将显示首帧
              </div>
            </template>
            <template
              v-else-if="mode === 'document' && (file || selectedAsset)"
            >
              <img
                v-if="shouldUseResultFrame && resultFrameUrl"
                :src="resultFrameUrl"
                alt="当前解析页"
                draggable="false"
                @load="handleResultFrameLoaded"
              />
              <img
                v-else-if="serverPreviewUrl"
                :src="serverPreviewUrl"
                alt="文档首页预览"
                draggable="false"
                @load="onStageResize"
              />
              <div v-else class="stream-stage">
                <FileText :size="28" />
                <strong>{{ file?.name || selectedAsset?.filename }}</strong>
                <span
                  >{{
                    (
                      (file?.size || selectedAsset?.size_bytes || 0) /
                      1024 /
                      1024
                    ).toFixed(2)
                  }}
                  MiB · 解析后按页浏览结果</span
                >
              </div>
            </template>
            <template v-else-if="mode === 'stream'">
              <img
                v-if="shouldUseResultFrame && resultFrameUrl"
                :src="resultFrameUrl"
                alt="当前解析帧"
                draggable="false"
                @load="handleResultFrameLoaded"
              />
              <img
                v-else-if="streamPreviewUrl"
                :src="streamPreviewUrl"
                alt="实时流首帧预览"
                draggable="false"
                @load="onStageResize"
              />
              <div v-else class="stream-stage">
                <Radio :size="28" />
                <strong>{{
                  selectedSource?.name || sourceName || "未选择视频流"
                }}</strong>
                <span>{{
                  selectedSource?.masked_url ||
                  sourceUrl ||
                  "登记或选择一个视频流源"
                }}</span>
              </div>
            </template>
            <div v-else class="empty">
              等待{{
                mode === "image"
                  ? "图片"
                  : mode === "document"
                    ? "PDF 文档"
                    : "视频文件"
              }}
            </div>
            <canvas
              v-show="overlayReady"
              ref="overlayCanvas"
              class="overlay"
              aria-hidden="true"
            />
            <!-- 识别区域 (ROI) 选框覆层 -->
            <div
              v-if="roiBoxStyle"
              class="roi-overlay-box"
              :style="roiBoxStyle"
            >
              <span class="roi-box-label">ROI 识别区域</span>
            </div>
          </div>
          <div v-if="overlayStatus" class="overlay-status" aria-live="polite">
            <Info :size="14" />
            <span>{{ overlayStatus }}</span>
          </div>
        </div>

        <div class="input-controls">
          <template v-if="mode !== 'stream'">
            <div class="input-origin">
              <span class="control-label">数据来源</span>
              <div
                class="segmented origin-modes"
                role="group"
                aria-label="数据来源"
              >
                <button
                  :class="{ active: inputOrigin === 'upload' }"
                  :aria-pressed="inputOrigin === 'upload'"
                  @click="selectOrigin('upload')"
                >
                  <Upload :size="15" />当前上传
                </button>
                <button
                  :class="{ active: inputOrigin === 'library' }"
                  :aria-pressed="inputOrigin === 'library'"
                  @click="selectOrigin('library')"
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
                @change="selectFile"
              />
              <small v-if="file" class="file-info-hint">
                已就绪 · {{ (file.size / (1024 * 1024)).toFixed(2) }} MB
              </small>
            </label>

            <div v-else class="library-picker-row">
              <label>
                <span>文件资产</span>
                <select v-model="assetId" @change="selectLibraryAsset">
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
                @click="refreshWorkspaceResources"
              >
                <RefreshCw :size="16" :class="{ spin: loadingSources }" />
              </button>
            </div>
          </template>

          <template v-else>
            <div class="library-picker-row">
              <label>
                <span>已登记视频流</span>
                <select v-model="sourceId" @change="loadStreamPreview(sourceId)">
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
                @click="refreshSources"
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
                    @click="previewNewStream"
                  >
                    <Eye :size="13" />
                    <span>预览首帧</span>
                  </button>
                </div>
              </label>
            </template>
          </template>

          <div v-if="mode === 'document'" class="parameter-grid">
            <label>
              <span>渲染倍率</span>
              <input
                v-model.number="pageScale"
                type="number"
                min="0.5"
                max="4"
                step="0.5"
              />
            </label>
          </div>

          <template v-else-if="mode !== 'image'">
            <div class="parameter-grid">
              <label>
                <span>采样策略</span>
                <select v-model="sampleStrategy">
                  <option
                    v-for="(text, value) in STRATEGY_LABELS"
                    :key="value"
                    :value="value"
                  >
                    {{ text }}
                  </option>
                </select>
              </label>
              <label>
                <span>采样间隔（毫秒）</span>
                <input
                  v-model.number="sampleIntervalMs"
                  type="number"
                  min="1"
                  max="3600000"
                  step="100"
                  :disabled="sampleStrategy !== 'interval'"
                />
              </label>
              <label>
                <span>{{
                  mode === "stream" ? "开始后跳过（毫秒）" : "起始时间（毫秒）"
                }}</span>
                <input
                  v-model.number="sampleStartMs"
                  type="number"
                  min="0"
                  step="1000"
                />
              </label>
              <label>
                <span>{{
                  mode === "stream"
                    ? "最大分析时长（毫秒）"
                    : "结束时间（毫秒）"
                }}</span>
                <input
                  v-model.number="sampleEndMs"
                  type="number"
                  min="0"
                  step="1000"
                  placeholder="不限"
                />
              </label>
              <label v-if="sampleStrategy === 'scene_change'">
                <span>场景切换阈值</span>
                <input
                  v-model.number="sceneChangeThreshold"
                  type="number"
                  min="0.01"
                  max="1"
                  step="0.05"
                />
              </label>
              <label>
                <span>帧最大边长（像素）</span>
                <input
                  v-model.number="frameMaxEdge"
                  type="number"
                  min="64"
                  max="8192"
                  step="64"
                  placeholder="原始尺寸"
                />
              </label>
              <template v-if="mode === 'stream'">
                <label>
                  <span>最大重连次数</span>
                  <input
                    v-model.number="maxReconnectAttempts"
                    type="number"
                    min="0"
                    max="20"
                  />
                </label>
                <label>
                  <span>连接超时（毫秒）</span>
                  <input
                    v-model.number="connectTimeoutMs"
                    type="number"
                    min="100"
                    max="120000"
                    step="100"
                  />
                </label>
                <label>
                  <span>读取超时（毫秒）</span>
                  <input
                    v-model.number="readTimeoutMs"
                    type="number"
                    min="100"
                    max="120000"
                    step="100"
                  />
                </label>
              </template>
            </div>
          </template>

          <div v-if="parameterEntries.length" class="domain-parameters">
            <span class="control-label domain-params-heading">领域参数配置</span>
            <!-- 紧凑水平开关胶囊行 -->
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

            <!-- 数值与文本字段网格 -->
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

    <section class="panel history-panel">
      <div class="panel-header">
        <div class="history-title-group">
          <h2>最近运行</h2>
          <p>{{ currentDomainLabel }} 最近运行记录</p>
        </div>
        <div class="toolbar compact history-toolbar">
          <button
            class="button secondary"
            :disabled="loadingHistory"
            @click="refreshHistory"
          >
            <RefreshCw :size="14" :class="{ spin: loadingHistory }" />刷新
          </button>
          <RouterLink
            class="button secondary"
            :to="{ path: '/runs', query: { domain } }"
          >
            查看全部
          </RouterLink>
        </div>
      </div>
      <DataTable
        :columns="historyRunColumns"
        :items="scopedHistoryRuns"
        :loading="loadingHistory"
        :loading-text="'正在加载历史运行...'"
        :empty-text="`暂无 ${currentDomainLabel} 历史运行记录`"
      >
        <template #pipeline="{ row }">
          <strong>{{ labelPipeline(row.pipeline.pipeline_id) }}</strong>
          <small v-if="row.pipeline.version" class="muted"> · {{ row.pipeline.version }}</small>
        </template>
        <template #asset_source="{ row }">
          {{ row.asset_id || row.source_id || '-' }}
        </template>
        <template #status="{ row }">
          <span class="badge" :class="row.status">{{
            labelRunStatus(row.status)
          }}</span>
        </template>
        <template #created_at="{ row }">
          {{ formatRunDate(row.created_at) }}
        </template>
        <template #actions="{ row }">
          <button
            class="button secondary history-detail-btn"
            title="查看此任务解析结果与回看"
            @click="openHistoryDetail(row)"
          >
            <Eye :size="13" />详情
          </button>
        </template>
      </DataTable>
    </section>

    <ResultDetailDrawer
      v-model:open="isDetailOpen"
      :run-id="detailRunId"
    />
  </section>
</template>

<style scoped>
.parse-workbench {
  gap: 14px;
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
.parse-context-nav {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
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
  transition: all 150ms ease;
}
.parse-context-nav a:hover,
.parse-context-nav a.active {
  border-color: var(--teal);
  background: #e7f1ee;
  color: var(--teal);
}
.workbench-config {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--line);
  flex-wrap: wrap;
}
.parse-context-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-left: auto;
}
.workbench-config > div:not(.media-modes),
.pipeline-picker,
.input-origin {
  display: grid;
  gap: 6px;
}
.control-label {
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}
.capability-modes,
.origin-modes {
  width: fit-content;
}
.capability-modes button,
.origin-modes button {
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
.media-modes button {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.input-layout {
  display: grid;
  grid-template-columns: minmax(360px, 1.15fr) minmax(320px, 0.85fr);
  gap: 18px;
  align-items: start;
}
.media-preview-column {
  display: grid;
  align-content: start;
  gap: 8px;
  min-width: 0;
}
.media-stage {
  position: relative;
  width: 100%;
  min-width: 0;
  aspect-ratio: 16 / 9;
  display: grid;
  place-items: center;
  overflow: hidden;
  background: #101816;
  color: #dbe6e2;
  border-radius: 6px;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08);
}
.media-stage img,
.media-stage video,
.overlay {
  position: absolute;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.overlay {
  pointer-events: none;
}
.overlay-status {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  box-sizing: border-box;
  min-height: 30px;
  padding: 6px 9px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: #f4f8f6;
  color: var(--muted);
  font-size: 12px;
  text-align: left;
  pointer-events: none;
}
.stream-stage {
  display: grid;
  justify-items: center;
  gap: 8px;
  max-width: 80%;
  text-align: center;
}
.stream-stage span {
  color: #9fb1aa;
  overflow-wrap: anywhere;
}
.input-controls {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
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
  font-size: 12px;
  font-weight: 700;
  color: var(--muted);
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

/* 紧凑领域布尔开关胶囊行 */
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
  background: var(--surface, #ffffff);
  border: 1px solid var(--line, #cbd5e1);
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-soft, #475569);
  cursor: pointer;
  user-select: none;
  transition: all 0.15s ease;
  line-height: 1.2;
  box-sizing: border-box;
}
.switch-pill:hover {
  background: #f1f5f9;
  border-color: #94a3b8;
  color: var(--text, #1e293b);
}
.switch-pill.active,
.switch-pill.checked {
  background: #ecfdf5;
  border-color: #10b981;
  color: #047857;
  font-weight: 600;
  box-shadow: 0 0 0 1px rgba(16, 185, 129, 0.25);
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
.input-controls label,
.file-picker {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.input-controls label > span {
  font-size: 12px;
  font-weight: 700;
  color: var(--muted);
}
.file-picker input[type="file"] {
  display: flex;
  align-items: center;
  height: 36px;
  min-height: 36px;
  padding: 4px 6px;
  border: 1px solid var(--line, #cbd5e1);
  border-radius: 4px;
  background: var(--surface, #ffffff);
  font-size: 12px;
  color: var(--muted, #64748b);
  cursor: pointer;
  box-sizing: border-box;
  transition:
    border-color 150ms ease,
    box-shadow 150ms ease;
}
.file-picker input[type="file"]:hover {
  border-color: #94a3b8;
}
.file-picker input[type="file"]:focus {
  border-color: #10b981;
  box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.15);
  outline: none;
}
.file-picker input[type="file"]::file-selector-button,
.file-picker input[type="file"]::-webkit-file-upload-button {
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
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  transition: all 150ms ease;
  box-sizing: border-box;
}
.file-picker input[type="file"]::file-selector-button:hover,
.file-picker input[type="file"]:hover::-webkit-file-upload-button {
  background: #ecfdf5;
  border-color: #10b981;
  color: #047857;
}
.file-picker small {
  overflow-wrap: anywhere;
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
.library-picker-row .source-refresh,
.source-refresh {
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
.run-strip {
  display: grid;
  grid-template-columns: minmax(260px, auto) minmax(160px, 1fr) auto;
  align-items: center;
  gap: 12px;
  margin-top: 14px;
  padding: 10px 14px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface);
}
.run-strip > div:first-child {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}
.progress-track {
  height: 7px;
  overflow: hidden;
  background: #dfe6e3;
  border-radius: 3px;
}
.progress-track span {
  display: block;
  height: 100%;
  background: var(--teal);
  transition: width 0.2s ease;
}
.progress-value {
  display: grid;
  justify-items: end;
  min-width: 92px;
}
.progress-value small {
  color: var(--muted);
  font-size: 11px;
  white-space: nowrap;
}
.warning-panel {
  margin-top: 14px;
}
.warning-panel h2 {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: #7c4b08;
}
.warning-list {
  display: grid;
  gap: 7px;
  margin: 0;
  padding-left: 20px;
}
.warning-list li {
  color: #7c4b08;
  font-size: 12px;
  overflow-wrap: anywhere;
}
.results-layout {
  display: block;
  margin-top: 14px;
}
.result-counters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  margin: 0 0 14px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #f8faf9;
  overflow: hidden;
}
.result-counters div {
  padding: 10px 14px;
  border-right: 1px solid var(--line);
}
.result-counters div:last-child {
  border-right: 0;
}
.result-counters dt {
  color: var(--muted);
  font-size: 11px;
  font-weight: 650;
}
.result-counters dd {
  margin: 4px 0 0;
  font-size: 20px;
  font-weight: 700;
  color: #17211f;
}
.metadata-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  margin: 0 0 14px;
  background: var(--line);
  border: 1px solid var(--line);
  border-radius: 6px;
  overflow: hidden;
}
.metadata-grid div {
  padding: 9px 10px;
  background: var(--surface);
}
.metadata-grid .metadata-wide {
  grid-column: 1 / -1;
}
.metadata-grid dt {
  color: var(--muted);
  font-size: 11px;
}
.metadata-grid dd {
  margin: 3px 0 0;
  font-weight: 700;
  overflow-wrap: anywhere;
}
.result-summary textarea {
  width: 100%;
  min-height: 160px;
  margin-bottom: 12px;
}
.result-empty {
  min-height: 260px;
}
.history-panel {
  margin-top: 14px;
}
.history-panel .history-title-group {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}
.history-panel .history-title-group h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text, #17211f);
  white-space: nowrap;
}
.history-panel .history-title-group p,
.history-panel .panel-header p {
  margin: 0;
  color: var(--muted, #64716d);
  font-size: 12px;
  line-height: 1.4;
  white-space: nowrap;
}
.history-toolbar {
  display: flex !important;
  flex-direction: row !important;
  align-items: center !important;
  flex-wrap: nowrap !important;
  gap: 8px !important;
  margin-left: auto;
}
.history-load-btn {
  height: 22px;
  min-height: 22px;
  padding: 0 6px;
  font-size: 11px;
  gap: 3px;
  border-radius: 3px;
}
.history-empty {
  min-height: 60px;
  padding: 16px;
  text-align: center;
  color: var(--muted);
  font-size: 12px;
}
.unit-list {
  display: grid;
  max-height: 620px;
  overflow: auto;
}
.unit-list button {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  gap: 9px;
  align-items: center;
  width: 100%;
  padding: 9px 12px;
  border: 0;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
  color: var(--text);
  text-align: left;
  cursor: pointer;
  transition: background 150ms ease;
}
.unit-list button:hover {
  background: #f4f7f6;
}
.unit-list button.selected {
  background: #edf5f3;
  box-shadow: inset 3px 0 0 var(--teal);
}
.unit-list small {
  display: block;
  margin-top: 2px;
  color: var(--muted);
}
.unit-index {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--line);
  border-radius: 3px;
  font-size: 11px;
}
pre {
  max-height: 320px;
  overflow: auto;
  padding: 12px;
  background: #101816;
  color: #dbe6e2;
  border-radius: 4px;
  font-size: 11px;
}
.spin {
  animation: spin 0.9s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
@media (max-width: 900px) {
  .parse-context-bar {
    align-items: start;
    flex-direction: column;
  }
  .parse-context-nav {
    justify-content: flex-start;
  }
  .input-layout,
  .results-layout {
    grid-template-columns: 1fr;
  }
  .metadata-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .run-strip {
    grid-template-columns: 1fr auto;
  }
  .run-strip .progress-track {
    grid-column: 1 / -1;
    grid-row: 2;
  }
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
  .capability-modes,
  .origin-modes {
    width: 100%;
  }
  .capability-modes button,
  .origin-modes button {
    flex: 1;
  }
  .media-modes {
    width: 100%;
  }
  .media-modes button {
    flex: 1;
    justify-content: center;
    min-width: 0;
  }
  .input-layout {
    display: block;
  }
  .input-controls {
    margin-top: 12px;
  }
  .parameter-grid {
    grid-template-columns: 1fr;
  }
  .result-counters {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .result-counters div {
    padding-inline: 8px;
  }
}

/* OCR ROI Selection */
.ocr-roi-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  background: var(--surface-soft, #f8fafc);
  border: 1px solid var(--line, #e2e8f0);
  border-radius: 6px;
  margin-bottom: 8px;
}

.roi-toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.roi-badge {
  font-size: 11px;
  font-family: var(--font-mono, monospace);
  background: #eff6ff;
  color: #2563eb;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
}

.roi-drawing-layer {
  position: absolute;
  inset: 0;
  z-index: 20;
  cursor: crosshair;
  background: transparent;
}

.media-stage.roi-drawing-mode {
  cursor: crosshair !important;
  user-select: none !important;
  -webkit-user-select: none !important;
}

.media-stage.roi-drawing-mode * {
  pointer-events: none !important;
  user-select: none !important;
  -webkit-user-select: none !important;
  -webkit-user-drag: none !important;
}

.media-stage img,
.media-stage video {
  -webkit-user-drag: none;
  user-select: none;
}

.roi-overlay-box {
  position: absolute;
  border: 2px dashed #2563eb;
  background: rgba(37, 99, 235, 0.18);
  pointer-events: none;
  z-index: 12;
  box-sizing: border-box;
  transition: none;
}

.roi-box-label {
  position: absolute;
  top: 0;
  left: 0;
  background: #2563eb;
  color: #ffffff;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-bottom-right-radius: 4px;
  user-select: none;
  pointer-events: none;
}
</style>
