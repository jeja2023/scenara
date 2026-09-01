<script setup lang="ts">
import { BellRing, Camera, Radio, Trash2, Volume2, VolumeX } from "@lucide/vue";
import { onBeforeUnmount, onMounted, ref } from "vue";

import {
  api,
  apiImageDataUrl,
  apiStream,
  streamJsonEvents,
  userFacingError,
} from "../../api";
import { listAlerts } from "../../api/surveillance";
import { labelModality } from "../../labels";
import type { SurveillanceAlert, SurveillanceAlertEvent } from "../../types";

const alerts = ref<SurveillanceAlert[]>([]);
const snapshotUrls = ref(new Map<string, string>());
const failedSnapshots = ref(new Set<string>());
const connected = ref(false);
const muted = ref(true);
const error = ref("");
let controller: AbortController | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
let stopped = false;
let reconnectAttempt = 0;
let cursor = 0;

function scheduleReconnect(): void {
  if (stopped || reconnectTimer !== undefined) return;
  const delay = Math.min(30_000, 1_000 * 2 ** Math.min(5, reconnectAttempt++));
  reconnectTimer = setTimeout(() => {
    reconnectTimer = undefined;
    void connect();
  }, delay);
}

function format(value: number): string {
  if (!value) return "-";
  return new Date(value * 1000).toLocaleTimeString("zh-CN", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function snapshotPath(alert: SurveillanceAlert): string | null {
  return alert.snapshot_artifact_id
    ? `/api/v1/runs/${encodeURIComponent(alert.run_id)}/artifacts/${encodeURIComponent(alert.snapshot_artifact_id)}`
    : null;
}

function snapshot(alert: SurveillanceAlert): string | null {
  return snapshotUrls.value.get(alert.alert_id) ?? null;
}

async function loadSnapshot(alert: SurveillanceAlert): Promise<void> {
  const path = snapshotPath(alert);
  if (!path || snapshotUrls.value.has(alert.alert_id)) return;
  try {
    const url = await apiImageDataUrl(path);
    snapshotUrls.value = new Map(snapshotUrls.value).set(alert.alert_id, url);
  } catch {
    failedSnapshots.value = new Set(failedSnapshots.value).add(alert.alert_id);
  }
}

function retrySnapshot(alert: SurveillanceAlert): void {
  const next = new Set(failedSnapshots.value);
  next.delete(alert.alert_id);
  failedSnapshots.value = next;
  void loadSnapshot(alert);
}

function beep(): void {
  if (muted.value || typeof AudioContext === "undefined") return;
  try {
    const context = new AudioContext();
    const oscillator = context.createOscillator();
    oscillator.frequency.value = 880;
    oscillator.connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.12);
    oscillator.addEventListener("ended", () => void context.close());
  } catch {
    // Ignore audio context autoplay restriction errors
  }
}

async function initial(): Promise<void> {
  const page = await listAlerts("limit=30");
  alerts.value = page.items;
  await Promise.all(page.items.map(loadSnapshot));
}

async function connect(): Promise<void> {
  if (stopped) return;
  controller?.abort();
  controller = new AbortController();
  connected.value = false;
  error.value = "";
  try {
    const response = await apiStream(
      `/api/v1/surveillance/alerts/live-stream?last_event_id=${cursor}`,
      controller.signal,
    );
    reconnectAttempt = 0;
    connected.value = true;
    for await (const event of streamJsonEvents<SurveillanceAlertEvent>(
      response,
    )) {
      cursor = Math.max(cursor, event.event_cursor);
      if (event.event_type !== "alert.triggered") {
        await initial();
        continue;
      }
      const alert = await api<SurveillanceAlert>(
        `/api/v1/surveillance/alerts/${encodeURIComponent(event.alert_id)}`,
      );
      if (!alerts.value.some((item) => item.alert_id === alert.alert_id)) {
        alerts.value = [alert, ...alerts.value].slice(0, 30);
        void loadSnapshot(alert);
        beep();
      }
    }
  } catch (caught) {
    if (!controller?.signal.aborted) {
      error.value = userFacingError(caught, "实时告警连接已断开");
      scheduleReconnect();
    }
  } finally {
    connected.value = false;
    if (!stopped && !controller?.signal.aborted) scheduleReconnect();
  }
}

onMounted(async () => {
  try {
    await initial();
  } catch (caught) {
    error.value = userFacingError(caught);
  }
  void connect();
});

onBeforeUnmount(() => controller?.abort());
onBeforeUnmount(() => {
  stopped = true;
  if (reconnectTimer !== undefined) clearTimeout(reconnectTimer);
});
</script>

<template>
  <main class="page live-page">
    <p v-if="error" class="error-banner">{{ error }}</p>

    <!-- 顶部操作与流连接状态工具栏 -->
    <div class="filter-controls">
      <div class="filter-left">
        <span class="live-status-pill" :class="{ online: connected }">
          <span class="pulse-dot"></span>
          <Radio :size="13" />
          <span>{{
            connected
              ? "实时事件流已连接 (Active)"
              : "事件流重连中 (Connecting...)"
          }}</span>
        </span>

        <span class="badge count-badge">实时捕获: {{ alerts.length }} 条</span>
      </div>

      <div class="filter-right">
        <button
          class="button secondary tiny-btn audio-btn"
          :class="{ active: !muted }"
          @click="muted = !muted"
        >
          <Volume2 v-if="!muted" :size="13" class="audio-on-icon" />
          <VolumeX v-else :size="13" />
          <span>{{ muted ? "开启提示音效" : "静音模式" }}</span>
        </button>

        <button
          class="button secondary tiny-btn"
          :disabled="!alerts.length"
          @click="alerts = []"
        >
          <Trash2 :size="12" />
          <span>清空实时流</span>
        </button>
      </div>
    </div>

    <!-- 实时告警墙网格 -->
    <section class="live-alert-grid">
      <article
        v-for="alert in alerts"
        :key="alert.alert_id"
        class="panel live-card-item"
      >
        <!-- 顶部实时抓拍图 -->
        <div class="snapshot-wrapper">
          <img
            v-if="snapshot(alert)"
            :src="snapshot(alert)!"
            alt="实时抓拍"
            class="live-img"
          />
          <div v-else class="placeholder-box">
            <Camera :size="28" class="placeholder-icon" />
            <span>{{
              failedSnapshots.has(alert.alert_id)
                ? "抓拍图加载失败"
                : "无抓拍图"
            }}</span>
            <button
              v-if="failedSnapshots.has(alert.alert_id)"
              class="button secondary tiny-btn"
              @click.stop="retrySnapshot(alert)"
            >
              重试
            </button>
          </div>

          <!-- 抓拍时间角标 -->
          <div class="time-overlay-tag">
            {{ format(alert.triggered_at) }}
          </div>

          <!-- 相似度得分角标 -->
          <div class="score-overlay-tag">
            <span>相似度</span>
            <strong>{{ (alert.match_score * 100).toFixed(1) }}%</strong>
          </div>
        </div>

        <!-- 告警内容摘要 -->
        <div class="live-content">
          <div class="camera-row">
            <div class="camera-info">
              <Camera :size="13" class="cam-icon" />
              <strong>{{ alert.camera_id }}</strong>
            </div>
            <span class="badge modality-badge">{{
              labelModality(alert.modality)
            }}</span>
          </div>

          <div class="identity-info-row">
            <span class="identity-label">目标身份:</span>
            <span class="mono identity-val">{{
              alert.portrait_identity_id
            }}</span>
          </div>

          <div class="footer-stats-row">
            <span class="occurrence-text">
              已累计出现 <strong>{{ alert.occurrence_count }}</strong> 次
            </span>
            <span class="max-score-text"
              >最高 {{ (alert.max_score * 100).toFixed(1) }}%</span
            >
          </div>
        </div>
      </article>
    </section>

    <div v-if="!alerts.length" class="panel empty-live-state">
      <div class="radar-pulse-box">
        <BellRing :size="36" class="radar-icon" />
      </div>
      <p class="empty-title">正在监听实时布控告警事件流</p>
      <p class="empty-sub">
        当摄像头检测到符合布控名单的目标时，将在此处实时推送告警抓拍与研判卡片
      </p>
    </div>
  </main>
</template>

<style scoped>
.live-page {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.error-banner {
  padding: 8px 12px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  border-radius: 4px;
  font-size: 12px;
  margin: 0;
}

/* 顶部控制栏 */
.filter-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  padding: 6px 12px;
  flex-wrap: wrap;
}

.filter-left,
.filter-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.live-status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 500;
  background: #fef3c7;
  color: #92400e;
  border: 1px solid #fde68a;
  transition: all 0.2s ease;
}

.live-status-pill.online {
  background: #dcfce7;
  color: #166534;
  border-color: #bbf7d0;
}

.pulse-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #d97706;
}

.live-status-pill.online .pulse-dot {
  background: #16a34a;
  box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.25);
  animation: pulse 1.8s infinite;
}

@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.5);
  }
  70% {
    box-shadow: 0 0 0 6px rgba(34, 197, 94, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(34, 197, 94, 0);
  }
}

.count-badge {
  background: #edf2f0;
  color: #45534f;
  font-size: 11px;
  padding: 3px 7px;
  border-radius: 4px;
}

.audio-btn.active {
  background: var(--color-accent-soft, #e4f1f1);
  color: var(--color-accent-hover, #065e67);
  border-color: var(--color-accent, #087682);
}

.audio-on-icon {
  color: var(--color-accent, #087682);
}

/* 实时卡片网格 */
.live-alert-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}

.live-card-item {
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: all 0.15s ease;
}

.live-card-item:hover {
  border-color: var(--line-strong, #b7c2bd);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
  transform: translateY(-1px);
}

.snapshot-wrapper {
  position: relative;
  width: 100%;
  height: 150px;
  background: #f1f4f3;
  display: flex;
  align-items: center;
  justify-content: center;
}

.live-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.placeholder-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  color: var(--muted, #64716d);
  font-size: 11px;
}

.placeholder-icon {
  color: #b7c2bd;
}

.time-overlay-tag {
  position: absolute;
  top: 6px;
  left: 6px;
  background: rgba(17, 26, 24, 0.75);
  backdrop-filter: blur(4px);
  color: #ffffff;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10.5px;
  font-family: var(--font-mono, monospace);
}

.score-overlay-tag {
  position: absolute;
  bottom: 6px;
  right: 6px;
  background: rgba(17, 26, 24, 0.82);
  backdrop-filter: blur(4px);
  color: #ffffff;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.score-overlay-tag strong {
  color: #34d399;
  font-size: 11.5px;
}

/* 卡片内容 */
.live-content {
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.camera-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.camera-info {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.camera-info strong {
  font-size: 12.5px;
  color: var(--graphite, #17211f);
}

.cam-icon {
  color: var(--color-accent, #087682);
}

.modality-badge {
  font-size: 10px;
  background: #eef2f1;
  color: #2c3e38;
  padding: 1px 5px;
  border-radius: 3px;
}

.identity-info-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
}

.identity-label {
  color: var(--muted, #64716d);
  flex-shrink: 0;
}

.identity-val {
  color: var(--graphite, #17211f);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.footer-stats-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 10.5px;
  color: var(--muted, #64716d);
  padding-top: 4px;
  border-top: 1px dashed var(--line, #e2e8e6);
}

.occurrence-text strong {
  color: var(--color-accent, #087682);
}

/* 空状态 */
.empty-live-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 56px 16px;
  gap: 8px;
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  text-align: center;
}

.radar-pulse-box {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: #edf2f0;
  display: grid;
  place-items: center;
  margin-bottom: 6px;
}

.radar-icon {
  color: var(--color-accent, #087682);
}

.empty-title {
  margin: 0;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--graphite, #17211f);
}

.empty-sub {
  margin: 0;
  font-size: 11.5px;
  color: var(--muted, #64716d);
  max-width: 480px;
}

.mono {
  font-family: var(--font-mono, monospace);
  font-size: 11.5px;
}
</style>
