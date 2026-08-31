<script setup lang="ts">
import { Pause, Play, Plus, RefreshCw } from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";

import { userFacingError } from "../../api";
import {
  createTask,
  listTasks,
  listWatchlists,
  taskAction,
} from "../../api/surveillance";
import { labelSurveillanceTaskStatus } from "../../labels";
import type {
  CameraRecord,
  MediaSource,
  SurveillanceTask,
  Watchlist,
} from "../../types";
import { api } from "../../api";

const tasks = ref<SurveillanceTask[]>([]);
const watchlists = ref<Watchlist[]>([]);
const sources = ref<MediaSource[]>([]);
const cameras = ref<CameraRecord[]>([]);
const loading = ref(false);
const error = ref("");
const form = reactive({
  name: "",
  watchlist_id: "",
  source_id: "",
  camera_id: "",
  face_threshold: 0.8,
  body_threshold: 0.72,
  cooldown_seconds: 30,
  alert_level: "warning",
});
const ready = computed(() =>
  Boolean(form.name && form.watchlist_id && form.source_id && form.camera_id),
);

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [taskPage, watchlistPage, sourcePage, cameraRows] = await Promise.all(
      [
        listTasks(),
        listWatchlists(),
        api<{ items: MediaSource[] }>("/api/v1/media/sources?limit=200"),
        api<CameraRecord[]>("/api/v1/portrait/cameras"),
      ],
    );
    tasks.value = taskPage.items;
    watchlists.value = watchlistPage.items.filter(
      (item) => item.status !== "archived",
    );
    sources.value = sourcePage.items;
    cameras.value = cameraRows;
  } catch (caught) {
    error.value = userFacingError(caught);
  } finally {
    loading.value = false;
  }
}

async function create(): Promise<void> {
  try {
    await createTask({
      name: form.name,
      watchlist_ids: [form.watchlist_id],
      bindings: [
        {
          binding_id: `bind-${crypto.randomUUID()}`,
          source_id: form.source_id,
          camera_id: form.camera_id,
        },
      ],
      schedule: {
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
        weekly: [],
        exceptions: [],
      },
      match_policy: "alert_on_match",
      threshold_policy: {
        policy_version: "console-v1",
        face_threshold: form.face_threshold,
        body_threshold: form.body_threshold,
        min_face_quality: 0,
        min_body_quality: 0,
        face_weight: 0.65,
        body_weight: 0.35,
      },
      cooldown_seconds: form.cooldown_seconds,
      alert_level: form.alert_level,
    });
    form.name = "";
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught);
  }
}

async function action(
  task: SurveillanceTask,
  operation: "start" | "pause" | "resume",
): Promise<void> {
  try {
    await taskAction(task.task_id, operation);
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught);
  }
}

onMounted(() => void refresh());
</script>

<template>
  <main class="page task-page">
    <p v-if="error" class="error-message">{{ error }}</p>
    <section class="panel form-grid">
      <label
        >任务名称<input
          v-model.trim="form.name"
          placeholder="例如：大堂重点布控"
      /></label>
      <label
        >名单<select v-model="form.watchlist_id">
          <option value="">请选择</option>
          <option
            v-for="item in watchlists"
            :key="item.watchlist_id"
            :value="item.watchlist_id"
          >
            {{ item.name }}
          </option>
        </select></label
      >
      <label
        >视频源<select v-model="form.source_id">
          <option value="">请选择</option>
          <option
            v-for="item in sources"
            :key="item.source_id"
            :value="item.source_id"
          >
            {{ item.name }}
          </option>
        </select></label
      >
      <label
        >摄像头<select v-model="form.camera_id">
          <option value="">请选择</option>
          <option
            v-for="item in cameras"
            :key="item.camera_id"
            :value="item.camera_id"
          >
            {{ item.display_name }}
          </option>
        </select></label
      >
      <label
        >人脸阈值<input
          v-model.number="form.face_threshold"
          type="number"
          min="-1"
          max="1"
          step=".01"
      /></label>
      <label
        >人体阈值<input
          v-model.number="form.body_threshold"
          type="number"
          min="-1"
          max="1"
          step=".01"
      /></label>
      <label
        >冷却秒数<input
          v-model.number="form.cooldown_seconds"
          type="number"
          min="1"
          max="86400"
      /></label>
      <label
        >告警等级<select v-model="form.alert_level">
          <option value="critical">严重</option>
          <option value="warning">警告</option>
          <option value="info">提示</option>
        </select></label
      >
      <button class="button" :disabled="!ready" @click="create">
        <Plus :size="16" />创建任务
      </button>
    </section>
    <section class="panel">
      <div class="panel-header-row">
        <h2>任务列表</h2>
        <button class="button secondary refresh-btn" @click="refresh">
          <RefreshCw :size="14" />刷新
        </button>
      </div>
      <div v-for="task in tasks" :key="task.task_id" class="task-row">
        <div>
          <strong>{{ task.name }}</strong
          ><small
            >{{ task.task_id }} ·
            {{ task.bindings.map((item) => item.camera_id).join(", ") }} ·
            {{ task.cooldown_seconds }} 秒冷却</small
          >
        </div>
        <div class="actions">
          <span class="badge" :class="task.status">{{ labelSurveillanceTaskStatus(task.status) }}</span
          ><button
            v-if="task.status !== 'active'"
            class="icon-button"
            title="启动"
            @click="action(task, task.status === 'paused' ? 'resume' : 'start')"
          >
            <Play :size="16" /></button
          ><button
            v-else
            class="icon-button"
            title="暂停"
            @click="action(task, 'pause')"
          >
            <Pause :size="16" />
          </button>
        </div>
      </div>
      <p v-if="!tasks.length" class="muted">暂无布控任务。</p>
    </section>
  </main>
</template>

<style scoped>
.task-page {
  display: grid;
  gap: 1rem;
}
.panel-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.8rem;
}
h2 {
  font-size: 1rem;
  margin: 0;
}
.panel {
  border: 1px solid var(--border-color, #d9e0ea);
  border-radius: 0.8rem;
  padding: 1rem;
  background: var(--panel-color, #fff);
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.75rem;
  align-items: end;
}
label {
  display: grid;
  gap: 0.3rem;
  color: var(--muted-text, #64748b);
  font-size: 0.84rem;
}
input,
select {
  min-width: 0;
  padding: 0.6rem;
  border: 1px solid var(--border-color, #cbd5e1);
  border-radius: 0.45rem;
  background: transparent;
  color: inherit;
}
.button,
.icon-button {
  border: 0;
  border-radius: 0.5rem;
  cursor: pointer;
}
.button {
  min-height: 2.35rem;
  display: inline-flex;
  gap: 0.35rem;
  align-items: center;
  justify-content: center;
  padding: 0.45rem 0.8rem;
  background: var(--accent, #2563eb);
  color: #fff;
}
.button.secondary,
.icon-button {
  background: var(--soft-color, #e2e8f0);
  color: inherit;
}
.button:disabled {
  opacity: 0.5;
}
.task-row {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.85rem 0;
  border-bottom: 1px solid var(--border-color, #e2e8f0);
}
small {
  display: block;
  color: var(--muted-text, #64748b);
  margin-top: 0.25rem;
}
.actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.icon-button {
  padding: 0.45rem;
}
.badge {
  padding: 0.2rem 0.45rem;
  border-radius: 999px;
  background: var(--soft-color, #e2e8f0);
  font-size: 0.78rem;
}
.badge.active {
  background: #dcfce7;
  color: #166534;
}
.badge.failed {
  background: #fee2e2;
  color: #991b1b;
}
.error-message {
  color: #dc2626;
}
.muted {
  color: var(--muted-text, #64748b);
}
@media (max-width: 900px) {
  .page-header,
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
