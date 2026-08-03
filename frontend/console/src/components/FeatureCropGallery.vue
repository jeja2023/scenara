<script setup lang="ts">
import { ImageOff, Loader2, X } from "@lucide/vue";
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
}

function step(offset: number): void {
  const total = croppedObjects.value.length;
  if (total < 2) return;
  activeIndex.value = (activeIndex.value + offset + total) % total;
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") closeLightbox();
  else if (event.key === "ArrowLeft") step(-1);
  else if (event.key === "ArrowRight") step(1);
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
      <h2>特征图片</h2>
      <span class="badge">{{ croppedObjects.length }} 张</span>
    </div>

    <p v-if="error" class="callout error">{{ error }}</p>

    <div v-if="cropCards.length" class="crop-grid">
      <button
        v-for="(card, index) in cropCards"
        :key="card.object.object_id"
        class="crop-card"
        :title="`${labelObjectType(card.object.object_type)} · 点击查看大图原图`"
        @click="openLightbox(index)"
      >
        <span class="crop-frame">
          <img
            v-if="card.src"
            :src="card.src"
            :alt="`${labelObjectType(card.object.object_type)}裁剪图`"
          />
          <Loader2 v-else-if="card.loading" :size="18" class="spin" />
          <ImageOff v-else :size="18" />
        </span>
        <span class="crop-meta">
          <strong>{{ labelObjectType(card.object.object_type) }}</strong>
          <small v-if="card.object.score != null">{{
            card.object.score.toFixed(2)
          }}</small>
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
            <strong>{{ labelObjectType(activeObject!.object_type) }}</strong>
            <small>
              {{ activeIndex + 1 }} / {{ croppedObjects.length }}
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

        <div class="lightbox-stage" :style="{ aspectRatio: unitAspectRatio }">
          <img v-if="largeUrl" :src="largeUrl" alt="对象所在的完整原图" />
          <Loader2 v-else-if="largeLoading" :size="22" class="spin" />
          <span v-else class="lightbox-missing">该单元的大图原图不可用</span>
          <span
            v-if="largeUrl && highlightStyle"
            class="lightbox-highlight"
            :style="highlightStyle"
          />
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
          <span class="lightbox-hint">按 Esc 关闭，← → 切换对象</span>
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
  grid-template-columns: repeat(auto-fill, minmax(108px, 1fr));
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
  border-radius: 4px;
  text-align: left;
}
.crop-card:hover,
.crop-card:focus-visible {
  border-color: var(--teal);
  background: #e7f1ee;
}
.crop-frame {
  position: relative;
  display: grid;
  place-items: center;
  aspect-ratio: 3 / 4;
  overflow: hidden;
  background: #101816;
  color: #9fb1aa;
  border-radius: 3px;
}
.crop-frame img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.crop-meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 6px;
}
.crop-meta strong {
  font-size: 12px;
}
.crop-meta small {
  color: var(--muted);
  font-size: 11px;
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
  background: #101816;
  color: #dbe6e2;
  border-radius: 3px;
}
.lightbox-stage img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.lightbox-missing {
  font-size: 12px;
}
.lightbox-highlight {
  position: absolute;
  outline: 2px solid #ef6c52;
  outline-offset: 0;
  box-shadow: 0 0 0 9999px rgba(10, 18, 16, 0.35);
  pointer-events: none;
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
