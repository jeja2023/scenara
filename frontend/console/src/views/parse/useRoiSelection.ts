import { ref, type ComputedRef, type Ref } from "vue";
import type { MediaUnitResult } from "../../types";

type Point = { x: number; y: number };

interface MediaBounds {
  renderHeight: number;
  renderLeft: number;
  renderTop: number;
  renderWidth: number;
}

function boundedRatio(value: number): number {
  return Math.max(0, Math.min(1, value));
}

export function useRoiSelection(
  pipelineParameters: Ref<Record<string, unknown>>,
  selectedUnit: ComputedRef<MediaUnitResult | undefined>,
) {
  const mediaStageRef = ref<HTMLElement | null>(null);
  const stageRectVersion = ref(0);
  const isDrawingRoi = ref(false);
  const roiStart = ref<Point | null>(null);
  const roiCurrent = ref<Point | null>(null);
  const selectedRoi = ref<[number, number, number, number] | null>(null);

  function onStageResize(): void {
    stageRectVersion.value += 1;
  }

  function setMediaStage(element: unknown): void {
    mediaStageRef.value = element instanceof HTMLElement ? element : null;
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
    delete pipelineParameters.value.roi;
  }

  function getMediaContentBounds(stageEl: HTMLElement): MediaBounds {
    const stage = stageEl.getBoundingClientRect();
    const image = stageEl.querySelector("img") as HTMLImageElement | null;
    const video = stageEl.querySelector("video") as HTMLVideoElement | null;
    const naturalWidth =
      image && image.naturalWidth > 0
        ? image.naturalWidth
        : video && video.videoWidth > 0
          ? video.videoWidth
          : selectedUnit.value?.width || 0;
    const naturalHeight =
      image && image.naturalHeight > 0
        ? image.naturalHeight
        : video && video.videoHeight > 0
          ? video.videoHeight
          : selectedUnit.value?.height || 0;

    if (
      !naturalWidth ||
      !naturalHeight ||
      stage.width <= 0 ||
      stage.height <= 0
    ) {
      return {
        renderLeft: 0,
        renderTop: 0,
        renderWidth: stage.width || 1,
        renderHeight: stage.height || 1,
      };
    }

    const stageRatio = stage.width / stage.height;
    const mediaRatio = naturalWidth / naturalHeight;
    if (mediaRatio > stageRatio) {
      const renderHeight = stage.width / mediaRatio;
      return {
        renderLeft: 0,
        renderTop: (stage.height - renderHeight) / 2,
        renderWidth: stage.width,
        renderHeight,
      };
    }

    const renderWidth = stage.height * mediaRatio;
    return {
      renderLeft: (stage.width - renderWidth) / 2,
      renderTop: 0,
      renderWidth,
      renderHeight: stage.height,
    };
  }

  function toPoint(event: MouseEvent, stageEl: HTMLElement): Point {
    const stage = stageEl.getBoundingClientRect();
    const bounds = getMediaContentBounds(stageEl);
    return {
      x: boundedRatio(
        (event.clientX - stage.left - bounds.renderLeft) / bounds.renderWidth,
      ),
      y: boundedRatio(
        (event.clientY - stage.top - bounds.renderTop) / bounds.renderHeight,
      ),
    };
  }

  function handleRoiMouseDown(event: MouseEvent): void {
    if (!isDrawingRoi.value || event.button !== 0 || !mediaStageRef.value)
      return;
    event.preventDefault();
    event.stopPropagation();
    const point = toPoint(event, mediaStageRef.value);
    roiStart.value = point;
    roiCurrent.value = point;
    window.addEventListener("mousemove", handleRoiMouseMove);
    window.addEventListener("mouseup", handleRoiMouseUp);
  }

  function handleRoiMouseMove(event: MouseEvent): void {
    if (!isDrawingRoi.value || !roiStart.value || !mediaStageRef.value) return;
    event.preventDefault();
    roiCurrent.value = toPoint(event, mediaStageRef.value);
  }

  function handleRoiMouseUp(event?: MouseEvent): void {
    window.removeEventListener("mousemove", handleRoiMouseMove);
    window.removeEventListener("mouseup", handleRoiMouseUp);
    if (!isDrawingRoi.value || !roiStart.value) return;
    if (event && mediaStageRef.value) {
      roiCurrent.value = toPoint(event, mediaStageRef.value);
    }
    const current = roiCurrent.value || roiStart.value;
    const minX = boundedRatio(Math.min(roiStart.value.x, current.x));
    const maxX = boundedRatio(Math.max(roiStart.value.x, current.x));
    const minY = boundedRatio(Math.min(roiStart.value.y, current.y));
    const maxY = boundedRatio(Math.max(roiStart.value.y, current.y));
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

  function disposeRoiSelection(): void {
    window.removeEventListener("mousemove", handleRoiMouseMove);
    window.removeEventListener("mouseup", handleRoiMouseUp);
  }

  return {
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
  };
}
