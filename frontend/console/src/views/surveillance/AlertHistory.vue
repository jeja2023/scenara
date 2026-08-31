<script setup lang="ts">
import {
  Camera,
  Check,
  Clock,
  ExternalLink,
  Filter,
  RefreshCw,
  Search,
  ShieldAlert,
  X,
} from "@lucide/vue";
import { onMounted, reactive, ref } from "vue";

import { userFacingError } from "../../api";
import {
  createAlertFeedback,
  listAlerts,
  triageAlert,
} from "../../api/surveillance";
import { labelModality, labelSurveillanceAlertStatus } from "../../labels";
import type { SurveillanceAlert } from "../../types";

const alerts = ref<SurveillanceAlert[]>([]);
const total = ref(0);
const loading = ref(false);
const mutatingId = ref<string | null>(null);
const error = ref("");
const filters = reactive({
  status: "",
  camera_id: "",
});

function format(value: number): string {
  if (!value) return "-";
  return new Date(value * 1000).toLocaleString("zh-CN", {
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function query(): string {
  const params = new URLSearchParams({ limit: "100" });
  if (filters.status) params.set("status", filters.status);
  if (filters.camera_id.trim()) params.set("camera_id", filters.camera_id.trim());
  return params.toString();
}

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const page = await listAlerts(query());
    alerts.value = page.items;
    total.value = page.total;
  } catch (caught) {
    error.value = userFacingError(caught);
  } finally {
    loading.value = false;
  }
}

async function handleTriage(
  alert: SurveillanceAlert,
  status: "confirmed" | "false_positive" | "ignored",
): Promise<void> {
  mutatingId.value = alert.alert_id;
  try {
    await triageAlert(alert.alert_id, {
      expected_revision: alert.revision,
      status,
      reason:
        status === "confirmed"
          ? "人工确认命中"
          : status === "false_positive"
            ? "人工排除误报"
            : "人工忽略",
    });
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught);
  } finally {
    mutatingId.value = null;
  }
}

async function handleCreateFeedback(alert: SurveillanceAlert): Promise<void> {
  try {
    await createAlertFeedback(alert.alert_id);
    alert.triage_reason = (alert.triage_reason || "") + " (已生成反馈样本)";
  } catch (caught) {
    error.value = userFacingError(caught, "无法创建待审核反馈");
  }
}

function artifactUrl(alert: SurveillanceAlert): string | null {
  return alert.snapshot_artifact_id
    ? `/api/v1/runs/${encodeURIComponent(alert.run_id)}/artifacts/${encodeURIComponent(alert.snapshot_artifact_id)}`
    : null;
}

onMounted(() => void refresh());
</script>

<template>
  <main class="page alert-page">
    <p v-if="error" class="error-banner">{{ error }}</p>

    <!-- 顶部操作与筛选工具栏 -->
    <div class="filter-controls">
      <div class="filter-left">
        <label class="filter-item">
          <Filter :size="12" class="filter-icon" />
          <span class="filter-label">研判状态:</span>
          <select v-model="filters.status" class="filter-select" @change="refresh">
            <option value="">全部状态 (All)</option>
            <option value="pending">待处置 (Pending)</option>
            <option value="confirmed">已确认命中 (Confirmed)</option>
            <option value="false_positive">误报排除 (False Positive)</option>
            <option value="ignored">已忽略 (Ignored)</option>
          </select>
        </label>

        <div class="search-box">
          <Search :size="13" class="search-icon" />
          <input
            v-model.trim="filters.camera_id"
            placeholder="搜索摄像头编号..."
            class="search-input"
            @keyup.enter="refresh"
          />
        </div>

        <span class="badge count-badge">共 {{ total }} 条告警记录</span>
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
      </div>
    </div>

    <!-- 告警研判卡片列表 -->
    <div class="alerts-cards-list">
      <article
        v-for="alert in alerts"
        :key="alert.alert_id"
        class="panel alert-card-item"
      >
        <!-- 左侧：告警抓拍图像 -->
        <div class="snapshot-box">
          <img
            v-if="artifactUrl(alert)"
            :src="artifactUrl(alert)!"
            alt="告警抓拍"
            class="snapshot-img"
          />
          <div v-else class="snapshot-placeholder">
            <Camera :size="24" class="placeholder-icon" />
            <span>无抓拍图</span>
          </div>

          <div class="score-overlay-badge">
            <span>相似度</span>
            <strong>{{ (alert.match_score * 100).toFixed(1) }}%</strong>
          </div>
        </div>

        <!-- 右侧：告警研判详细信息 -->
        <div class="alert-details-box">
          <div class="card-header-row">
            <div class="header-left">
              <div class="camera-title">
                <Camera :size="13" class="title-icon" />
                <strong>{{ alert.camera_id }}</strong>
              </div>
              <span class="badge modality-badge">{{ labelModality(alert.modality) }}</span>
              <span class="time-text">
                <Clock :size="11" />
                {{ format(alert.triggered_at) }}
              </span>
            </div>

            <span class="badge status-badge" :class="alert.status">
              {{ labelSurveillanceAlertStatus(alert.status) }}
            </span>
          </div>

          <!-- 核心属性元数据网格 -->
          <div class="meta-grid">
            <div class="meta-item">
              <span class="meta-label">目标身份 (ID)</span>
              <span class="meta-value mono">{{ alert.portrait_identity_id }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">所属任务</span>
              <span class="meta-value">{{ alert.task_id }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">累计频次</span>
              <span class="meta-value">
                已出现 <strong>{{ alert.occurrence_count }}</strong> 次 (最高 {{ (alert.max_score * 100).toFixed(1) }}%)
              </span>
            </div>
            <div class="meta-item">
              <span class="meta-label">关联轨迹</span>
              <span class="meta-value mono muted">
                {{ alert.trajectory_identity_id || "暂无轨迹关联" }}
              </span>
            </div>
          </div>

          <!-- 底部操作与研判处置栏 -->
          <div class="card-footer-actions">
            <div v-if="alert.status === 'pending'" class="pending-actions">
              <button
                class="button primary tiny-btn triage-confirm-btn"
                :disabled="mutatingId === alert.alert_id"
                @click="handleTriage(alert, 'confirmed')"
              >
                <Check :size="12" />确认命中
              </button>
              <button
                class="button danger tiny-btn triage-reject-btn"
                :disabled="mutatingId === alert.alert_id"
                @click="handleTriage(alert, 'false_positive')"
              >
                <X :size="12" />排除误报
              </button>
              <button
                class="button secondary tiny-btn"
                :disabled="mutatingId === alert.alert_id"
                @click="handleTriage(alert, 'ignored')"
              >
                忽略
              </button>
            </div>

            <div v-else class="triaged-info-row">
              <span class="triage-reason-badge">
                研判结论: <strong>{{ alert.triage_reason }}</strong>
                <small v-if="alert.triaged_by"> · 处置人: {{ alert.triaged_by }}</small>
              </span>

              <button
                v-if="alert.status === 'false_positive'"
                class="button secondary tiny-btn feedback-btn"
                @click="handleCreateFeedback(alert)"
              >
                <ExternalLink :size="11" />创建待审核难例样本
              </button>
            </div>
          </div>
        </div>
      </article>

      <div v-if="!alerts.length" class="panel empty-state">
        <ShieldAlert :size="36" class="empty-icon" />
        <p>当前筛选条件下暂无告警研判记录</p>
      </div>
    </div>
  </main>
</template>

<style scoped>
.alert-page {
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
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: 8px;
  color: var(--muted, #64716d);
  pointer-events: none;
}

.search-input {
  height: 28px;
  padding: 0 8px 0 26px;
  font-size: 11.5px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #fafbfb;
  color: var(--graphite, #17211f);
  width: 180px;
}
.search-input:focus {
  border-color: var(--color-accent, #087682);
  background: #ffffff;
  outline: none;
}

.count-badge {
  background: #edf2f0;
  color: #45534f;
  font-size: 11px;
  padding: 3px 7px;
  border-radius: 4px;
}

/* 告警研判卡片列表 */
.alerts-cards-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.alert-card-item {
  display: grid;
  grid-template-columns: 160px 1fr;
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  overflow: hidden;
  transition: all 0.15s ease;
}

.alert-card-item:hover {
  border-color: var(--line-strong, #b7c2bd);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

@media (max-width: 720px) {
  .alert-card-item {
    grid-template-columns: 1fr;
  }
}

/* 抓拍照片容器 */
.snapshot-box {
  position: relative;
  background: #f1f4f3;
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.snapshot-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.snapshot-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  color: var(--muted, #64716d);
  font-size: 10.5px;
}

.placeholder-icon {
  color: #b7c2bd;
}

.score-overlay-badge {
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

.score-overlay-badge strong {
  color: #34d399;
  font-size: 11.5px;
}

/* 右侧研判详情 */
.alert-details-box {
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.camera-title {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.camera-title strong {
  font-size: 13px;
  color: var(--graphite, #17211f);
}

.title-icon {
  color: var(--color-accent, #087682);
}

.modality-badge {
  font-size: 10.5px;
  background: #eef2f1;
  color: #2c3e38;
  padding: 1px 6px;
  border-radius: 3px;
}

.time-text {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  color: var(--muted, #64716d);
}

.status-badge {
  font-size: 10.5px;
  padding: 1px 7px;
  border-radius: 3px;
  font-weight: 500;
}
.status-badge.pending {
  background: #fef3c7;
  color: #92400e;
}
.status-badge.confirmed {
  background: #dcfce7;
  color: #166534;
}
.status-badge.false_positive {
  background: #fee2e2;
  color: #991b1b;
}
.status-badge.ignored {
  background: #f1f5f9;
  color: #64748b;
}

/* 属性元数据 */
.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 6px 12px;
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  padding: 6px 10px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}

.meta-label {
  color: var(--muted, #64716d);
  flex-shrink: 0;
}

.meta-value {
  color: var(--graphite, #17211f);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta-value strong {
  color: var(--color-accent, #087682);
}

/* 底部操作区 */
.card-footer-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  margin-top: auto;
  padding-top: 4px;
}

.pending-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.triage-confirm-btn {
  background: #16a34a;
  border-color: #16a34a;
}
.triage-confirm-btn:hover {
  background: #15803d;
}

.triage-reject-btn {
  background: #dc2626;
  border-color: #dc2626;
}
.triage-reject-btn:hover {
  background: #b91c1c;
}

.triaged-info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 8px;
}

.triage-reason-badge {
  font-size: 11px;
  color: var(--graphite, #17211f);
}

.triage-reason-badge strong {
  color: var(--color-accent, #087682);
}

.feedback-btn {
  font-size: 11px;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 16px;
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
</style>
