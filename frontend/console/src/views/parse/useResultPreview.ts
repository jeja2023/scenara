import { computed, nextTick, ref, type ComputedRef, type Ref } from "vue";
import { apiImageDataUrl } from "../../api";
import type { MediaMode } from "../../composables/useDomainCatalog";
import type { ResultEnvelope, Run, VisionObject } from "../../types";

const FRAME_ALIGNMENT_TOLERANCE_SECONDS = 0.15;
const RESULT_FRAME_CACHE_LIMIT = 8;

interface ResultPreviewOptions {
  followLatestUnit: Ref<boolean>;
  handleVideoError: () => void;
  mediaUrl: Ref<string>;
  mode: Ref<MediaMode>;
  result: Ref<ResultEnvelope | null>;
  run: Ref<Run | null>;
  selectedUnit: ComputedRef<ResultEnvelope["units"][number] | undefined>;
  selectedUnitIndex: Ref<number>;
  serverPreviewUrl: Ref<string>;
  videoPlaybackFailed: Ref<boolean>;
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

export function useResultPreview(options: ResultPreviewOptions) {
  const videoElement = ref<HTMLVideoElement | null>(null);
  const overlayCanvas = ref<HTMLCanvasElement | null>(null);
  const resultFrameUrl = ref("");
  const resultFrameUnitId = ref("");
  const resultFrameLoading = ref(false);
  const resultFrameUnavailable = ref(false);
  const videoFrameUnitId = ref("");
  const videoPlaying = ref(false);
  const resultFrameCache = new Map<string, string>();
  let resultFrameLoadSequence = 0;

  const displayedMediaUrl = computed(
    () => options.serverPreviewUrl.value || options.mediaUrl.value,
  );
  const prefersResultFramePreview = computed(
    () =>
      options.mode.value === "document" ||
      options.mode.value === "stream" ||
      (options.mode.value === "video" &&
        (!options.mediaUrl.value || options.videoPlaybackFailed.value)),
  );
  const shouldUseResultFrame = computed(() =>
    Boolean(
      options.selectedUnit.value &&
      options.run.value?.run_id &&
      prefersResultFramePreview.value,
    ),
  );
  const overlayReady = computed(() => {
    const unit = options.selectedUnit.value;
    if (!unit?.objects.length) return false;
    if (options.mode.value === "image") return true;
    if (shouldUseResultFrame.value) {
      return (
        resultFrameUnitId.value === unit.unit_id &&
        Boolean(resultFrameUrl.value)
      );
    }
    return videoFrameUnitId.value === unit.unit_id;
  });
  const overlayStatus = computed(() => {
    if (!options.selectedUnit.value?.objects.length || overlayReady.value)
      return "";
    if (videoPlaying.value) return "";
    if (resultFrameLoading.value) return "正在同步结果帧";
    if (resultFrameUnavailable.value && shouldUseResultFrame.value) {
      return "结果帧暂不可用，已暂停叠加标注";
    }
    return options.mode.value === "video" ? "正在定位结果帧" : "正在加载结果帧";
  });

  function clearOverlay(): void {
    const canvas = overlayCanvas.value;
    const context = canvas?.getContext("2d");
    if (canvas && context) context.clearRect(0, 0, canvas.width, canvas.height);
  }

  function setOverlayCanvas(element: unknown): void {
    overlayCanvas.value = element instanceof HTMLCanvasElement ? element : null;
  }

  function setVideoElement(element: unknown): void {
    videoElement.value = element instanceof HTMLVideoElement ? element : null;
  }

  function resetResultPreview(): void {
    resultFrameLoadSequence += 1;
    resultFrameUrl.value = "";
    resultFrameUnitId.value = "";
    resultFrameLoading.value = false;
    resultFrameUnavailable.value = false;
    videoFrameUnitId.value = "";
    videoPlaying.value = false;
    resultFrameCache.clear();
    clearOverlay();
  }

  function cacheResultFrame(key: string, value: string): void {
    resultFrameCache.delete(key);
    resultFrameCache.set(key, value);
    while (resultFrameCache.size > RESULT_FRAME_CACHE_LIMIT) {
      const oldest = resultFrameCache.keys().next().value;
      if (oldest === undefined) return;
      resultFrameCache.delete(oldest);
    }
  }

  function resultFramePath(runId: string, artifactId: string): string {
    return `/api/v1/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}`;
  }

  function preferredPreviewUnitIndex(): number {
    const units = options.result.value?.units ?? [];
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
    const unit = options.selectedUnit.value;
    if (
      shouldUseResultFrame.value ||
      options.mode.value !== "video" ||
      !options.mediaUrl.value ||
      options.videoPlaybackFailed.value ||
      !video ||
      unit?.pts_ms == null ||
      videoPlaying.value ||
      video.readyState < HTMLMediaElement.HAVE_METADATA
    ) {
      return;
    }
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
      // Metadata can arrive after the selected media unit; the seek handler retries.
    }
  }

  function handleVideoSeeked(): void {
    const video = videoElement.value;
    const unit = options.selectedUnit.value;
    if (!video || !unit || unit.pts_ms == null) return;
    if (
      Math.abs(video.currentTime - unit.pts_ms / 1000) <=
      FRAME_ALIGNMENT_TOLERANCE_SECONDS
    ) {
      videoFrameUnitId.value = unit.unit_id;
      drawOverlay();
      return;
    }
    syncVideoToSelectedUnit();
  }

  function handleVideoPlay(): void {
    videoPlaying.value = true;
    videoFrameUnitId.value = "";
    clearOverlay();
  }

  function handleVideoPlaybackError(): void {
    options.handleVideoError();
    if (!options.result.value?.units.length) return;
    const previewIndex = preferredPreviewUnitIndex();
    if (previewIndex !== options.selectedUnitIndex.value) {
      options.selectedUnitIndex.value = previewIndex;
      options.followLatestUnit.value = true;
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
      resultFrameUnitId.value === options.selectedUnit.value?.unit_id
    ) {
      drawOverlay();
    }
  }

  async function loadSelectedResultFrame(): Promise<void> {
    const sequence = ++resultFrameLoadSequence;
    const unit = options.selectedUnit.value;
    const runId = options.run.value?.run_id;
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
    if (!unit.frame_artifact_id) {
      resultFrameUnavailable.value = true;
      return;
    }
    const cacheKey = `${runId}:${unit.frame_artifact_id}`;
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
      const dataUrl = await apiImageDataUrl(
        resultFramePath(runId, unit.frame_artifact_id),
      );
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
      if (sequence === resultFrameLoadSequence)
        resultFrameLoading.value = false;
    }
  }

  function syncSelectedMediaFrame(): void {
    void loadSelectedResultFrame();
  }

  function formatOverlayBadge(item: VisionObject): string {
    const score = item.score != null ? ` ${item.score.toFixed(2)}` : "";
    const attributes = item.attributes as Record<string, unknown> | undefined;
    if (attributes?.action_label) return `${attributes.action_label}${score}`;
    if (attributes?.character_name && attributes?.style_label) {
      return `${attributes.character_name} · ${attributes.style_label}${score}`;
    }
    if (attributes?.style_label) return `${attributes.style_label}${score}`;
    if (attributes?.character_name)
      return `${attributes.character_name}${score}`;
    if (attributes?.accessory_label)
      return `${attributes.accessory_label}${score}`;
    if (attributes?.text) {
      const text = String(attributes.text).trim();
      return `${text.slice(0, 10)}${text.length > 10 ? "…" : ""}${score}`;
    }
    return item.object_type !== "person"
      ? `${item.object_type}${score}`
      : score.trim() || "目标";
  }

  function drawOverlay(): void {
    const canvas = overlayCanvas.value;
    const unit = options.selectedUnit.value;
    if (!canvas || !unit || !overlayReady.value) {
      clearOverlay();
      return;
    }
    canvas.width = unit.width;
    canvas.height = unit.height;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    const stroke = Math.max(1.5, Math.min(unit.width, unit.height) / 320);
    context.lineWidth = stroke;
    context.font = `${Math.max(11, Math.min(unit.width, unit.height) / 42)}px system-ui, sans-serif`;
    context.textBaseline = "bottom";
    for (const item of unit.objects) {
      const color = OVERLAY_COLORS[item.object_type] ?? "#4b7bd4";
      context.strokeStyle = color;
      context.fillStyle = color;
      if (item.polygon?.length && item.polygon.length >= 3) {
        context.beginPath();
        item.polygon.forEach((point, index) => {
          if (index === 0) context.moveTo(point.x, point.y);
          else context.lineTo(point.x, point.y);
        });
        context.closePath();
        context.stroke();
      }
      if (!item.bbox) continue;
      context.strokeRect(
        item.bbox.x,
        item.bbox.y,
        item.bbox.width,
        item.bbox.height,
      );
      const text = formatOverlayBadge(item);
      const width = context.measureText(text).width + 8;
      const height = Math.max(16, stroke * 9.5);
      context.globalAlpha = 0.88;
      context.fillRect(
        item.bbox.x,
        Math.max(height, item.bbox.y) - height,
        width,
        height,
      );
      context.globalAlpha = 1;
      context.fillStyle = "#ffffff";
      context.fillText(
        text,
        item.bbox.x + 4,
        Math.max(height, item.bbox.y) - 3,
      );
      context.fillStyle = color;
    }
  }

  return {
    clearOverlay,
    displayedMediaUrl,
    drawOverlay,
    handleResultFrameLoaded,
    handleVideoPause,
    handleVideoPlaybackError,
    handleVideoPlay,
    handleVideoSeeked,
    overlayCanvas,
    overlayReady,
    overlayStatus,
    prefersResultFramePreview,
    resetResultPreview,
    resultFrameLoading,
    resultFrameUnavailable,
    resultFrameUrl,
    shouldUseResultFrame,
    setOverlayCanvas,
    setVideoElement,
    syncSelectedMediaFrame,
    syncVideoToSelectedUnit,
    videoElement,
    videoPlaying,
  };
}
