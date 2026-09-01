import { computed, ref, type ComputedRef, type Ref } from "vue";
import type { MediaMode } from "../../composables/useDomainCatalog";
import type { PipelineParameterDefinition, Run } from "../../types";

type SampleStrategy = "interval" | "keyframe" | "scene_change" | "uniform";

const STRATEGY_LABELS: Record<SampleStrategy, string> = {
  interval: "固定间隔",
  keyframe: "关键帧",
  scene_change: "场景切换",
  uniform: "均匀分布",
};

interface ParseParameterOptions {
  mode: Ref<MediaMode>;
  parameterEntries: ComputedRef<[string, PipelineParameterDefinition][]>;
  pipelineParameterDefaults: Ref<Record<string, unknown>>;
  pipelineParameters: Ref<Record<string, unknown>>;
  selectedPipeline: ComputedRef<
    | { parameter_schema?: Record<string, PipelineParameterDefinition> }
    | null
    | undefined
  >;
  selectedRoi: Ref<[number, number, number, number] | null>;
}

function optionalNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function useParseParameters(options: ParseParameterOptions) {
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

  const samplingValid = computed(() => {
    const endMs = optionalNumber(sampleEndMs.value);
    const maxEdge = optionalNumber(frameMaxEdge.value);
    if (options.mode.value === "document") {
      return pageScale.value >= 0.5 && pageScale.value <= 4;
    }
    if (
      !Number.isInteger(sampleIntervalMs.value) ||
      sampleIntervalMs.value < 1 ||
      sampleIntervalMs.value > 3_600_000 ||
      !Number.isInteger(sampleStartMs.value) ||
      sampleStartMs.value < 0
    ) {
      return false;
    }
    if (
      endMs != null &&
      (!Number.isInteger(endMs) || endMs <= sampleStartMs.value)
    ) {
      return false;
    }
    if (options.mode.value === "stream" && endMs != null && endMs < 1_000)
      return false;
    if (
      sampleStrategy.value === "scene_change" &&
      (sceneChangeThreshold.value < 0.01 || sceneChangeThreshold.value > 1)
    ) {
      return false;
    }
    if (
      maxEdge != null &&
      (!Number.isInteger(maxEdge) || maxEdge < 64 || maxEdge > 8_192)
    ) {
      return false;
    }
    if (options.mode.value !== "stream") return true;
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

  const booleanParameterEntries = computed(() =>
    options.parameterEntries.value.filter(
      ([, definition]) => definition.control === "boolean",
    ),
  );
  const fieldParameterEntries = computed(() =>
    options.parameterEntries.value.filter(
      ([, definition]) => definition.control !== "boolean",
    ),
  );

  function isParameterWide(
    key: string,
    definition: PipelineParameterDefinition,
  ): boolean {
    if (
      ["custom_sensitive_words", "compliance_whitelist", "roi"].includes(key)
    ) {
      return true;
    }
    if (["language_hint", "min_score", "max_pages"].includes(key)) return false;
    return (
      definition.control === "text" &&
      Boolean(
        definition.placeholder?.includes("，") ||
        definition.placeholder?.includes(",") ||
        definition.placeholder?.includes("换行"),
      )
    );
  }

  const compactFieldEntriesCount = computed(
    () =>
      fieldParameterEntries.value.filter(
        ([key, definition]) => !isParameterWide(key, definition),
      ).length,
  );

  function formatOptionLabel(key: string, option: string): string {
    if (key === "language_hint") {
      return (
        {
          zh: "中文 / 中英 (zh)",
          en: "英文 (en)",
          ja: "日文 (ja)",
          ko: "韩文 (ko)",
          chinese_cht: "繁体中文 (cht)",
          fr: "法语 (fr)",
          de: "德语 (de)",
          ru: "俄语 (ru)",
          es: "西班牙语 (es)",
        }[option] ?? option
      );
    }
    return key === "sample_strategy"
      ? (STRATEGY_LABELS[option as SampleStrategy] ?? option)
      : option;
  }

  function samplingParameters(): Record<string, unknown> {
    const endMs = optionalNumber(sampleEndMs.value);
    const maxEdge = optionalNumber(frameMaxEdge.value);
    const parameters: Record<string, unknown> = {
      sample_interval_ms: sampleIntervalMs.value,
      sample_strategy: sampleStrategy.value,
      sample_start_ms: sampleStartMs.value,
      scene_change_threshold: sceneChangeThreshold.value,
    };
    if (
      options.mode.value !== "stream" &&
      endMs != null &&
      endMs > sampleStartMs.value
    ) {
      parameters.sample_end_ms = endMs;
    }
    if (maxEdge != null) parameters.frame_max_edge = maxEdge;
    if (options.mode.value === "stream") {
      if (endMs != null) parameters.stream_segment_duration_ms = endMs;
      parameters.max_reconnect_attempts = maxReconnectAttempts.value;
      parameters.connect_timeout_ms = connectTimeoutMs.value;
      parameters.read_timeout_ms = readTimeoutMs.value;
    }
    return parameters;
  }

  function runParameters(): Record<string, unknown> {
    const parameters =
      options.mode.value === "image"
        ? {}
        : options.mode.value === "document"
          ? { page_scale: pageScale.value }
          : samplingParameters();
    for (const [key, value] of Object.entries(
      options.pipelineParameters.value,
    )) {
      if (
        key !== "max_units" &&
        value !== undefined &&
        value !== null &&
        value !== "" &&
        JSON.stringify(value) !==
          JSON.stringify(options.pipelineParameterDefaults.value[key])
      ) {
        parameters[key] = value;
      }
    }
    if (options.selectedRoi.value) parameters.roi = options.selectedRoi.value;
    return parameters;
  }

  function applyRunParameters(parameters: Run["parameters"]): void {
    if (parameters.sample_interval_ms != null)
      sampleIntervalMs.value = Number(parameters.sample_interval_ms);
    if (parameters.sample_strategy != null)
      sampleStrategy.value = String(
        parameters.sample_strategy,
      ) as SampleStrategy;
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
      const values = Array.isArray(parameters.roi)
        ? parameters.roi
        : typeof parameters.roi === "string"
          ? parameters.roi.match(/[-+]?(?:\d*\.\d+|\d+)/g)
          : null;
      if (values?.length === 4) {
        options.selectedRoi.value = [
          Number(values[0]),
          Number(values[1]),
          Number(values[2]),
          Number(values[3]),
        ];
      }
    }
    const schema = options.selectedPipeline.value?.parameter_schema ?? {};
    for (const key of Object.keys(schema)) {
      if (parameters[key] !== undefined)
        options.pipelineParameters.value[key] = parameters[key];
    }
  }

  return {
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
  };
}
