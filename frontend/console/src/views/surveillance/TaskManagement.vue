<script setup lang="ts">
import {
  Camera,
  ClipboardList,
  Filter,
  ListChecks,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Search,
  Sliders,
} from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";

import { api, userFacingError } from "../../api";
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

const tasks = ref<SurveillanceTask[]>([]);
const watchlists = ref<Watchlist[]>([]);
const sources = ref<MediaSource[]>([]);
const cameras = ref<CameraRecord[]>([]);
const loading = ref(false);
const mutating = ref(false);
const error = ref("");
const searchQuery = ref("");
const statusFilter = ref<string>("all");
const showCreateModal = ref(false);

const form = reactive({
  name: "",
  watchlist_id: "",
  source_id: "",
  camera_id: "",
  face_threshold: 0.8,
  body_threshold: 0.72,
  cooldown_seconds: 30,
  alert_level: "warning" as "critical" | "warning" | "info",
});

const isReadyToSubmit = computed(() =>
  Boolean(
    form.name.trim() &&
      form.watchlist_id &&
      form.source_id &&
      form.camera_id,
  ),
);

const filteredTasks = computed(() => {
  return tasks.value.filter((item) => {
    if (statusFilter.value !== "all" && item.status !== statusFilter.value) {
      return false;
    }
    if (searchQuery.value.trim()) {
      const q = searchQuery.value.trim().toLowerCase();
      const matchName = item.name.toLowerCase().includes(q);
      const matchId = item.task_id.toLowerCase().includes(q);
      const matchCamera = item.bindings.some((b) =>
        b.camera_id.toLowerCase().includes(q),
      );
      return matchName || matchId || matchCamera;
    }
    return true;
  });
});

function getWatchlistName(id: string): string {
  const wl = watchlists.value.find((item) => item.watchlist_id === id);
  return wl ? wl.name : id;
}

function getCameraName(id: string): string {
  const cam = cameras.value.find((item) => item.camera_id === id);
  return cam ? cam.display_name : id;
}

function getSourceName(id: string): string {
  const src = sources.value.find((item) => item.source_id === id);
  return src ? src.name : id;
}

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

async function handleCreateTask(): Promise<void> {
  if (!isReadyToSubmit.value) return;
  mutating.value = true;
  error.value = "";
  try {
    await createTask({
      name: form.name.trim(),
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
    showCreateModal.value = false;
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught);
  } finally {
    mutating.value = false;
  }
}

async function handleTaskAction(
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
    <p v-if="error" class="error-banner">{{ error }}</p>

    <!-- 顶部操作与筛选工具栏 -->
    <div class="filter-controls">
      <div class="filter-left">
        <label class="filter-item">
          <Filter :size="12" class="filter-icon" />
          <span class="filter-label">状态筛选:</span>
          <select v-model="statusFilter" class="filter-select">
            <option value="all">全部状态 (All)</option>
            <option value="active">运行中 (Active)</option>
            <option value="paused">已暂停 (Paused)</option>
            <option value="stopped">已停止 (Stopped)</option>
          </select>
        </label>

        <div class="search-box">
          <Search :size="13" class="search-icon" />
          <input
            v-model="searchQuery"
            placeholder="搜索任务名称、ID 或摄像头..."
            class="search-input"
          />
        </div>

        <span class="badge count-badge">共 {{ tasks.length }} 个布控任务</span>
      </div>

      <div class="filter-right">
        <button
          class="button secondary tiny-btn"
          :disabled="loading"
          @click="refresh"
        >
          <RefreshCw :size="12" :class="{ spinning: loading }" />
          <span>刷新</span>
        </button>
        <button
          class="button primary tiny-btn"
          @click="showCreateModal = true"
        >
          <Plus :size="13" />
          <span>新建布控任务</span>
        </button>
      </div>
    </div>

    <!-- 主工作区：布控任务表格 -->
    <section class="panel task-table-panel">
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width: 50px; text-align: center;">序号</th>
              <th style="width: 200px;">任务名称 / ID</th>
              <th style="width: 160px;">关联布控名单</th>
              <th style="width: 180px;">监控视频源与摄像头</th>
              <th style="width: 170px;">多模态比对阈值</th>
              <th style="width: 90px; text-align: center;">频控冷却</th>
              <th style="width: 80px; text-align: center;">告警等级</th>
              <th style="width: 90px; text-align: center;">任务状态</th>
              <th style="width: 100px; text-align: center;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(task, idx) in filteredTasks" :key="task.task_id">
              <td style="text-align: center;" class="muted mono">{{ idx + 1 }}</td>
              <td>
                <div class="task-title-cell">
                  <strong>{{ task.name }}</strong>
                  <span class="mono muted sub-id">{{ task.task_id }}</span>
                </div>
              </td>
              <td>
                <div class="watchlist-tags-cell">
                  <span
                    v-for="wId in task.watchlist_ids"
                    :key="wId"
                    class="badge watchlist-tag"
                  >
                    <ListChecks :size="11" />
                    {{ getWatchlistName(wId) }}
                  </span>
                </div>
              </td>
              <td>
                <div class="binding-info-cell">
                  <div
                    v-for="b in task.bindings"
                    :key="b.binding_id"
                    class="binding-row"
                  >
                    <Camera :size="12" class="binding-icon" />
                    <span>{{ getCameraName(b.camera_id) }}</span>
                    <small class="muted mono">({{ getSourceName(b.source_id) }})</small>
                  </div>
                </div>
              </td>
              <td>
                <div class="thresholds-cell">
                  <span class="thresh-item">人脸: <strong>{{ task.threshold_policy.face_threshold != null ? (task.threshold_policy.face_threshold * 100).toFixed(0) + '%' : '-' }}</strong></span>
                  <span class="divider">|</span>
                  <span class="thresh-item">人体: <strong>{{ task.threshold_policy.body_threshold != null ? (task.threshold_policy.body_threshold * 100).toFixed(0) + '%' : '-' }}</strong></span>
                </div>
              </td>
              <td style="text-align: center;" class="mono">
                {{ task.cooldown_seconds }}s
              </td>
              <td style="text-align: center;">
                <span class="badge alert-level-badge" :class="task.alert_level">
                  {{ task.alert_level === 'critical' ? '严重' : task.alert_level === 'warning' ? '警告' : '提示' }}
                </span>
              </td>
              <td style="text-align: center;">
                <span class="badge status-badge" :class="task.status">
                  {{ labelSurveillanceTaskStatus(task.status) }}
                </span>
              </td>
              <td style="text-align: center;">
                <div class="table-actions">
                  <button
                    v-if="task.status !== 'active'"
                    class="button primary tiny-btn action-btn start-btn"
                    title="启动布控任务"
                    @click="handleTaskAction(task, task.status === 'paused' ? 'resume' : 'start')"
                  >
                    <Play :size="11" />启动
                  </button>
                  <button
                    v-else
                    class="button secondary tiny-btn action-btn pause-btn"
                    title="暂停任务"
                    @click="handleTaskAction(task, 'pause')"
                  >
                    <Pause :size="11" />暂停
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!filteredTasks.length">
              <td colspan="9" class="empty-cell">
                <div class="empty-state">
                  <ClipboardList :size="32" class="empty-icon" />
                  <p>暂无符合条件的布控任务</p>
                  <button
                    class="button primary tiny-btn"
                    @click="showCreateModal = true"
                  >
                    <Plus :size="12" />立即创建布控任务
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- ==================== 创建任务模态弹窗 ==================== -->
    <div
      v-if="showCreateModal"
      class="modal-overlay"
      @click.self="showCreateModal = false"
    >
      <div class="modal-dialog modal-dialog-lg" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div class="modal-title-box">
            <ClipboardList :size="17" class="modal-title-icon" />
            <div>
              <h3>创建新布控任务</h3>
              <p>绑定人像布控名单与视频流/摄像头，配置多模态比对策略及频控冷却规则</p>
            </div>
          </div>
        </div>
        <form @submit.prevent="handleCreateTask">
          <div class="modal-body">
            <!-- 基础信息 -->
            <div class="form-grid-2col">
              <label class="form-field">
                <span class="field-label">任务名称 <em class="required">*</em></span>
                <input
                  v-model="form.name"
                  placeholder="例如: 1号园区主出入口实时布控"
                  class="field-input"
                  required
                  autofocus
                />
              </label>
              <label class="form-field">
                <span class="field-label">告警等级 <em class="required">*</em></span>
                <select v-model="form.alert_level" class="field-input">
                  <option value="critical">严重 (Critical - 重点预警)</option>
                  <option value="warning">警告 (Warning - 标准关注)</option>
                  <option value="info">提示 (Info - 常规记录)</option>
                </select>
              </label>
            </div>

            <!-- 绑定源配置 -->
            <div class="form-grid-3col" style="margin-top: 12px;">
              <label class="form-field">
                <span class="field-label">关联布控名单 <em class="required">*</em></span>
                <select v-model="form.watchlist_id" class="field-input" required>
                  <option value="" disabled>请选择布控名单库</option>
                  <option
                    v-for="wl in watchlists"
                    :key="wl.watchlist_id"
                    :value="wl.watchlist_id"
                  >
                    {{ wl.name }} ({{ wl.category === 'blacklist' ? '黑名单' : wl.category === 'whitelist' ? '白名单' : '自定义' }})
                  </option>
                </select>
              </label>

              <label class="form-field">
                <span class="field-label">监控视频源 <em class="required">*</em></span>
                <select v-model="form.source_id" class="field-input" required>
                  <option value="" disabled>请选择媒体源</option>
                  <option
                    v-for="src in sources"
                    :key="src.source_id"
                    :value="src.source_id"
                  >
                    {{ src.name }}
                  </option>
                </select>
              </label>

              <label class="form-field">
                <span class="field-label">摄像头通道 <em class="required">*</em></span>
                <select v-model="form.camera_id" class="field-input" required>
                  <option value="" disabled>请选择摄像头</option>
                  <option
                    v-for="cam in cameras"
                    :key="cam.camera_id"
                    :value="cam.camera_id"
                  >
                    {{ cam.display_name }} ({{ cam.camera_id }})
                  </option>
                </select>
              </label>
            </div>

            <!-- 比对与频控阈值 -->
            <div class="form-section-title" style="margin-top: 14px;">
              <Sliders :size="13" />
              <span>多模态比对阈值与频控策略</span>
            </div>

            <div class="form-grid-3col" style="margin-top: 8px;">
              <label class="form-field">
                <span class="field-label">人脸比对相似度阈值</span>
                <input
                  v-model.number="form.face_threshold"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  class="field-input mono"
                />
              </label>
              <label class="form-field">
                <span class="field-label">人体 ReID 相似度阈值</span>
                <input
                  v-model.number="form.body_threshold"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  class="field-input mono"
                />
              </label>
              <label class="form-field">
                <span class="field-label">频控去重冷却时间 (秒)</span>
                <input
                  v-model.number="form.cooldown_seconds"
                  type="number"
                  min="1"
                  max="86400"
                  class="field-input mono"
                />
              </label>
            </div>
          </div>

          <div class="modal-actions">
            <button
              type="button"
              class="button secondary tiny-btn"
              @click="showCreateModal = false"
            >
              取消
            </button>
            <button
              type="submit"
              class="button primary tiny-btn"
              :disabled="mutating || !isReadyToSubmit"
            >
              <Plus :size="13" />确认创建布控任务
            </button>
          </div>
        </form>
      </div>
    </div>
  </main>
</template>

<style scoped>
.task-page {
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

/* 顶部过滤控制栏 */
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

.filter-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--muted, #64716d);
}

.filter-icon {
  color: var(--muted, #64716d);
}

.filter-label {
  font-weight: 500;
  white-space: nowrap;
}

.filter-select {
  height: 28px;
  padding: 0 8px;
  font-size: 11.5px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #fafbfb;
  color: var(--graphite, #17211f);
  cursor: pointer;
}
.filter-select:focus {
  border-color: var(--color-accent, #087682);
  outline: none;
}

.search-box {
  position: relative;
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}

.search-icon {
  position: absolute;
  left: 9px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--muted, #64716d);
  pointer-events: none;
  z-index: 1;
}

.search-input {
  height: 28px;
  line-height: 28px;
  padding: 0 10px 0 30px !important;
  font-size: 11.5px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #ffffff;
  color: var(--graphite, #17211f);
  width: 220px;
  box-sizing: border-box !important;
  outline: none;
}
.search-input:focus {
  border-color: var(--color-accent, #087682);
  background: #ffffff;
  outline: none;
  box-shadow: 0 0 0 2px var(--color-accent-soft, #e4f1f1);
}
.search-input::placeholder {
  color: var(--muted, #64716d);
  opacity: 0.75;
}

.count-badge {
  background: #edf2f0;
  color: #45534f;
  font-size: 11px;
  padding: 3px 7px;
  border-radius: 4px;
}

/* 任务列表面板与表格 */
.task-table-panel {
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  overflow: hidden;
}

.table-scroll {
  overflow-x: auto;
  background: #ffffff;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
}

.data-table th {
  height: 28px;
  padding: 2px 8px;
  font-size: 11.5px;
  font-weight: 600;
  background: #fafbfb;
  color: var(--muted, #64716d);
  border: 1px solid var(--line, #e2e8e6);
  white-space: nowrap;
  vertical-align: middle;
}

.data-table td {
  height: 28px;
  padding: 4px 8px;
  border: 1px solid var(--line, #e2e8e6);
  vertical-align: middle;
}

.task-title-cell {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.task-title-cell strong {
  font-size: 12.5px;
  color: var(--graphite, #17211f);
}

.sub-id {
  font-size: 10.5px;
}

.watchlist-tags-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.watchlist-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  background: #eef2f1;
  color: #2c3e38;
  padding: 1px 6px;
  border-radius: 3px;
}

.binding-info-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.binding-row {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.binding-icon {
  color: var(--color-accent, #087682);
}

.thresholds-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}

.thresh-item strong {
  color: var(--color-accent, #087682);
}

.divider {
  color: var(--line-strong, #b7c2bd);
}

.alert-level-badge {
  font-size: 10.5px;
  padding: 1px 6px;
  border-radius: 3px;
}
.alert-level-badge.critical {
  background: #fee2e2;
  color: #991b1b;
}
.alert-level-badge.warning {
  background: #fef3c7;
  color: #92400e;
}
.alert-level-badge.info {
  background: #e0f2fe;
  color: #0369a1;
}

.status-badge {
  font-size: 10.5px;
  padding: 1px 6px;
  border-radius: 3px;
}
.status-badge.active {
  background: #dcfce7;
  color: #166534;
}
.status-badge.paused {
  background: #fef3c7;
  color: #92400e;
}
.status-badge.stopped,
.status-badge.draft {
  background: #f1f5f9;
  color: #64748b;
}

.table-actions {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.action-btn {
  height: 22px;
  padding: 0 6px;
  font-size: 11px;
  gap: 3px;
}

/* 空状态 */
.empty-cell {
  background: #fafbfb;
  text-align: center;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 36px 16px;
  gap: 8px;
  color: var(--muted, #64716d);
  text-align: center;
}

.empty-icon {
  color: #b7c2bd;
}

.empty-state p {
  margin: 0;
  font-size: 12px;
}

.mono {
  font-family: var(--font-mono, monospace);
  font-size: 11.5px;
}

.muted {
  color: var(--muted, #64716d);
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  100% {
    transform: rotate(360deg);
  }
}

/* 模态弹窗 */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(17, 26, 24, 0.45);
  display: grid;
  place-items: center;
  z-index: 1000;
  padding: 16px;
}

.modal-dialog {
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 8px;
  box-shadow: 0 20px 50px rgba(15, 23, 21, 0.22);
  width: min(780px, 95vw);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  background: #fafbfb;
}

.modal-title-box {
  display: flex;
  align-items: center;
  gap: 10px;
}

.modal-title-icon {
  color: var(--color-accent, #087682);
}

.modal-title-box h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--graphite, #17211f);
}

.modal-title-box p {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--muted, #64716d);
}

.modal-body {
  padding: 16px 18px;
}

.form-grid-2col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.form-grid-3col {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
}

.form-section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--graphite, #17211f);
  padding-bottom: 4px;
  border-bottom: 1px dashed var(--line, #e2e8e6);
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-label {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--graphite, #17211f);
}

.required {
  color: #dc2626;
  font-style: normal;
}

.field-input {
  height: 28px;
  padding: 0 8px;
  font-size: 11.5px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #ffffff;
  color: var(--graphite, #17211f);
  box-sizing: border-box;
  width: 100%;
}
.field-input:focus {
  border-color: var(--color-accent, #087682);
  outline: none;
}

.modal-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid var(--line, #e2e8e6);
  background: #fafbfb;
}
</style>
