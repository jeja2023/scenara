import { computed, ref, type Ref } from "vue";

import { api, userFacingError } from "../api";
import { labelDomain } from "../labels";
import type {
  Domain,
  DomainManifest,
  MediaAsset,
  MediaKind,
  MediaSource,
  Pipeline,
  PipelineParameterDefinition,
} from "../types";

export type MediaMode = "image" | "video" | "document" | "stream";

interface DomainCatalogOptions {
  domain: Ref<Domain>;
  mode: Ref<MediaMode>;
  domainSearch: Ref<string>;
  assetId: Ref<string>;
  sourceId: Ref<string>;
  pipelineId: Ref<string>;
  pipelineParameters: Ref<Record<string, unknown>>;
  pipelineParameterDefaults: Ref<Record<string, unknown>>;
  assets: Ref<MediaAsset[]>;
  sources: Ref<MediaSource[]>;
  loadingSources: Ref<boolean>;
  error: Ref<string>;
  onModeChange: (mode: MediaMode) => void;
}

export function useDomainCatalog(options: DomainCatalogOptions) {
  const domainManifests = ref<DomainManifest[]>([]);
  const pipelines = ref<Pipeline[]>([]);

  const domainPipelines = computed(() =>
    pipelines.value.filter(
      (item) =>
        item.domain === options.domain.value && item.status === "active",
    ),
  );

  const availableDomains = computed(() => {
    const known = new Map(
      domainManifests.value.map((item) => [item.domain_id, item]),
    );
    for (const item of pipelines.value) {
      if (!known.has(item.domain)) {
        known.set(item.domain, {
          domain_id: item.domain,
          display_name: labelDomain(item.domain),
          schema_version: "-",
          console_route: `/parse?domain=${encodeURIComponent(item.domain)}`,
          capabilities: [],
        });
      }
    }
    return [...known.values()].sort(
      (left, right) =>
        (left.navigation_order ?? 100) - (right.navigation_order ?? 100) ||
        left.display_name.localeCompare(right.display_name),
    );
  });

  const filteredDomains = computed(() => {
    const query = options.domainSearch.value.trim().toLowerCase();
    if (!query) return availableDomains.value;
    return availableDomains.value.filter((item) =>
      `${item.display_name} ${item.domain_id}`.toLowerCase().includes(query),
    );
  });

  const selectedDomainManifest = computed(
    () =>
      availableDomains.value.find(
        (item) => item.domain_id === options.domain.value,
      ) ?? null,
  );

  const supportedMediaKinds = computed<MediaKind[]>(() =>
    selectedDomainManifest.value?.supported_media_kinds?.length
      ? selectedDomainManifest.value.supported_media_kinds
      : ["image", "video", "document", "stream"],
  );

  const selectedPipeline = computed(
    () =>
      domainPipelines.value.find(
        (item) => item.pipeline_id === options.pipelineId.value,
      ) ??
      domainPipelines.value[0] ??
      null,
  );

  const BUILTIN_PLATFORM_PARAMS = new Set([
    "roi",
    "sample_strategy",
    "sample_interval_ms",
    "scene_change_threshold",
    "frame_max_edge",
    "sample_start_ms",
    "sample_end_ms",
    "max_reconnect_attempts",
    "connect_timeout_ms",
    "read_timeout_ms",
    "page_scale",
  ]);

  const parameterEntries = computed(
    () =>
      Object.entries(selectedPipeline.value?.parameter_schema ?? {}).filter(
        ([key, definition]) =>
          !BUILTIN_PLATFORM_PARAMS.has(key) &&
          (!definition.media_kinds?.length ||
            definition.media_kinds.includes(options.mode.value)),
      ) as Array<[string, PipelineParameterDefinition]>,
  );

  const pipeline = computed(
    () =>
      selectedPipeline.value?.pipeline_id ||
      options.pipelineId.value ||
      selectedDomainManifest.value?.default_pipeline_id ||
      "",
  );

  const filteredAssets = computed(() =>
    options.assets.value.filter(
      (item) =>
        item.kind === options.mode.value &&
        (!item.domain || item.domain === options.domain.value),
    ),
  );

  const selectedAsset = computed(
    () =>
      options.assets.value.find(
        (item) => item.asset_id === options.assetId.value,
      ) ?? null,
  );

  const selectedSource = computed(
    () =>
      options.sources.value.find(
        (item) => item.source_id === options.sourceId.value,
      ) ?? null,
  );

  function syncPipelineParameterDefaults(): void {
    const schema = selectedPipeline.value?.parameter_schema ?? {};
    const next: Record<string, unknown> = {};
    const defaults: Record<string, unknown> = {};
    for (const [key, definition] of Object.entries(schema)) {
      defaults[key] = definition.default;
      next[key] =
        options.pipelineParameters.value[key] !== undefined
          ? options.pipelineParameters.value[key]
          : definition.default;
    }
    options.pipelineParameters.value = next;
    options.pipelineParameterDefaults.value = defaults;
  }

  function syncPipelineSelection(preferred = options.pipelineId.value): void {
    const preferredId =
      preferred || selectedDomainManifest.value?.default_pipeline_id || "";
    const match = domainPipelines.value.find(
      (item) => item.pipeline_id === preferredId,
    );
    options.pipelineId.value =
      match?.pipeline_id ?? domainPipelines.value[0]?.pipeline_id ?? "";
    syncPipelineParameterDefaults();
  }

  function ensureSupportedMode(): void {
    if (supportedMediaKinds.value.includes(options.mode.value)) return;
    const next = supportedMediaKinds.value[0];
    if (next) options.onModeChange(next);
  }

  async function refreshSources(): Promise<void> {
    options.loadingSources.value = true;
    try {
      const page = await api<{ items: MediaSource[] }>(
        "/api/v1/media/sources?limit=200",
      );
      options.sources.value = Array.isArray(page?.items) ? page.items : [];
    } catch (caught) {
      options.error.value = userFacingError(
        caught,
        "视频流来源加载失败，请稍后重试",
      );
    } finally {
      options.loadingSources.value = false;
    }
  }

  async function refreshWorkspaceResources(): Promise<void> {
    options.loadingSources.value = true;
    try {
      const [assetPage, sourcePage, pipelineRows, manifestRows] =
        await Promise.all([
          api<{ items: MediaAsset[] }>("/api/v1/media/assets?limit=200"),
          api<{ items: MediaSource[] }>("/api/v1/media/sources?limit=200"),
          api<Pipeline[]>("/api/v1/pipelines"),
          api<DomainManifest[]>("/api/v1/domains"),
        ]);
      options.assets.value = Array.isArray(assetPage?.items)
        ? assetPage.items
        : [];
      options.sources.value = Array.isArray(sourcePage?.items)
        ? sourcePage.items
        : [];
      pipelines.value = Array.isArray(pipelineRows) ? pipelineRows : [];
      domainManifests.value = Array.isArray(manifestRows) ? manifestRows : [];
      const currentDomain = availableDomains.value.find(
        (item) => item.domain_id === options.domain.value,
      );
      if (!currentDomain)
        options.domain.value =
          availableDomains.value[0]?.domain_id ?? options.domain.value;
      syncPipelineSelection();
      ensureSupportedMode();
    } catch (caught) {
      options.error.value = userFacingError(
        caught,
        "解析资源加载失败，请稍后重试",
      );
    } finally {
      options.loadingSources.value = false;
    }
  }

  return {
    domainManifests,
    pipelines,
    domainPipelines,
    availableDomains,
    filteredDomains,
    selectedDomainManifest,
    supportedMediaKinds,
    selectedPipeline,
    parameterEntries,
    pipeline,
    filteredAssets,
    selectedAsset,
    selectedSource,
    refreshSources,
    refreshWorkspaceResources,
    syncPipelineSelection,
    syncPipelineParameterDefaults,
    ensureSupportedMode,
  };
}
