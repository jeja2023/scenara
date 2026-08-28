<script setup lang="ts">
import { computed, onMounted, reactive, ref, type Ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { Check, GitMerge, RotateCcw, Scissors, Trash2, X } from "@lucide/vue";
import { api, userFacingError } from "../api";
import type {
  CameraRecord,
  LongTermIdentity,
  TimelineEntry,
  TrajectorySegment,
  TrajectoryStatus,
} from "../types";

const identities = ref<LongTermIdentity[]>([]);
const total = ref(0);
const cameras = ref<CameraRecord[]>([]);
const segments = ref<TrajectorySegment[]>([]);
const timeline = ref<TimelineEntry[]>([]);
const selectedId = ref("");
const mergeSelection = ref<string[]>([]);
const splitSelection = ref<string[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const message = ref("");
const filters = reactive({ status: "", camera_id: "", since: "", until: "" });
const renameDraft = ref("");

const selected = computed(
  () =>
    identities.value.find((item) => item.identity_id === selectedId.value) ??
    null,
);

function clearFeedback(): void {
  error.value = "";
  message.value = "";
}

function formatTime(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString("zh-CN", { hour12: false });
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)} 秒`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)} 分钟`;
  return `${(seconds / 3600).toFixed(1)} 小时`;
}

function statusLabel(status: TrajectoryStatus): string {
  return (
    { auto: "待研判", confirmed: "已确认", rejected: "已否决" }[status] ??
    status
  );
}

function statusClass(status: TrajectoryStatus): string {
  if (status === "confirmed") return "active";
  if (status === "rejected") return "error-badge";
  return "warn-badge";
}

function methodLabel(method: string): string {
  return (
    { new_identity: "首次出现", reid: "跨镜关联", manual: "人工调整" }[
      method
    ] ?? method
  );
}

function cameraName(cameraId: string): string {
  return (
    cameras.value.find((item) => item.camera_id === cameraId)?.display_name ||
    cameraId
  );
}

function identityQuery(): string {
  const params = new URLSearchParams({ limit: "200" });
  if (filters.status) params.set("status", filters.status);
  if (filters.camera_id) params.set("camera_id", filters.camera_id);
  if (filters.since)
    params.set("since", String(Date.parse(filters.since) / 1000));
  if (filters.until)
    params.set("until", String(Date.parse(filters.until) / 1000));
  return params.toString();
}

async function loadDetail(): Promise<void> {
  if (!selectedId.value) {
    segments.value = [];
    timeline.value = [];
    return;
  }
  const identity = encodeURIComponent(selectedId.value);
  const [segmentPage, entries] = await Promise.all([
    api<{ items: TrajectorySegment[] }>(
      `/api/v1/portrait/trajectories/identities/${identity}/segments?limit=500`,
    ),
    api<TimelineEntry[]>(
      `/api/v1/portrait/trajectories/identities/${identity}/timeline`,
    ),
  ]);
  segments.value = segmentPage.items;
  timeline.value = entries;
  splitSelection.value = [];
}

async function refresh(): Promise<void> {
  loading.value = true;
  clearFeedback();
  try {
    const [page, cameraList] = await Promise.all([
      api<{ items: LongTermIdentity[]; total: number }>(
        `/api/v1/portrait/trajectories/identities?${identityQuery()}`,
      ),
      api<CameraRecord[]>("/api/v1/portrait/cameras"),
    ]);
    identities.value = page.items;
    total.value = page.total;
    cameras.value = cameraList;
    if (
      !identities.value.some((item) => item.identity_id === selectedId.value)
    ) {
      selectedId.value = identities.value[0]?.identity_id ?? "";
    }
    renameDraft.value = selected.value?.display_name ?? "";
    await loadDetail();
  } catch (caught) {
    error.value = userFacingError(caught, "长期轨迹加载失败");
  } finally {
    loading.value = false;
  }
}

function resetFilters(): void {
  filters.status = "";
  filters.camera_id = "";
  filters.since = "";
  filters.until = "";
  void refresh();
}

async function select(identityId: string): Promise<void> {
  selectedId.value = identityId;
  renameDraft.value = selected.value?.display_name ?? "";
  clearFeedback();
  try {
    await loadDetail();
  } catch (caught) {
    error.value = userFacingError(caught, "轨迹详情加载失败");
  }
}

async function patchIdentity(
  body: Record<string, unknown>,
  note: string,
): Promise<void> {
  if (!selectedId.value) return;
  saving.value = true;
  clearFeedback();
  try {
    await api<LongTermIdentity>(
      `/api/v1/portrait/trajectories/identities/${encodeURIComponent(selectedId.value)}`,
      { method: "PATCH", body: JSON.stringify(body) },
    );
    message.value = note;
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught, "身份更新失败");
  } finally {
    saving.value = false;
  }
}

async function removeIdentity(): Promise<void> {
  if (!selectedId.value) return;
  saving.value = true;
  clearFeedback();
  try {
    await api<void>(
      `/api/v1/portrait/trajectories/identities/${encodeURIComponent(selectedId.value)}`,
      { method: "DELETE" },
    );
    selectedId.value = "";
    message.value = "身份及其生物特征已删除";
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught, "身份删除失败");
  } finally {
    saving.value = false;
  }
}

async function mergeInto(): Promise<void> {
  const sources = mergeSelection.value.filter(
    (item) => item !== selectedId.value,
  );
  if (!selectedId.value || !sources.length) return;
  saving.value = true;
  clearFeedback();
  try {
    await api<LongTermIdentity>(
      "/api/v1/portrait/trajectories/identities/merge",
      {
        method: "POST",
        body: JSON.stringify({
          target_identity_id: selectedId.value,
          source_identity_ids: sources,
        }),
      },
    );
    mergeSelection.value = [];
    message.value = "已将所选身份合并到当前身份";
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught, "身份合并失败");
  } finally {
    saving.value = false;
  }
}

async function splitOut(): Promise<void> {
  if (!selectedId.value || !splitSelection.value.length) return;
  saving.value = true;
  clearFeedback();
  try {
    const created = await api<LongTermIdentity>(
      "/api/v1/portrait/trajectories/identities/split",
      {
        method: "POST",
        body: JSON.stringify({
          source_identity_id: selectedId.value,
          segment_ids: splitSelection.value,
        }),
      },
    );
    splitSelection.value = [];
    selectedId.value = created.identity_id;
    message.value = "已拆分为新身份";
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught, "片段拆分失败");
  } finally {
    saving.value = false;
  }
}

function toggle(target: Ref<string[]>, id: string): void {
  target.value = target.value.includes(id)
    ? target.value.filter((item) => item !== id)
    : [...target.value, id];
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page">
    <p v-if="error" class="callout error">{{ error }}</p>
    <p v-if="message" class="callout success">{{ message }}</p>

    <!-- 顶部单行紧凑过滤工具栏 -->
    <div class="panel filters-panel">
      <div class="filter-toolbar">
        <div class="filter-item">
          <span class="filter-label">研判状态</span>
          <select v-model="filters.status" class="filter-select" @change="refresh">
            <option value="">全部</option>
            <option value="auto">待研判</option>
            <option value="confirmed">已确认</option>
            <option value="rejected">已否决</option>
          </select>
        </div>
        <div class="filter-item">
          <span class="filter-label">抓拍机位</span>
          <select v-model="filters.camera_id" class="filter-select" @change="refresh">
            <option value="">全部机位</option>
            <option
              v-for="camera in cameras"
              :key="camera.camera_id"
              :value="camera.camera_id"
            >
              {{ camera.display_name || camera.camera_id }}
            </option>
          </select>
        </div>
        <div class="filter-item">
          <span class="filter-label">起始时间</span>
          <input
            v-model="filters.since"
            type="datetime-local"
            class="filter-input date-input"
            @change="refresh"
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">截止时间</span>
          <input
            v-model="filters.until"
            type="datetime-local"
            class="filter-input date-input"
            @change="refresh"
          />
        </div>
        <div class="filter-actions">
          <button class="button secondary filter-btn" @click="resetFilters">
            <RotateCcw :size="13" />重置
          </button>
        </div>
      </div>
    </div>

    <div class="trajectory-grid">
      <!-- 1. 身份列表 -->
      <section class="panel identity-panel">
        <div class="panel-header">
          <div class="header-left">
            <h2>身份列表</h2>
            <span class="badge">{{ total }}</span>
          </div>
        </div>
        <div class="identity-list">
          <div
            v-for="identity in identities"
            :key="identity.identity_id"
            class="identity-row"
            :class="{ selected: identity.identity_id === selectedId }"
          >
            <input
              type="checkbox"
              class="checkbox-input"
              :checked="mergeSelection.includes(identity.identity_id)"
              :title="'选择以合并到当前身份'"
              @change="toggle(mergeSelection, identity.identity_id)"
            />
            <button
              type="button"
              class="identity-main"
              @click="select(identity.identity_id)"
            >
              <div class="identity-top">
                <strong class="identity-name">{{ identity.display_name || identity.identity_id }}</strong>
                <span class="badge status-badge" :class="statusClass(identity.status)">
                  {{ statusLabel(identity.status) }}
                </span>
              </div>
              <small class="identity-sub">
                {{ identity.segment_count }} 段 · {{ identity.camera_ids.length }} 机位 · {{ identity.modalities.join("+") || "无特征" }}
              </small>
              <small class="identity-time">最近出现 {{ formatTime(identity.last_seen_at) }}</small>
            </button>
          </div>
          <div v-if="!identities.length" class="empty-tip">还没有长期轨迹身份</div>
        </div>

        <div v-if="mergeSelection.length" class="panel-footer merge-bar">
          <span class="muted-text">已选 {{ mergeSelection.length }} 个身份</span>
          <button
            class="button primary merge-btn"
            :disabled="saving || !selectedId"
            @click="mergeInto"
          >
            <GitMerge :size="13" />合并到当前身份
          </button>
        </div>
      </section>

      <!-- 2. 选定身份的研判与详情 -->
      <section v-if="selected" class="panel detail-panel">
        <div class="panel-header">
          <div class="header-left">
            <h2>{{ selected.display_name || selected.identity_id }}</h2>
            <span class="badge status-badge" :class="statusClass(selected.status)">
              {{ statusLabel(selected.status) }}
            </span>
          </div>
          <small class="header-time-range">
            首次 {{ formatTime(selected.first_seen_at) }} · 最近 {{ formatTime(selected.last_seen_at) }}
          </small>
        </div>

        <!-- 研判工具条 -->
        <div class="adjudication-bar">
          <div class="rename-box">
            <span class="field-label">身份命名</span>
            <input
              v-model="renameDraft"
              class="field-input rename-input"
              maxlength="256"
              placeholder="例如：张三"
              @keyup.enter="patchIdentity({ display_name: renameDraft }, '名称已更新')"
            />
            <button
              class="button secondary action-btn"
              :disabled="saving || renameDraft === selected.display_name"
              @click="patchIdentity({ display_name: renameDraft }, '名称已更新')"
            >
              保存名称
            </button>
          </div>
          <div class="status-actions">
            <button
              class="button primary action-btn"
              :disabled="saving || selected.status === 'confirmed'"
              @click="patchIdentity({ status: 'confirmed' }, '身份已确认')"
            >
              <Check :size="13" />确认
            </button>
            <button
              class="button secondary action-btn"
              :disabled="saving || selected.status === 'rejected'"
              @click="patchIdentity({ status: 'rejected' }, '身份已否决')"
            >
              <X :size="13" />否决
            </button>
            <button
              class="button secondary action-btn danger-btn"
              :disabled="saving"
              @click="removeIdentity"
            >
              <Trash2 :size="13" />删除
            </button>
          </div>
        </div>

        <!-- 跨机位时间线 -->
        <div class="subhead-bar">
          <strong>跨摄像头轨迹时间线</strong>
          <span class="muted-text">{{ timeline.length }} 次出现</span>
        </div>
        <ol class="timeline">
          <li v-for="entry in timeline" :key="entry.segment_id" class="timeline-item">
            <div class="timeline-dot" />
            <div class="timeline-content">
              <strong class="timeline-cam">{{ entry.camera_name || cameraName(entry.camera_id) }}</strong>
              <small class="timeline-meta">
                {{ formatTime(entry.first_seen_at) }} · 停留 {{ formatDuration(entry.duration_seconds) }} · {{ methodLabel(entry.match_method) }}
              </small>
              <small v-if="entry.transition_seconds !== null" class="timeline-gap">
                距上次出现 {{ formatDuration(entry.transition_seconds) }}
              </small>
            </div>
          </li>
          <li v-if="!timeline.length" class="empty-tip">该身份还没有轨迹片段</li>
        </ol>

        <!-- 轨迹片段与拆分 -->
        <div class="subhead-bar">
          <strong>轨迹片段列表</strong>
          <button
            class="button secondary action-btn"
            :disabled="saving || !splitSelection.length"
            @click="splitOut"
          >
            <Scissors :size="13" />拆分所选片段 ({{ splitSelection.length }})
          </button>
        </div>
        <div class="segment-list">
          <label
            v-for="segment in segments"
            :key="segment.segment_id"
            class="segment-row"
          >
            <input
              type="checkbox"
              class="checkbox-input"
              :checked="splitSelection.includes(segment.segment_id)"
              @change="toggle(splitSelection, segment.segment_id)"
            />
            <div class="segment-info">
              <strong class="segment-cam">{{ cameraName(segment.camera_id) }}</strong>
              <small class="segment-meta">
                {{ formatTime(segment.first_seen_at) }} · {{ segment.frame_count }} 帧 · 质量 {{ segment.track_quality.toFixed(2) }} · {{ methodLabel(segment.match_method) }}
                {{ segment.match_method === "reid" ? `（${segment.match_score.toFixed(3)}）` : "" }}
              </small>
            </div>
          </label>
          <div v-if="!segments.length" class="empty-tip">没有片段</div>
        </div>
      </section>
      <section v-else class="panel empty-panel">
        <div class="empty-tip">请在左侧选择一个长期轨迹身份</div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* 顶部紧凑过滤工具栏 */
.filters-panel {
  padding: 10px 14px;
  background: #ffffff;
}

.filter-toolbar {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.filter-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.filter-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--graphite, #17211f);
  white-space: nowrap;
}

.filter-input,
.filter-select {
  height: 28px;
  line-height: 28px;
  padding: 0 8px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 5px;
  background: #ffffff;
  color: var(--graphite, #17211f);
  font-size: 11.5px;
  outline: none;
  box-sizing: border-box;
  transition: all 0.15s ease;
}

.filter-input:focus,
.filter-select:focus {
  border-color: var(--primary, #0ea5e9);
  box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.12);
}

.date-input {
  width: 170px;
}

.filter-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.filter-btn {
  height: 28px;
  padding: 0 10px;
  font-size: 11.5px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* 主栅格 */
.trajectory-grid {
  display: grid;
  grid-template-columns: minmax(300px, 0.9fr) minmax(0, 1.3fr);
  gap: 14px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  margin-bottom: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-header h2 {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--graphite, #17211f);
  margin: 0;
}

.header-time-range {
  font-size: 11px;
  color: var(--muted, #64716d);
}

/* 身份列表 */
.identity-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 520px;
  overflow-y: auto;
}

.identity-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 5px;
  background: #ffffff;
  transition: all 0.15s ease;
}

.identity-row:hover {
  background: #fafbfb;
  border-color: #cbd5e1;
}

.identity-row.selected {
  background: var(--teal-soft, #e0f2fe);
  border-color: var(--primary, #0ea5e9);
}

.identity-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  border: none;
  background: transparent;
  padding: 0;
  text-align: left;
  cursor: pointer;
  min-width: 0;
}

.identity-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.identity-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--graphite, #17211f);
}

.identity-sub {
  font-size: 11px;
  color: var(--muted, #64716d);
}

.identity-time {
  font-size: 10.5px;
  color: #94a3b8;
}

.merge-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: #fafbfb;
  border-top: 1px solid var(--line, #e2e8e6);
  margin-top: 10px;
}

.merge-btn {
  height: 26px;
  padding: 0 10px;
  font-size: 11.5px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* 研判栏 */
.adjudication-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 5px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.rename-box {
  display: flex;
  align-items: center;
  gap: 6px;
}

.rename-input {
  width: 130px;
}

.status-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.action-btn {
  height: 24px;
  padding: 0 8px;
  font-size: 11px;
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.danger-btn {
  color: #ef4444;
}

.danger-btn:hover {
  background: rgba(239, 68, 68, 0.1);
}

/* 时间线 */
.subhead-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--graphite, #17211f);
  margin: 12px 0 8px;
}

.timeline {
  list-style: none;
  padding: 0;
  margin: 0 0 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.timeline-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 10px;
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
}

.timeline-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary, #0ea5e9);
  margin-top: 6px;
  flex-shrink: 0;
}

.timeline-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.timeline-cam {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--graphite, #17211f);
}

.timeline-meta {
  font-size: 11px;
  color: var(--muted, #64716d);
}

.timeline-gap {
  font-size: 10.5px;
  color: #0b7557;
}

/* 片段列表 */
.segment-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 200px;
  overflow-y: auto;
}

.segment-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.12s ease;
}

.segment-row:hover {
  background: #f1f5f4;
}

.segment-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.segment-cam {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--graphite, #17211f);
}

.segment-meta {
  font-size: 10.5px;
  color: var(--muted, #64716d);
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 18px;
  line-height: 18px;
  padding: 0 6px;
  font-size: 10.5px;
  white-space: nowrap;
}

.empty-tip {
  font-size: 11.5px;
  color: var(--muted, #64716d);
  padding: 16px;
  text-align: center;
}

.empty-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 240px;
}

.checkbox-input {
  cursor: pointer;
}

@media (max-width: 900px) {
  .trajectory-grid {
    grid-template-columns: 1fr;
  }
}
</style>
