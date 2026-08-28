<script setup lang="ts">
import {
  ImageOff,
  Loader2,
  RotateCcw,
  Target,
  X,
  ZoomIn,
  ZoomOut,
} from "@lucide/vue";
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";

import { apiImageDataUrl, userFacingError } from "../api";
import { labelObjectType } from "../labels";
import type { MediaUnitResult, VisionObject } from "../types";

const props = defineProps<{
  /** 产出该结果的运行标识。 */
  runId: string;
  /** 当前查看的分析单元；为空时不展示任何裁剪图。 */
  unit: MediaUnitResult | null;
  /** 单元没有帧大图时使用的回退大图地址（例如本地选择的原图）。 */
  fallbackLargeUrl?: string;
}>();

const images = ref(new Map<string, string>());
const pending = ref(new Set<string>());
const failed = ref(new Set<string>());
const error = ref("");
const activeIndex = ref(-1);
const largeUrl = ref("");
const largeLoading = ref(false);
const lightboxElement = ref<HTMLElement | null>(null);
const stageElement = ref<HTMLElement | null>(null);

// 缩放与平移状态
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 6.0;
const ZOOM_STEP = 0.3;
const zoom = ref(1.0);
const panX = ref(0);
const panY = ref(0);
const isDragging = ref(false);
const dragStartX = ref(0);
const dragStartY = ref(0);
const dragStartPanX = ref(0);
const dragStartPanY = ref(0);

const transformStyle = computed(() => ({
  transform: `translate(${panX.value}px, ${panY.value}px) scale(${zoom.value})`,
  transformOrigin: "center center",
  transition: isDragging.value ? "none" : "transform 0.15s cubic-bezier(0.2, 0, 0, 1)",
}));

function resetZoom(): void {
  zoom.value = 1.0;
  panX.value = 0;
  panY.value = 0;
}

function setZoom(newZoom: number, originX?: number, originY?: number): void {
  const oldZoom = zoom.value;
  const clamped = Math.min(
    MAX_ZOOM,
    Math.max(MIN_ZOOM, Math.round(newZoom * 100) / 100),
  );
  if (clamped === oldZoom) return;

  if (originX !== undefined && originY !== undefined) {
    const ratio = clamped / oldZoom;
    panX.value = originX - (originX - panX.value) * ratio;
    panY.value = originY - (originY - panY.value) * ratio;
  } else {
    const ratio = clamped / oldZoom;
    panX.value = panX.value * ratio;
    panY.value = panY.value * ratio;
  }
  zoom.value = clamped;
}

function zoomIn(): void {
  setZoom(zoom.value + ZOOM_STEP);
}

function zoomOut(): void {
  setZoom(zoom.value - ZOOM_STEP);
}

function focusTarget(): void {
  const obj = activeObject.value;
  const unit = props.unit;
  if (!obj?.bbox || !unit || unit.width <= 0 || unit.height <= 0) {
    setZoom(2.2);
    return;
  }
  const targetZoom = 2.6;
  const normX = (obj.bbox.x + obj.bbox.width / 2) / unit.width;
  const normY = (obj.bbox.y + obj.bbox.height / 2) / unit.height;
  const rect = stageElement.value?.getBoundingClientRect();
  const w = rect?.width ?? 800;
  const h = rect?.height ?? 450;
  zoom.value = targetZoom;
  panX.value = (0.5 - normX) * w * targetZoom;
  panY.value = (0.5 - normY) * h * targetZoom;
}

function onWheel(event: WheelEvent): void {
  const stageEl = stageElement.value;
  if (!stageEl) return;
  const rect = stageEl.getBoundingClientRect();
  const mouseX = event.clientX - (rect.left + rect.width / 2);
  const mouseY = event.clientY - (rect.top + rect.height / 2);
  const delta = event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP;
  setZoom(zoom.value + delta, mouseX, mouseY);
}

function onMouseDown(event: MouseEvent): void {
  if (event.button !== 0) return;
  isDragging.value = true;
  dragStartX.value = event.clientX;
  dragStartY.value = event.clientY;
  dragStartPanX.value = panX.value;
  dragStartPanY.value = panY.value;
  window.addEventListener("mousemove", onWindowMouseMove);
  window.addEventListener("mouseup", onWindowMouseUp);
}

function onWindowMouseMove(event: MouseEvent): void {
  if (!isDragging.value) return;
  panX.value = dragStartPanX.value + (event.clientX - dragStartX.value);
  panY.value = dragStartPanY.value + (event.clientY - dragStartY.value);
}

function onWindowMouseUp(): void {
  if (!isDragging.value) return;
  isDragging.value = false;
  window.removeEventListener("mousemove", onWindowMouseMove);
  window.removeEventListener("mouseup", onWindowMouseUp);
}

function onDoubleClick(): void {
  if (zoom.value > 1.15) {
    resetZoom();
  } else {
    focusTarget();
  }
}

interface CropCard {
  object: VisionObject;
  artifactId: string;
  src: string;
  loading: boolean;
}

const croppedObjects = computed<VisionObject[]>(() =>
  (props.unit?.objects ?? []).filter((item) => !!item.crop_artifact_id),
);
const cropCards = computed<CropCard[]>(() =>
  croppedObjects.value.map((object) => {
    const artifactId = object.crop_artifact_id ?? "";
    return {
      object,
      artifactId,
      src: images.value.get(artifactId) ?? "",
      loading: pending.value.has(artifactId),
    };
  }),
);
const objectCount = computed(() => props.unit?.objects.length ?? 0);
const activeObject = computed<VisionObject | null>(
  () => croppedObjects.value[activeIndex.value] ?? null,
);
const lightboxOpen = computed(
  () => activeIndex.value >= 0 && !!activeObject.value,
);
const unitAspectRatio = computed(() => {
  const unit = props.unit;
  if (!unit || unit.width <= 0 || unit.height <= 0) return "16 / 9";
  return `${unit.width} / ${unit.height}`;
});

/** 把边框换算成相对单元尺寸的百分比，用于在大图上精确高亮。 */
const highlightStyle = computed(() => {
  const unit = props.unit;
  const bbox = activeObject.value?.bbox;
  if (!unit || !bbox || unit.width <= 0 || unit.height <= 0) return null;
  return {
    left: `${(bbox.x / unit.width) * 100}%`,
    top: `${(bbox.y / unit.height) * 100}%`,
    width: `${(bbox.width / unit.width) * 100}%`,
    height: `${(bbox.height / unit.height) * 100}%`,
  };
});

function artifactPath(artifactId: string): string {
  return `/api/v1/runs/${encodeURIComponent(props.runId)}/artifacts/${encodeURIComponent(artifactId)}`;
}

async function loadArtifact(artifactId: string): Promise<string> {
  const cached = images.value.get(artifactId);
  if (cached) return cached;
  pending.value = new Set(pending.value).add(artifactId);
  try {
    const dataUrl = await apiImageDataUrl(artifactPath(artifactId));
    images.value = new Map(images.value).set(artifactId, dataUrl);
    return dataUrl;
  } catch (caught) {
    failed.value = new Set(failed.value).add(artifactId);
    error.value = userFacingError(caught, "特征图片加载失败，请稍后重试");
    return "";
  } finally {
    const next = new Set(pending.value);
    next.delete(artifactId);
    pending.value = next;
  }
}

function loadCrops(): void {
  for (const item of croppedObjects.value) {
    const artifactId = item.crop_artifact_id;
    if (!artifactId) continue;
    if (
      images.value.has(artifactId) ||
      pending.value.has(artifactId) ||
      failed.value.has(artifactId)
    )
      continue;
    void loadArtifact(artifactId);
  }
}

async function openLightbox(index: number): Promise<void> {
  activeIndex.value = index;
  resetZoom();
  void nextTick(() => lightboxElement.value?.focus());
  const frameArtifactId = props.unit?.frame_artifact_id;
  if (!frameArtifactId) {
    largeUrl.value = props.fallbackLargeUrl ?? "";
    return;
  }
  const cached = images.value.get(frameArtifactId);
  if (cached) {
    largeUrl.value = cached;
    return;
  }
  largeLoading.value = true;
  try {
    largeUrl.value =
      (await loadArtifact(frameArtifactId)) || (props.fallbackLargeUrl ?? "");
  } finally {
    largeLoading.value = false;
  }
}

function closeLightbox(): void {
  activeIndex.value = -1;
  resetZoom();
}

function step(offset: number): void {
  const total = croppedObjects.value.length;
  if (total < 2) return;
  activeIndex.value = (activeIndex.value + offset + total) % total;
  resetZoom();
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") closeLightbox();
  else if (event.key === "ArrowLeft") step(-1);
  else if (event.key === "ArrowRight") step(1);
  else if (event.key === "+" || event.key === "=") zoomIn();
  else if (event.key === "-" || event.key === "_") zoomOut();
  else if (event.key === "0") resetZoom();
  else if (event.key === "f" || event.key === "F") focusTarget();
  else return;
  event.preventDefault();
}

function reset(): void {
  images.value = new Map();
  pending.value = new Set();
  failed.value = new Set();
  error.value = "";
  activeIndex.value = -1;
  largeUrl.value = "";
  resetZoom();
}

function getCropTag(obj: VisionObject) {
  const attrs = (obj.attributes ?? {}) as Record<string, unknown>;
  const isCosplay =
    obj.object_type === "cosplay" ||
    Boolean(attrs.character_name) ||
    Boolean(attrs.is_cosplay);

  if (isCosplay) {
    const charName = String(attrs.character_name || "二次元Cosplay");
    return {
      type: "cosplay",
      badgeText: "二次元 Cosplay",
      mainTitle: charName,
      subTitle: attrs.series_name
        ? String(attrs.series_name)
        : attrs.style_label
          ? String(attrs.style_label)
          : "Cosplay角色",
      badgeClass: "tag-cosplay",
    };
  }

  if (obj.object_type === "clothing" || attrs.style_label) {
    const styleLabel = String(attrs.style_label || "日常休闲");
    const isSpecial = [
      "汉服",
      "洛丽塔",
      "JK制服",
      "女仆装",
      "哥特风",
      "旗袍",
      "和服",
    ].includes(styleLabel);
    return {
      type: isSpecial ? "special-fashion" : "casual-fashion",
      badgeText: isSpecial ? "特色服饰" : "日常服饰",
      mainTitle: styleLabel,
      subTitle: attrs.dominant_color
        ? `色调 · ${attrs.dominant_color}`
        : "服装风格",
      badgeClass: isSpecial ? "tag-special" : "tag-casual",
    };
  }

  if (obj.object_type === "accessory" || attrs.accessory_label) {
    return {
      type: "accessory",
      badgeText: "配饰",
      mainTitle: String(attrs.accessory_label || "服饰配饰"),
      subTitle: attrs.material ? String(attrs.material) : "饰品",
      badgeClass: "tag-accessory",
    };
  }

  if (obj.object_type === "action" || attrs.action_label) {
    return {
      type: "action",
      badgeText: "动作",
      mainTitle: String(attrs.action_label || "行为动作"),
      subTitle: attrs.intensity ? `强度 · ${attrs.intensity}` : "时序动作",
      badgeClass: "tag-action",
    };
  }

  if (obj.object_type === "text" || attrs.text) {
    const txt = String(attrs.text).trim();
    return {
      type: "text",
      badgeText: "文本",
      mainTitle: txt.slice(0, 12) + (txt.length > 12 ? "…" : ""),
      subTitle: "OCR识别",
      badgeClass: "tag-text",
    };
  }

  return {
    type: "default",
    badgeText: labelObjectType(obj.object_type),
    mainTitle: labelObjectType(obj.object_type),
    subTitle: "",
    badgeClass: "tag-default",
  };
}

// 切换运行时先清空缓存；两个侦听器按注册顺序执行，因此重新加载一定发生在清空之后。
watch(() => props.runId, reset);
// 以字符串作为观察键，避免数组 getter 每次求值都产生新引用而反复触发。
watch(
  () =>
    `${props.runId}:${props.unit?.unit_id ?? ""}:${croppedObjects.value.length}`,
  () => {
    activeIndex.value = -1;
    loadCrops();
  },
  { immediate: true },
);
onBeforeUnmount(reset);
</script>

<template>
  <section class="panel feature-crops">
    <div class="panel-header">
      <h2>当前单元特征图片</h2>
      <span class="badge">{{ croppedObjects.length }} 张</span>
    </div>

    <p v-if="error" class="callout error">{{ error }}</p>

    <div v-if="cropCards.length" class="crop-grid">
      <button
        v-for="(card, index) in cropCards"
        :key="card.object.object_id"
        class="crop-card"
        :class="[
          getCropTag(card.object).badgeClass,
          { 'is-cosplay-card': getCropTag(card.object).type === 'cosplay' },
          {
            'is-special-card':
              getCropTag(card.object).type === 'special-fashion',
          },
        ]"
        :title="`${getCropTag(card.object).mainTitle} · 点击查看大图原图`"
        @click="openLightbox(index)"
      >
        <span class="crop-frame">
          <!-- 醒目角标 -->
          <span
            v-if="getCropTag(card.object).type === 'cosplay'"
            class="crop-corner-badge cosplay-badge"
          >
            二次元
          </span>
          <span
            v-else-if="getCropTag(card.object).type === 'special-fashion'"
            class="crop-corner-badge special-badge"
          >
            特色
          </span>
          <img
            v-if="card.src"
            :src="card.src"
            :alt="`${getCropTag(card.object).mainTitle}裁剪图`"
          />
          <Loader2 v-else-if="card.loading" :size="18" class="spin" />
          <ImageOff v-else :size="18" />
        </span>
        <span class="crop-meta">
          <div class="crop-meta-top">
            <strong
              :class="{
                'cosplay-text-highlight':
                  getCropTag(card.object).type === 'cosplay',
              }"
            >
              {{ getCropTag(card.object).mainTitle }}
            </strong>
            <small v-if="card.object.score != null">{{
              card.object.score.toFixed(2)
            }}</small>
          </div>
          <div v-if="getCropTag(card.object).subTitle" class="crop-meta-sub">
            {{ getCropTag(card.object).subTitle }}
          </div>
        </span>
      </button>
    </div>
    <div v-else class="empty crop-empty">
      {{
        objectCount
          ? "本单元的对象没有裁剪图，可能是运行时未开启特征图片、超出配额，或已超过保留期被清理。"
          : "本单元没有识别到对象。"
      }}
    </div>

    <div
      v-if="lightboxOpen"
      ref="lightboxElement"
      class="lightbox"
      role="dialog"
      aria-modal="true"
      aria-label="特征图片大图"
      tabindex="-1"
      @click.self="closeLightbox"
      @keydown="onKeydown"
    >
      <div class="lightbox-panel">
        <header>
          <div>
            <div class="lightbox-title-row">
              <span
                v-if="getCropTag(activeObject!).type === 'cosplay'"
                class="lightbox-tag-pill cosplay-pill"
              >
                二次元 Cosplay
              </span>
              <span
                v-else-if="getCropTag(activeObject!).type === 'special-fashion'"
                class="lightbox-tag-pill special-pill"
              >
                特色服饰
              </span>
              <strong>{{ getCropTag(activeObject!).mainTitle }}</strong>
            </div>
            <small>
              {{ activeIndex + 1 }} / {{ croppedObjects.length }}
              <template v-if="getCropTag(activeObject!).subTitle">
                · {{ getCropTag(activeObject!).subTitle }}
              </template>
              <template v-if="unit">
                · 原图 {{ unit.width }} × {{ unit.height }}</template
              >
              <template v-if="activeObject!.score != null">
                · 置信度 {{ activeObject!.score!.toFixed(3) }}</template
              >
            </small>
          </div>
          <button
            class="icon-button"
            aria-label="关闭大图"
            title="关闭大图"
            @click="closeLightbox"
          >
            <X :size="18" />
          </button>
        </header>

        <div
          ref="stageElement"
          class="lightbox-stage"
          :class="{
            'is-dragging': isDragging,
            'is-zoomed': zoom > 1.05,
          }"
          :style="{ aspectRatio: unitAspectRatio }"
          @wheel.prevent="onWheel"
          @mousedown="onMouseDown"
          @dblclick="onDoubleClick"
        >
          <div class="lightbox-canvas" :style="transformStyle">
            <img
              v-if="largeUrl"
              :src="largeUrl"
              alt="对象所在的完整原图"
              draggable="false"
            />
            <Loader2 v-else-if="largeLoading" :size="22" class="spin" />
            <span v-else class="lightbox-missing">该单元的大图原图不可用</span>
            <span
              v-if="largeUrl && highlightStyle"
              class="lightbox-highlight"
              :style="highlightStyle"
            />
          </div>

          <!-- 悬浮缩放控制工具栏 -->
          <div class="lightbox-zoom-toolbar" @mousedown.stop @dblclick.stop>
            <button
              type="button"
              class="zoom-tool-btn"
              title="缩小 (快捷键: - 或 滚轮向下)"
              :disabled="zoom <= MIN_ZOOM"
              @click.stop="zoomOut"
            >
              <ZoomOut :size="15" />
            </button>
            <button
              type="button"
              class="zoom-tool-label"
              title="点击重置为 100% 原始大小 (快捷键: 0)"
              @click.stop="resetZoom"
            >
              {{ Math.round(zoom * 100) }}%
            </button>
            <button
              type="button"
              class="zoom-tool-btn"
              title="放大 (快捷键: + 或 滚轮向上)"
              :disabled="zoom >= MAX_ZOOM"
              @click.stop="zoomIn"
            >
              <ZoomIn :size="15" />
            </button>
            <span class="zoom-tool-divider" />
            <button
              type="button"
              class="zoom-tool-btn"
              title="聚焦当前目标 (快捷键: F 或 双击图片)"
              @click.stop="focusTarget"
            >
              <Target :size="15" />
            </button>
            <button
              type="button"
              class="zoom-tool-btn"
              title="重置缩放与位置"
              @click.stop="resetZoom"
            >
              <RotateCcw :size="15" />
            </button>
          </div>
        </div>

        <footer>
          <button
            class="button secondary"
            :disabled="croppedObjects.length < 2"
            title="上一个对象（← 键）"
            @click="step(-1)"
          >
            上一个
          </button>
          <span class="lightbox-hint">
            按 Esc 关闭，← → 切换对象 · 滚轮 / +/- 缩放 · 拖拽平移 · 双击 / F 聚焦目标
          </span>
          <button
            class="button secondary"
            :disabled="croppedObjects.length < 2"
            title="下一个对象（→ 键）"
            @click="step(1)"
          >
            下一个
          </button>
        </footer>
      </div>
    </div>
  </section>
</template>

<style scoped>
.crop-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(118px, 1fr));
  gap: 10px;
  padding: 12px;
}
.crop-card {
  display: grid;
  gap: 6px;
  padding: 6px;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--text);
  cursor: pointer;
  border-radius: 6px;
  text-align: left;
  transition: all 0.15s ease;
}
.crop-card:hover,
.crop-card:focus-visible {
  border-color: var(--teal, #2f9e7e);
  background: #f0fdf4;
}

/* Cosplay and Fashion Badges */
.crop-card.is-cosplay-card {
  border: 1.5px solid #8b5cf6;
  background: #fbf9ff;
  box-shadow: 0 2px 8px rgba(139, 92, 246, 0.12);
}
.crop-card.is-cosplay-card:hover,
.crop-card.is-cosplay-card:focus-visible {
  border-color: #7c3aed;
  background: #f5f3ff;
  box-shadow: 0 4px 14px rgba(124, 58, 237, 0.22);
}
.crop-card.is-special-card {
  border: 1.5px solid #ec4899;
  background: #fdf2f8;
}
.crop-card.is-special-card:hover,
.crop-card.is-special-card:focus-visible {
  border-color: #db2777;
  background: #fce7f3;
}
.crop-corner-badge {
  position: absolute;
  top: 4px;
  left: 4px;
  z-index: 2;
  font-size: 9.5px;
  font-weight: 700;
  padding: 1.5px 5px;
  border-radius: 3px;
  line-height: 1.2;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
}
.crop-corner-badge.cosplay-badge {
  background: linear-gradient(135deg, #7c3aed, #a855f7);
  color: #ffffff;
  border: 1px solid rgba(255, 255, 255, 0.35);
}
.crop-corner-badge.special-badge {
  background: linear-gradient(135deg, #db2777, #f43f5e);
  color: #ffffff;
  border: 1px solid rgba(255, 255, 255, 0.35);
}

.crop-frame {
  position: relative;
  display: grid;
  place-items: center;
  aspect-ratio: 3 / 4;
  overflow: hidden;
  background: #101816;
  color: #9fb1aa;
  border-radius: 4px;
}
.crop-frame img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.crop-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.crop-meta-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 4px;
}
.crop-meta-top strong {
  font-size: 11.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.crop-meta-top strong.cosplay-text-highlight {
  color: #7c3aed;
  font-weight: 750;
}
.crop-meta-top small {
  color: var(--muted);
  font-size: 10.5px;
  font-family: var(--font-mono, monospace);
  flex-shrink: 0;
}
.crop-meta-sub {
  font-size: 10px;
  color: var(--muted, #64748b);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lightbox-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.lightbox-tag-pill {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
}
.lightbox-tag-pill.cosplay-pill {
  background: #f5f3ff;
  color: #7c3aed;
  border: 1px solid #c4b5fd;
}
.lightbox-tag-pill.special-pill {
  background: #fdf2f8;
  color: #db2777;
  border: 1px solid #fbcfe8;
}
.crop-empty {
  min-height: 96px;
  padding: 16px;
  text-align: center;
}
.lightbox {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(10, 18, 16, 0.78);
}
.lightbox-panel {
  display: grid;
  gap: 12px;
  width: min(1080px, 100%);
  max-height: 100%;
  padding: 14px;
  overflow: auto;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 4px;
}
.lightbox-panel header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.lightbox-panel header small {
  display: block;
  margin-top: 3px;
  color: var(--muted);
  font-size: 11px;
}
.lightbox-stage {
  position: relative;
  display: grid;
  place-items: center;
  width: 100%;
  max-height: 68vh;
  margin-inline: auto;
  overflow: hidden;
  background: #0b1311;
  color: #dbe6e2;
  border-radius: 6px;
  cursor: grab;
  user-select: none;
}
.lightbox-stage.is-dragging {
  cursor: grabbing;
}
.lightbox-stage.is-zoomed {
  cursor: grab;
}
.lightbox-canvas {
  position: relative;
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  will-change: transform;
}
.lightbox-canvas img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  user-select: none;
  -webkit-user-drag: none;
  pointer-events: none;
}
.lightbox-missing {
  font-size: 12px;
}
.lightbox-highlight {
  position: absolute;
  outline: 2.5px solid #ef4444;
  outline-offset: 0;
  box-shadow: 0 0 0 9999px rgba(10, 18, 16, 0.38);
  pointer-events: none;
  border-radius: 2px;
}

/* 浮动缩放工具栏 */
.lightbox-zoom-toolbar {
  position: absolute;
  right: 14px;
  bottom: 14px;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 4px 6px;
  background: rgba(15, 23, 42, 0.78);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 20px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.45);
  user-select: none;
}
.zoom-tool-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  border: none;
  background: transparent;
  color: #f1f5f9;
  border-radius: 50%;
  cursor: pointer;
  transition: all 0.15s ease;
}
.zoom-tool-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.2);
  color: #ffffff;
}
.zoom-tool-btn:active:not(:disabled) {
  transform: scale(0.92);
}
.zoom-tool-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.zoom-tool-label {
  padding: 2px 6px;
  border: none;
  background: transparent;
  color: #cbd5e1;
  font-size: 11.5px;
  font-family: var(--font-mono, monospace);
  font-weight: 600;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.15s;
}
.zoom-tool-label:hover {
  background: rgba(255, 255, 255, 0.15);
  color: #ffffff;
}
.zoom-tool-divider {
  width: 1px;
  height: 14px;
  background: rgba(255, 255, 255, 0.22);
  margin-inline: 2px;
}

.lightbox-panel footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.lightbox-hint {
  color: var(--muted);
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
@media (max-width: 520px) {
  .crop-grid {
    grid-template-columns: repeat(auto-fill, minmax(88px, 1fr));
  }
  .lightbox {
    padding: 12px;
  }
}
</style>
