<script setup lang="ts">
import {
  AlertTriangle,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Clock3,
  Download,
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
import FeatureCropGallery from "../components/FeatureCropGallery.vue";
import GenericDomainResult from "../components/GenericDomainResult.vue";
import {
  useDomainCatalog,
  type MediaMode,
} from "../composables/useDomainCatalog";
import { useMediaPreview } from "../composables/useMediaPreview";
import { useRefresh } from "../composables/useRefresh";
import {
  labelDomain,
  labelMediaKind,
  labelPipeline,
  labelRunError,
  labelRunStatus,
  labelSampleStrategy,
  labelTerminationReason,
  labelWarning,
} from "../labels";
import type {
  Domain,
  MediaAsset,
  MediaUnitResult,
  MediaSource,
  ResultEnvelope,
  ResultPage,
  Run,
  RunPage,
  VisionObject,
  OcrBlock,
  TableColumn,
} from "../types";
import DataTable from "../components/DataTable.vue";

const objectColumns: TableColumn<VisionObject>[] = [
  { key: "object_id", label: "对象", class: "mono" },
  { key: "object_type", label: "类型" },
  { key: "score", label: "置信度" },
  { key: "bbox", label: "边框 x, y, w, h", class: "mono" },
];

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
const showAdvanced = ref(false);

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
function payloadList<T>(key: string): T[] {
  const value = result.value?.domain_payload[key];
  return Array.isArray(value) ? (value as T[]) : [];
}

const persons = computed(() =>
  result.value?.domain_payload.domain === "portrait"
    ? payloadList<VisionObject>("persons")
    : [],
);
const ocrBlocks = computed(() =>
  result.value?.domain_payload.domain === "ocr"
    ? payloadList<OcrBlock>("blocks")
    : [],
);
const ocrText = computed(() =>
  result.value?.domain_payload.domain === "ocr" &&
  typeof result.value.domain_payload.text === "string"
    ? result.value.domain_payload.text
    : "",
);
const genericPayload = computed(() => {
  const payload = result.value?.domain_payload;
  return payload && !["portrait", "ocr"].includes(payload.domain)
    ? payload
    : null;
});
const selectedUnit = computed(
  () => result.value?.units[selectedUnitIndex.value] ?? result.value?.units[0],
);
const selectedObjects = computed(() => selectedUnit.value?.objects ?? []);

const TIMELINE_WINDOW_SIZE = 100;
interface TimelineItem {
  unit: MediaUnitResult | null;
  index: number;
  jump?: "start" | "end";
}
const timelineItems = computed<TimelineItem[]>(() => {
  const units = result.value?.units ?? [];
  if (units.length <= TIMELINE_WINDOW_SIZE * 2 + 1) {
    return units.map((unit, index) => ({ unit, index }));
  }
  const selected = Math.min(selectedUnitIndex.value, units.length - 1);
  const start = Math.max(0, selected - TIMELINE_WINDOW_SIZE);
  const end = Math.min(units.length, start + TIMELINE_WINDOW_SIZE * 2 + 1);
  const items: TimelineItem[] = units
    .slice(start, end)
    .map((unit, offset) => ({ unit, index: start + offset }));
  if (start > 0) items.unshift({ unit: null, index: 0, jump: "start" });
  if (end < units.length) items.push({ unit: null, index: units.length - 1, jump: "end" });
  return items;
});

const resultJson = computed(() => JSON.stringify(result.value, null, 2));
const mediaMetadata = computed(() => result.value?.media_metadata ?? null);
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
const totalObjects = computed(
  () => result.value?.units.reduce((s, u) => s + u.objects.length, 0) ?? 0,
);
const sampledUnitCount = computed(
  () => mediaMetadata.value?.sampled_units ?? result.value?.units.length ?? 0,
);
const resultUnitCount = computed(() => result.value?.units.length ?? 0);
const hasFilteredResultUnits = computed(
  () =>
    (mode.value === "video" || mode.value === "stream") &&
    sampledUnitCount.value > resultUnitCount.value,
);
const hasResult = computed(() => !!result.value);
const currentDomainLabel = computed(
  () => selectedDomainManifest.value?.display_name || labelDomain(domain.value),
);
const isDomainScoped = computed(() =>
  Boolean(route.params?.domain || props.initialDomain || domain.value),
);
const currentMediaLabel = computed(() => labelMediaKind(mode.value));
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
  showAdvanced.value = false;
  clearMediaUrl();
  resetResult();
  if (value === "stream") void refreshSources();
  navigateWorkspace(domain.value, value);
}

function selectOrigin(value: InputOrigin): void {
  inputOrigin.value = value;
  file.value = null;
  assetId.value = "";
  clearMediaUrl();
  resetResult();
}

function selectDomain(value: Domain): void {
  if (domain.value === value) return;
  domain.value = value;
  pipelineId.value = "";
  domainSearch.value = "";
  resetResult();
  syncPipelineSelection();
  ensureSupportedMode();
  navigateWorkspace(value, mode.value);
  void refreshHistory();
}

function selectFile(event: Event): void {
  const selected = (event.target as HTMLInputElement).files?.[0] ?? null;
  inputOrigin.value = "upload";
  assetId.value = "";
  file.value = selected;
  clearMediaUrl();
  mediaUrl.value = selected ? URL.createObjectURL(selected) : "";
  resetResult();
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
    if (!page.result.units.length) break;
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
        } else if (run.value && !isTerminal.value) {
          run.value = {
            ...run.value,
            status: event.status ?? run.value.status,
            progress: event.payload?.progress ?? run.value.progress,
          };
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
    if (progressChanged && !isTerminal.value) {
      void loadResult(initial.run_id, true).catch(() => undefined);
    }
  }
  if (sseAbort) {
    sseAbort.abort();
    sseAbort = null;
  }
  if (generation !== pollGeneration || run.value.status !== "completed") return;
  await loadResult(initial.run_id);
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
  const asset = await api<MediaAsset>("/api/v1/media/assets", {
    method: "POST",
    body: form,
  });
  assets.value = [
    asset,
    ...assets.value.filter((item) => item.asset_id !== asset.asset_id),
  ];
  assetId.value = asset.asset_id;
  inputOrigin.value = "library";
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
  if (parameters.read_timeout_ms != null)
    readTimeoutMs.value = Number(parameters.read_timeout_ms);
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
    if (existing.status === "completed") {
      await loadResult(existing.run_id);
    } else if (!["failed", "cancelled"].includes(existing.status)) {
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
    if (!["completed", "failed", "cancelled"].includes(updated.status))
      followRun(updated);
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

function selectUnit(index: number): void {
  const alreadySelected = selectedUnitIndex.value === index;
  selectedUnitIndex.value = index;
  followLatestUnit.value = index >= (result.value?.units.length ?? 1) - 1;
  if (alreadySelected) syncSelectedMediaFrame();
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
  image_region: "#8a63c9",
  table_region: "#c98a17",
};

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
      if (item.score != null) {
        const text = item.score.toFixed(2);
        const width = ctx.measureText(text).width + 6;
        const height = Math.max(14, stroke * 9);
        ctx.globalAlpha = 0.85;
        ctx.fillRect(
          item.bbox.x,
          Math.max(height, item.bbox.y) - height,
          width,
          height,
        );
        ctx.globalAlpha = 1;
        ctx.fillStyle = "#ffffff";
        ctx.fillText(text, item.bbox.x + 3, Math.max(height, item.bbox.y) - 2);
        ctx.fillStyle = color;
      }
    }
  }
}

function exportResult(format: "json" | "csv"): void {
  const current = result.value;
  if (!current) return;
  let blob: Blob;
  let extension: string;
  if (format === "json") {
    blob = new Blob([JSON.stringify(current, null, 2)], {
      type: "application/json",
    });
    extension = "json";
  } else {
    const header =
      "单元标识,单元类型,索引,时间点毫秒,页码,宽,高,对象标识,对象类型,置信度,边框x,边框y,边框宽,边框高";
    const rows: string[] = [header];
    for (const unit of current.units) {
      if (!unit.objects.length) {
        rows.push(
          [
            unit.unit_id,
            unit.unit_type,
            unit.index,
            unit.pts_ms ?? "",
            unit.page_number ?? "",
            unit.width,
            unit.height,
            "",
            "",
            "",
            "",
            "",
            "",
            "",
          ].join(","),
        );
        continue;
      }
      for (const item of unit.objects) {
        rows.push(
          [
            unit.unit_id,
            unit.unit_type,
            unit.index,
            unit.pts_ms ?? "",
            unit.page_number ?? "",
            unit.width,
            unit.height,
            item.object_id,
            item.object_type,
            item.score?.toFixed(4) ?? "",
            item.bbox?.x.toFixed(2) ?? "",
            item.bbox?.y.toFixed(2) ?? "",
            item.bbox?.width.toFixed(2) ?? "",
            item.bbox?.height.toFixed(2) ?? "",
          ].join(","),
        );
      }
    }
    blob = new Blob(["﻿" + rows.join("\n")], {
      type: "text/csv;charset=utf-8",
    });
    extension = "csv";
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `scenara-${current.run_id}.${extension}`;
  link.click();
  URL.revokeObjectURL(url);
}

function formatTime(milliseconds?: number | null): string {
  if (milliseconds == null) return "-";
  const seconds = milliseconds / 1000;
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;
}

function formatDuration(milliseconds?: number | null): string {
  return milliseconds == null ? "未知" : formatTime(milliseconds);
}

function formatRunDate(value: number): string {
  return new Date(value * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function historyMode(runItem: Run): MediaMode {
  const asset = runItem.asset_id
    ? assets.value.find((candidate) => candidate.asset_id === runItem.asset_id)
    : null;
  return asset?.kind ?? (runItem.source_id ? "stream" : mode.value);
}

function openHistory(runItem: Run): void {
  void router.push({
    path: workspacePath(runItem.domain, historyMode(runItem)),
    query: { run: runItem.run_id },
  });
}

function labelTimestampSource(value: string): string {
  return (
    {
      decoder_pts: "解码器时间戳",
      position_msec: "媒体位置时间戳",
      monotonic_clock: "单调作业时钟",
    }[value] ?? "未知"
  );
}

function formatBox(
  item:
    { x: number; y: number; width: number; height: number } | null | undefined,
): string {
  if (!item) return "-";
  return [item.x, item.y, item.width, item.height]
    .map((value) => value.toFixed(1))
    .join(", ");
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
onMounted(async () => {
  await refreshWorkspaceResources();
  await restoreRouteSelection();
  await refreshHistory();
});
useRefresh(async () => {
  await Promise.all([refreshWorkspaceResources(), refreshHistory()]);
});
onBeforeUnmount(() => {
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
    <div v-if="hasResult" class="page-header">
      <div class="toolbar">
        <button
          class="button secondary"
          title="导出结构化结果"
          @click="exportResult('json')"
        >
          <Download :size="15" />导出 JSON
        </button>
        <button
          class="button secondary"
          title="导出对象明细表"
          @click="exportResult('csv')"
        >
          <Download :size="15" />导出 CSV
        </button>
      </div>
    </div>

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
          v-if="supportedMediaKinds.includes('video')"
          :class="{ active: mode === 'video' }"
          role="tab"
          :aria-selected="mode === 'video'"
          @click="selectMode('video')"
        >
          <Video :size="16" />视频
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
          v-if="hasResult"
          class="button secondary"
          @click="router.push('/results')"
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
          <div class="media-stage">
            <img
              v-if="mode === 'image' && displayedMediaUrl"
              :src="displayedMediaUrl"
              alt="待解析图片"
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
              <video
                v-else-if="mediaUrl && !videoPlaybackFailed"
                ref="videoElement"
                :src="mediaUrl"
                controls
                preload="metadata"
                @loadedmetadata="syncVideoToSelectedUnit"
                @seeked="handleVideoSeeked"
                @play="handleVideoPlay"
                @pause="handleVideoPause"
                @error="handleVideoPlaybackError"
              />
              <img
                v-else-if="serverPreviewUrl"
                :src="serverPreviewUrl"
                alt="视频首帧预览"
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
                @load="handleResultFrameLoaded"
              />
              <img
                v-else-if="serverPreviewUrl"
                :src="serverPreviewUrl"
                alt="文档首页预览"
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
                @load="handleResultFrameLoaded"
              />
              <img
                v-else-if="streamPreviewUrl"
                :src="streamPreviewUrl"
                alt="实时流首帧预览"
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
              <small>{{ file?.name || "尚未选择文件" }}</small>
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
            <label
              ><span>已登记视频流</span
              ><select v-model="sourceId" @change="loadStreamPreview(sourceId)">
                <option value="">登记新视频流</option>
                <option
                  v-for="source in sources"
                  :key="source.source_id"
                  :value="source.source_id"
                >
                  {{ source.name }} · {{ source.masked_url }}
                </option>
              </select></label
            >
            <button
              class="icon-button source-refresh"
              :disabled="loadingSources"
              title="刷新视频流"
              aria-label="刷新视频流"
              @click="refreshSources"
            >
              <RefreshCw :size="16" :class="{ spin: loadingSources }" />
            </button>
            <template v-if="!sourceId">
              <label
                ><span>视频流名称</span
                ><input
                  v-model.trim="sourceName"
                  maxlength="256"
                  placeholder="例如：东门摄像头"
              /></label>
              <label
                ><span>视频流地址</span
                ><input
                  v-model.trim="sourceUrl"
                  maxlength="4096"
                  placeholder="rtsp://host/path"
              /></label>
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
            <label
              ><span>采样策略</span>
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
            <div class="parameter-grid">
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
              class="button secondary advanced-toggle"
              @click="showAdvanced = !showAdvanced"
            >
              <component
                :is="showAdvanced ? ChevronUp : ChevronDown"
                :size="15"
              />{{ showAdvanced ? "收起高级参数" : "展开高级参数" }}
            </button>
            <div v-if="showAdvanced" class="parameter-grid">
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
                  mode === "stream"
                    ? "最大分析时长（毫秒）"
                    : "结束时间（毫秒）"
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

          <div v-if="parameterEntries.length" class="domain-parameters">
            <span class="control-label">领域参数</span>
            <div class="parameter-grid">
              <label
                v-for="[key, definition] in parameterEntries"
                :key="key"
                :class="{ 'parameter-wide': definition.control === 'text' }"
              >
                <span>{{ definition.label }}</span>
                <input
                  v-if="definition.control === 'boolean'"
                  v-model="pipelineParameters[key]"
                  type="checkbox"
                />
                <input
                  v-else-if="['integer', 'number'].includes(definition.control)"
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
                    {{ option }}
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

    <div class="results-layout">
      <section class="panel result-summary">
        <div class="panel-header">
          <h2>解析结果</h2>
          <Clock3 v-if="loading" :size="16" class="spin" />
        </div>
        <div v-if="result" class="panel-body">
          <dl class="result-counters">
            <div>
              <dt>{{ hasFilteredResultUnits ? "采样单元" : "分析单元" }}</dt>
              <dd>{{ sampledUnitCount }}</dd>
            </div>
            <div v-if="hasFilteredResultUnits">
              <dt>命中单元</dt>
              <dd>{{ resultUnitCount }}</dd>
            </div>
            <div>
              <dt>识别对象</dt>
              <dd>{{ totalObjects || persons.length || ocrBlocks.length }}</dd>
            </div>
            <div>
              <dt>模型</dt>
              <dd>{{ result.models.length }}</dd>
            </div>
          </dl>
          <dl v-if="mediaMetadata" class="metadata-grid">
            <div>
              <dt>画面尺寸</dt>
              <dd>
                {{ mediaMetadata.width || selectedUnit?.width }} ×
                {{ mediaMetadata.height || selectedUnit?.height }}
              </dd>
            </div>
            <div>
              <dt>时长</dt>
              <dd>{{ formatDuration(mediaMetadata.duration_ms) }}</dd>
            </div>
            <div>
              <dt>帧率</dt>
              <dd>{{ mediaMetadata.fps?.toFixed(2) || "未知" }}</dd>
            </div>
            <div>
              <dt>编码</dt>
              <dd>
                {{ mediaMetadata.codec || mediaMetadata.format || "未知" }}
              </dd>
            </div>
            <div v-if="mediaMetadata.sample_strategy">
              <dt>采样策略</dt>
              <dd>{{ labelSampleStrategy(mediaMetadata.sample_strategy) }}</dd>
            </div>
            <div v-if="mediaMetadata.frames_read != null">
              <dt>读取帧数</dt>
              <dd>{{ mediaMetadata.frames_read }}</dd>
            </div>
            <div v-if="mediaMetadata.reconnect_count != null">
              <dt>重连次数</dt>
              <dd>{{ mediaMetadata.reconnect_count }}</dd>
            </div>
            <div v-if="mediaMetadata.elapsed_ms != null">
              <dt>解码耗时</dt>
              <dd>{{ (mediaMetadata.elapsed_ms / 1000).toFixed(2) }} 秒</dd>
            </div>
            <div v-if="mediaMetadata.timestamp_source" class="metadata-wide">
              <dt>时间戳来源</dt>
              <dd>
                {{ labelTimestampSource(mediaMetadata.timestamp_source) }}
              </dd>
            </div>
          </dl>
          <textarea
            v-if="domain === 'ocr'"
            readonly
            :value="ocrText"
            aria-label="OCR 文本结果"
          />
          <GenericDomainResult
            v-if="genericPayload"
            :payload="genericPayload"
          />
          <DataTable
            v-if="selectedObjects.length"
            :columns="objectColumns"
            :items="selectedObjects"
            table-class="bordered-table"
          >
            <template #score="{ row }">
              {{ row.score?.toFixed(3) ?? "-" }}
            </template>
            <template #bbox="{ row }">
              <span class="mono">{{ formatBox(row.bbox) }}</span>
            </template>
          </DataTable>
          <details>
            <summary>原始结果（JSON）</summary>
            <pre>{{ resultJson }}</pre>
          </details>
        </div>
        <div v-else class="empty result-empty">
          {{ loading ? "正在解析数据" : "暂无结果" }}
        </div>
      </section>

      <div class="results-aside">
        <FeatureCropGallery
          v-if="result"
          :run-id="result.run_id"
          :unit="selectedUnit ?? null"
          :fallback-large-url="displayedMediaUrl"
        />

        <section class="panel timeline-panel">
          <div class="panel-header">
            <h2>
              {{
                mode === "image"
                  ? "解析单元"
                  : mode === "document"
                    ? "页面"
                    : "时间轴"
              }}
            </h2>
            <span class="badge">{{ result?.units.length || 0 }}</span>
          </div>
          <div v-if="result?.units.length" class="unit-list">
            <button
              v-for="item in timelineItems"
              :key="item.unit ? item.unit.unit_id : `jump-${item.jump}`"
              :class="{ selected: selectedUnitIndex === item.index }"
              :title="
                item.unit
                  ? undefined
                  : item.jump === 'start'
                    ? '跳到首个单元'
                    : '跳到末尾'
              "
              @click="selectUnit(item.index)"
            >
              <template v-if="item.unit">
                <span class="unit-index">{{ item.index + 1 }}</span>
                <span
                  ><strong>{{
                    item.unit.unit_type === "page"
                      ? `第 ${item.unit.page_number} 页`
                      : formatTime(item.unit.pts_ms)
                  }}</strong
                  ><small
                    >{{ item.unit.width }} × {{ item.unit.height }} ·
                    {{ item.unit.objects.length }} 个对象</small
                  ></span
                >
              </template>
              <span v-else class="unit-jump">
                {{ item.jump === "start" ? "首单元" : "末单元" }} ({{ item.index + 1 }})
              </span>
            </button>
          </div>
          <div v-else class="empty">等待解析单元</div>
        </section>
      </div>
    </div>

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
            class="button secondary history-load-btn"
            title="载入此解析结果"
            @click="openHistory(row)"
          >
            载入<ArrowRight :size="12" />
          </button>
        </template>
      </DataTable>
    </section>
  </section>
</template>

<style scoped>
.parse-workbench {
  gap: 14px;
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
  gap: 18px;
  padding: 12px 0;
  border-bottom: 1px solid var(--line);
}
.parse-context-nav {
  display: flex;
  align-items: center;
  gap: 10px;
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
  flex: 1;
  max-width: 460px;
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
  grid-template-columns: minmax(360px, 1.25fr) minmax(280px, 0.75fr);
  gap: 16px;
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
  display: grid;
  align-content: start;
  gap: 14px;
}
.domain-parameters {
  display: grid;
  gap: 8px;
  padding-top: 4px;
  border-top: 1px solid var(--line);
}
.parameter-wide {
  grid-column: 1 / -1;
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
  display: grid;
  gap: 6px;
}
.input-controls label > span {
  font-size: 12px;
  font-weight: 700;
  color: var(--muted);
}
.file-picker small {
  overflow-wrap: anywhere;
}
.library-picker-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 34px;
  gap: 8px;
  align-items: end;
}
.library-picker-row .source-refresh {
  position: static;
}
.source-refresh {
  position: absolute;
  right: 7px;
  top: 25px;
}
.parameter-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.advanced-toggle {
  justify-self: start;
  display: inline-flex;
  align-items: center;
  gap: 6px;
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
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 340px);
  gap: 14px;
  margin-top: 14px;
  align-items: start;
}
.results-aside {
  display: grid;
  gap: 14px;
  min-width: 0;
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
  display: grid;
  gap: 3px;
}
.history-panel .history-title-group h2 {
  margin: 0;
}
.history-panel .panel-header p {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
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
</style>
