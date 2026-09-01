<script setup lang="ts">
import { Crop, FileText, Info, Radio, X } from "@lucide/vue";
import type { CSSProperties } from "vue";
import type { MediaMode } from "../../composables/useDomainCatalog";
import type { MediaAsset, MediaSource } from "../../types";

defineProps<{
  displayedMediaUrl: string;
  file: File | null;
  handleImageError: () => void;
  handleResultFrameLoaded: () => void;
  handleVideoLoadedData: () => void;
  handleVideoPause: () => void;
  handleVideoPlaybackError: () => void;
  handleVideoPlay: () => void;
  handleVideoSeeked: () => void;
  hasResult: boolean;
  isDrawingRoi: boolean;
  mediaUrl: string;
  mode: MediaMode;
  onStageResize: () => void;
  overlayReady: boolean;
  overlayStatus: string;
  resultFrameUrl: string;
  roiBoxStyle: CSSProperties | null;
  selectedAsset: MediaAsset | null;
  selectedRoi: [number, number, number, number] | null;
  selectedSource: MediaSource | null;
  serverPreviewUrl: string;
  setMediaStage: (element: unknown) => void;
  setOverlayCanvas: (element: unknown) => void;
  setVideoElement: (element: unknown) => void;
  shouldUseResultFrame: boolean;
  syncVideoToSelectedUnit: () => void;
  sourceName: string;
  sourceUrl: string;
  streamPreviewUrl: string;
  videoPlaying: boolean;
  videoPlaybackFailed: boolean;
}>();

const emit = defineEmits<{
  clearRoi: [];
  mouseDown: [event: MouseEvent];
  toggleRoi: [];
}>();
</script>

<template>
  <div class="media-preview-column">
    <div class="ocr-roi-toolbar">
      <div class="roi-toolbar-left">
        <button
          type="button"
          class="button small"
          :class="isDrawingRoi ? 'primary' : 'secondary'"
          @click="emit('toggleRoi')"
        >
          <Crop :size="13" />
          {{
            isDrawingRoi
              ? "正在拖拽圈选 (松开完成)"
              : selectedRoi
                ? "重新圈选区域"
                : "圈选识别区域"
          }}
        </button>
        <span v-if="selectedRoi" class="roi-badge">
          区域坐标：[{{
            selectedRoi.map((value) => value.toFixed(3)).join(", ")
          }}]
        </span>
      </div>
      <div v-if="selectedRoi" class="roi-toolbar-right">
        <button
          type="button"
          class="button small ghost text-danger"
          title="清除圈选区域，恢复全画幅识别"
          @click="emit('clearRoi')"
        >
          <X :size="13" />清除区域
        </button>
      </div>
    </div>

    <div
      :ref="setMediaStage"
      class="media-stage"
      :class="{ 'roi-drawing-mode': isDrawingRoi }"
      @mousedown="emit('mouseDown', $event)"
    >
      <div v-if="isDrawingRoi" class="roi-drawing-layer" />
      <img
        v-if="mode === 'image' && displayedMediaUrl"
        :src="displayedMediaUrl"
        alt="待解析图片"
        draggable="false"
        @load="onStageResize"
        @error="handleImageError"
      />
      <template
        v-else-if="mode === 'video' && (displayedMediaUrl || resultFrameUrl)"
      >
        <img
          v-if="shouldUseResultFrame && resultFrameUrl"
          :src="resultFrameUrl"
          alt="当前解析帧"
          @load="handleResultFrameLoaded"
        />
        <img
          v-else-if="serverPreviewUrl && !hasResult && !videoPlaying"
          :src="serverPreviewUrl"
          alt="视频首帧预览"
          draggable="false"
          @load="onStageResize"
        />
        <video
          v-else-if="mediaUrl && !videoPlaybackFailed"
          :ref="setVideoElement"
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
      <template v-else-if="mode === 'document' && (file || selectedAsset)">
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
            selectedSource?.masked_url || sourceUrl || "登记或选择一个视频流源"
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
        :ref="setOverlayCanvas"
        class="overlay"
        aria-hidden="true"
      />
      <div v-if="roiBoxStyle" class="roi-overlay-box" :style="roiBoxStyle">
        <span class="roi-box-label">识别区域</span>
      </div>
    </div>
    <div v-if="overlayStatus" class="overlay-status" aria-live="polite">
      <Info :size="14" /><span>{{ overlayStatus }}</span>
    </div>
  </div>
</template>

<style scoped>
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
