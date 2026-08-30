<script setup lang="ts">
import { BellRing, Radio, Volume2, VolumeX } from "@lucide/vue";
import { onBeforeUnmount, onMounted, ref } from "vue";

import { api, apiStream, streamJsonEvents, userFacingError } from "../../api";
import { listAlerts } from "../../api/surveillance";
import type { SurveillanceAlert, SurveillanceAlertEvent } from "../../types";

const alerts = ref<SurveillanceAlert[]>([]);
const connected = ref(false);
const muted = ref(true);
const error = ref("");
let controller: AbortController | null = null;
let cursor = 0;

function format(value: number): string {
  return new Date(value * 1000).toLocaleTimeString("zh-CN", { hour12: false });
}
function snapshot(alert: SurveillanceAlert): string | null {
  return alert.snapshot_artifact_id
    ? `/api/v1/runs/${encodeURIComponent(alert.run_id)}/artifacts/${encodeURIComponent(alert.snapshot_artifact_id)}`
    : null;
}
function beep(): void {
  if (muted.value || typeof AudioContext === "undefined") return;
  const context = new AudioContext();
  const oscillator = context.createOscillator();
  oscillator.frequency.value = 880;
  oscillator.connect(context.destination);
  oscillator.start();
  oscillator.stop(context.currentTime + 0.12);
  oscillator.addEventListener("ended", () => void context.close());
}
async function initial(): Promise<void> {
  const page = await listAlerts("limit=30");
  alerts.value = page.items;
}
async function connect(): Promise<void> {
  controller?.abort();
  controller = new AbortController();
  connected.value = false;
  error.value = "";
  try {
    const response = await apiStream(
      `/api/v1/surveillance/alerts/live-stream?last_event_id=${cursor}`,
      controller.signal,
    );
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
        beep();
      }
    }
  } catch (caught) {
    if (!controller?.signal.aborted)
      error.value = userFacingError(caught, "实时告警连接已断开");
  } finally {
    connected.value = false;
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
</script>

<template>
  <main class="page live-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Live Surveillance</p>
        <h1>实时预警中心</h1>
        <p>只显示已持久化告警。断线后可按事件游标恢复历史。</p>
      </div>
      <div class="toolbar">
        <span class="connection" :class="{ online: connected }"
          ><Radio :size="15" />{{ connected ? "已连接" : "重连中" }}</span
        ><button class="button secondary" @click="muted = !muted">
          <VolumeX v-if="muted" :size="16" /><Volume2 v-else :size="16" />{{
            muted ? "开启提示音" : "静音"
          }}
        </button>
      </div>
    </header>
    <p v-if="error" class="error-message">{{ error }}</p>
    <section class="alert-wall">
      <article v-for="alert in alerts" :key="alert.alert_id" class="alert-card">
        <img v-if="snapshot(alert)" :src="snapshot(alert)!" alt="实时抓拍" />
        <div class="alert-content">
          <div class="card-top">
            <BellRing :size="18" /><strong>{{ alert.camera_id }}</strong
            ><time>{{ format(alert.triggered_at) }}</time>
          </div>
          <p class="score">{{ (alert.match_score * 100).toFixed(1) }}%</p>
          <p>{{ alert.modality }} · {{ alert.portrait_identity_id }}</p>
          <small>告警事件 · 已出现 {{ alert.occurrence_count }} 次</small>
        </div>
      </article>
      <p v-if="!alerts.length" class="empty">等待新的已持久化告警。</p>
    </section>
  </main>
</template>

<style scoped>
.live-page {
  display: grid;
  gap: 1rem;
}
.page-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: start;
}
.eyebrow {
  margin: 0;
  color: var(--accent, #2563eb);
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
h1,
p {
  margin-top: 0;
}
.toolbar {
  display: flex;
  gap: 0.6rem;
  align-items: center;
}
.connection {
  display: inline-flex;
  gap: 0.3rem;
  align-items: center;
  color: #b45309;
}
.connection.online {
  color: #15803d;
}
.button {
  border: 0;
  border-radius: 0.5rem;
  padding: 0.45rem 0.75rem;
  cursor: pointer;
}
.button.secondary {
  background: var(--soft-color, #e2e8f0);
  color: inherit;
}
.alert-wall {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 1rem;
}
.alert-card {
  overflow: hidden;
  border: 1px solid var(--border-color, #d9e0ea);
  border-radius: 0.8rem;
  background: var(--panel-color, #fff);
  box-shadow: 0 0.3rem 1rem rgba(15, 23, 42, 0.07);
}
.alert-card img {
  width: 100%;
  height: 170px;
  object-fit: cover;
  background: #e2e8f0;
}
.alert-content {
  padding: 0.85rem;
}
.card-top {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.card-top time {
  margin-left: auto;
  color: var(--muted-text, #64748b);
  font-size: 0.8rem;
}
.score {
  font-size: 2rem;
  font-weight: 750;
  margin: 0.65rem 0 0.15rem;
  color: #dc2626;
}
.alert-content p:not(.score) {
  font-size: 0.85rem;
  overflow-wrap: anywhere;
}
.alert-content small {
  color: var(--muted-text, #64748b);
}
.empty {
  grid-column: 1/-1;
  text-align: center;
  padding: 3rem;
  color: var(--muted-text, #64748b);
  border: 1px dashed var(--border-color, #cbd5e1);
  border-radius: 0.8rem;
}
.error-message {
  color: #dc2626;
}
@media (max-width: 700px) {
  .page-header {
    display: grid;
  }
  .toolbar {
    justify-content: space-between;
  }
}
</style>
