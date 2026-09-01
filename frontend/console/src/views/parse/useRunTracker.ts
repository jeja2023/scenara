import { type ComputedRef, type Ref } from "vue";
import { ApiError, api, apiStream, streamJsonEvents } from "../../api";
import type { MediaMode } from "../../composables/useDomainCatalog";
import type {
  MediaUnitResult,
  ResultEnvelope,
  ResultPage,
  Run,
} from "../../types";

const NETWORK_RETRY_DELAYS_MS = [250, 500, 1000, 2000] as const;

interface RunTrackerOptions {
  followLatestUnit: Ref<boolean>;
  formatTime: (milliseconds?: number | null) => string;
  loadStreamPreview: (sourceId: string) => Promise<void>;
  mode: Ref<MediaMode>;
  onError: (error: unknown) => void;
  onRefreshHistory: () => void;
  onRunChange: (run: Run) => void;
  prefersResultFramePreview: ComputedRef<boolean>;
  progressDetail: Ref<string>;
  result: Ref<ResultEnvelope | null>;
  run: Ref<Run | null>;
  selectedUnitIndex: Ref<number>;
  sourceId: Ref<string>;
}

interface EventSubscription {
  completed: Promise<boolean>;
  connected: Promise<boolean>;
}

function isTerminal(status: Run["status"]): boolean {
  return ["completed", "failed", "cancelled"].includes(status);
}

export function useRunTracker(options: RunTrackerOptions) {
  let pollGeneration = 0;
  let resultLoadSequence = 0;
  let sseAbort: AbortController | null = null;

  function preferredPreviewUnitIndex(units: MediaUnitResult[]): number {
    if (!options.prefersResultFramePreview.value)
      return Math.max(0, units.length - 1);
    for (let index = units.length - 1; index >= 0; index -= 1) {
      if (units[index]?.frame_artifact_id) return index;
    }
    return Math.max(0, units.length - 1);
  }

  function resetRunTracking(): void {
    pollGeneration += 1;
    resultLoadSequence += 1;
    sseAbort?.abort();
    sseAbort = null;
  }

  async function loadResult(
    runId: string,
    ignoreMissing = false,
  ): Promise<void> {
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
      options.result.value?.run_id === runId ? options.result.value.units : [];
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
    if (units.length > first.unit_total)
      units = units.slice(0, first.unit_total);
    const shouldFollowLatest =
      options.followLatestUnit.value || !options.result.value;
    options.result.value = { ...first.result, units };
    if (shouldFollowLatest && units.length) {
      options.selectedUnitIndex.value = preferredPreviewUnitIndex(units);
    } else if (options.selectedUnitIndex.value >= units.length) {
      options.selectedUnitIndex.value = Math.max(0, units.length - 1);
    }
    if (options.mode.value === "stream" && options.sourceId.value) {
      void options.loadStreamPreview(options.sourceId.value);
    }
  }

  function subscribeEvents(runId: string): EventSubscription {
    sseAbort?.abort();
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
            expected_units?: number | null;
            latest_pts_ms?: number | null;
            progress?: number | null;
            processed_units?: number;
            unit_count?: number;
            unit_total?: number;
          };
        }>(response)) {
          if (options.run.value && event.status && isTerminal(event.status)) {
            options.run.value = await api<Run>(
              `/api/v1/runs/${encodeURIComponent(runId)}`,
            );
            options.onRunChange(options.run.value);
            options.onRefreshHistory();
          } else if (
            options.run.value &&
            !isTerminal(options.run.value.status)
          ) {
            options.run.value = {
              ...options.run.value,
              status: event.status ?? options.run.value.status,
              progress: event.payload?.progress ?? options.run.value.progress,
            };
            options.onRunChange(options.run.value);
          }
          if (event.payload?.processed_units != null) {
            options.progressDetail.value =
              event.payload.expected_units == null
                ? `已处理 ${event.payload.processed_units} 个采样单元${event.payload.latest_pts_ms == null ? "" : ` · ${options.formatTime(event.payload.latest_pts_ms)}`}`
                : `${event.payload.processed_units} / ${event.payload.expected_units} 个采样单元`;
          }
          const availableUnitCount =
            event.event_type === "result.delta"
              ? event.payload?.unit_total
              : event.payload?.unit_count;
          if (
            ["result.partial", "result.delta"].includes(
              event.event_type ?? "",
            ) &&
            (availableUnitCount ?? 0) >
              (options.result.value?.units.length ?? 0)
          ) {
            void loadResult(runId, true).catch(() => undefined);
          }
        }
        resolveCompleted(true);
      } catch {
        resolveConnected(false);
        resolveCompleted(false);
      }
    })();
    return { connected, completed };
  }

  async function getRunWithNetworkRetry(
    runId: string,
    generation: number,
  ): Promise<Run | null> {
    for (let attempt = 0; ; attempt += 1) {
      if (generation !== pollGeneration) return null;
      try {
        return await api<Run>(`/api/v1/runs/${encodeURIComponent(runId)}`);
      } catch (caught) {
        if (generation !== pollGeneration) return null;
        const retryDelay = NETWORK_RETRY_DELAYS_MS[attempt];
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
    options.run.value = initial;
    options.onRunChange(initial);
    const subscription = subscribeEvents(initial.run_id);
    if (await subscription.connected) await subscription.completed;
    if (generation !== pollGeneration) return;
    while (
      generation === pollGeneration &&
      options.run.value &&
      !isTerminal(options.run.value.status)
    ) {
      await new Promise((resolve) => window.setTimeout(resolve, 500));
      if (generation !== pollGeneration) return;
      const refreshed = await getRunWithNetworkRetry(
        initial.run_id,
        generation,
      );
      if (!refreshed || !options.run.value) return;
      const progressChanged = refreshed.progress > options.run.value.progress;
      options.run.value = refreshed;
      options.onRunChange(refreshed);
      if (progressChanged)
        void loadResult(initial.run_id, true).catch(() => undefined);
    }
    if (sseAbort) {
      sseAbort.abort();
      sseAbort = null;
    }
    if (generation !== pollGeneration || !options.run.value) return;
    options.onRunChange(options.run.value);
    options.onRefreshHistory();
    if (["completed", "cancelled"].includes(options.run.value.status)) {
      await loadResult(initial.run_id, true);
    }
    if (options.mode.value === "stream" && options.run.value.next_run_id) {
      const next = await api<Run>(
        `/api/v1/runs/${encodeURIComponent(options.run.value.next_run_id)}`,
      );
      followRun(next);
    }
  }

  function followRun(initial: Run): void {
    void pollRun(initial).catch(options.onError);
  }

  return { followRun, loadResult, pollRun, resetRunTracking };
}
