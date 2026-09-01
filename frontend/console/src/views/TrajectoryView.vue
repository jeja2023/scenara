<script setup lang="ts">
import {
  Camera,
  Check,
  Clock,
  Filter,
  GitMerge,
  Layers,
  MapPin,
  RefreshCw,
  RotateCcw,
  Route,
  Scissors,
  Trash2,
  UserCheck,
  UserRound,
  Users,
  X,
} from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";

import { api, userFacingError } from "../api";
import DataTable from "../components/DataTable.vue";
import type {
  CameraRecord,
  LongTermIdentity,
  TableColumn,
  TimelineEntry,
  TrajectorySegment,
  TrajectoryStatus,
} from "../types";

const segmentColumns: TableColumn<TrajectorySegment>[] = [
  { key: "segment_id", label: "片段标识", class: "mono", width: "160px" },
  { key: "camera_id", label: "抓拍机位", width: "160px" },
  { key: "time_range", label: "时序区间", width: "200px" },
  {
    key: "track_quality",
    label: "跟踪质量",
    width: "100px",
    align: "center",
    headerAlign: "center",
  },
  {
    key: "match_method",
    label: "匹配方式",
    width: "120px",
    align: "center",
    headerAlign: "center",
  },
  {
    key: "match_score",
    label: "相似度",
    width: "100px",
    align: "center",
    headerAlign: "center",
  },
  {
    key: "actions",
    label: "拆分操作",
    width: "100px",
    align: "right",
    headerAlign: "right",
  },
];

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

const segmentPageSize = ref(10);

const selected = computed(
  () =>
    identities.value.find((item) => item.identity_id === selectedId.value) ??
    null,
);

const confirmedCount = computed(
  () => identities.value.filter((i) => i.status === "confirmed").length,
);

const pendingCount = computed(
  () => identities.value.filter((i) => i.status === "auto").length,
);

function clearFeedback(): void {
  error.value = "";
  message.value = "";
}

function notifySuccess(msg: string): void {
  message.value = msg;
  setTimeout(() => {
    message.value = "";
  }, 3500);
}

function formatTime(timestamp: number): string {
  if (!timestamp) return "-";
  return new Date(timestamp * 1000).toLocaleString("zh-CN", { hour12: false });
}

function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return "0 秒";
  if (seconds < 60) return `${seconds.toFixed(1)} 秒`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)} 分钟`;
  return `${(seconds / 3600).toFixed(1)} 小时`;
}

function statusLabel(status: TrajectoryStatus): string {
  switch (status) {
    case "auto":
      return "待研判 (Auto)";
    case "confirmed":
      return "已确认 (Confirmed)";
    case "rejected":
      return "已否决 (Rejected)";
    default:
      return status || "-";
  }
}

function methodLabel(method: string): string {
  switch (method) {
    case "new_identity":
      return "首次出现";
    case "reid":
      return "跨镜 ReID";
    case "manual":
      return "人工关联";
    default:
      return method || "-";
  }
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
    error.value = userFacingError(caught, "长期轨迹数据加载失败");
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
    notifySuccess(note);
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught, "身份更新失败");
  } finally {
    saving.value = false;
  }
}

async function removeIdentity(): Promise<void> {
  if (!selectedId.value) return;
  if (!window.confirm("确定要删除该长期轨迹身份及其所有特征关联记录吗？"))
    return;
  saving.value = true;
  clearFeedback();
  try {
    await api<void>(
      `/api/v1/portrait/trajectories/identities/${encodeURIComponent(selectedId.value)}`,
      { method: "DELETE" },
    );
    selectedId.value = "";
    notifySuccess("身份及其生物特征记录已成功删除");
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
    notifySuccess(`已将 ${sources.length} 个身份成功合并至当前主体`);
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught, "身份合并失败");
  } finally {
    saving.value = false;
  }
}

async function splitOut(segmentId?: string): Promise<void> {
  const targetSegments = segmentId ? [segmentId] : splitSelection.value;
  if (!selectedId.value || !targetSegments.length) return;
  saving.value = true;
  clearFeedback();
  try {
    const created = await api<LongTermIdentity>(
      "/api/v1/portrait/trajectories/identities/split",
      {
        method: "POST",
        body: JSON.stringify({
          source_identity_id: selectedId.value,
          segment_ids: targetSegments,
        }),
      },
    );
    splitSelection.value = [];
    selectedId.value = created.identity_id;
    notifySuccess(
      `已成功拆分为新身份「${created.display_name || created.identity_id}」`,
    );
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught, "片段拆分失败");
  } finally {
    saving.value = false;
  }
}

function toggle(target: string[], id: string): void {
  const index = target.indexOf(id);
  if (index >= 0) {
    target.splice(index, 1);
  } else {
    target.push(id);
  }
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page trajectory-page">
    <p v-if="error" class="error-banner">{{ error }}</p>
    <p v-if="message" class="success-banner">{{ message }}</p>

    <!-- 1. 顶部数据统计卡片 -->
    <section class="stats">
      <article class="stat teal">
        <div class="stat-top-row">
          <span class="stat-title">长期身份主体</span>
          <div class="stat-icon-badge">
            <Users :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{ total }} 个</strong>
        <small class="stat-desc">跨摄像头时序人像生物特征聚类</small>
      </article>

      <article class="stat green">
        <div class="stat-top-row">
          <span class="stat-title">已研判确认</span>
          <div class="stat-icon-badge">
            <UserCheck :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{ confirmedCount }} 个</strong>
        <small class="stat-desc">{{ pendingCount }} 个待人工研判</small>
      </article>

      <article class="stat amber">
        <div class="stat-top-row">
          <span class="stat-title">布控感知机位</span>
          <div class="stat-icon-badge">
            <Camera :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{ cameras.length }} 个</strong>
        <small class="stat-desc">园区/卡口智能抓拍视频源</small>
      </article>

      <article class="stat teal">
        <div class="stat-top-row">
          <span class="stat-title">时序轨迹片段</span>
          <div class="stat-icon-badge">
            <Route :size="15" />
          </div>
        </div>
        <strong class="stat-value">{{ segments.length }} 段</strong>
        <small class="stat-desc">{{
          selected
            ? `当前选定: ${selected.display_name || selected.identity_id}`
            : "未选择身份"
        }}</small>
      </article>
    </section>

    <!-- 2. 顶部紧凑过滤工具栏 -->
    <div class="filter-controls">
      <div class="filter-left">
        <label class="filter-item">
          <Filter :size="12" class="filter-icon" />
          <span class="filter-label">研判状态:</span>
          <select
            v-model="filters.status"
            class="filter-select"
            @change="refresh"
          >
            <option value="">全部状态 (All)</option>
            <option value="auto">待研判 (Auto)</option>
            <option value="confirmed">已确认 (Confirmed)</option>
            <option value="rejected">已否决 (Rejected)</option>
          </select>
        </label>

        <label class="filter-item">
          <span class="filter-label">抓拍机位:</span>
          <select
            v-model="filters.camera_id"
            class="filter-select"
            @change="refresh"
          >
            <option value="">全部机位 (All Cameras)</option>
            <option
              v-for="camera in cameras"
              :key="camera.camera_id"
              :value="camera.camera_id"
            >
              {{ camera.display_name || camera.camera_id }}
            </option>
          </select>
        </label>

        <label class="filter-item">
          <span class="filter-label">起始:</span>
          <input
            v-model="filters.since"
            type="datetime-local"
            class="filter-input date-input"
            @change="refresh"
          />
        </label>

        <label class="filter-item">
          <span class="filter-label">截止:</span>
          <input
            v-model="filters.until"
            type="datetime-local"
            class="filter-input date-input"
            @change="refresh"
          />
        </label>
      </div>

      <div class="filter-right">
        <button class="button secondary tiny-btn" @click="resetFilters">
          <RotateCcw :size="12" />
          <span>重置筛选</span>
        </button>
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

    <!-- 3. 工作台左右联动架构 -->
    <div class="trajectory-workbench-layout">
      <!-- 左侧：身份列表与合并多选 -->
      <aside class="trajectory-sidebar">
        <div class="sidebar-header">
          <div class="header-left">
            <Users :size="14" class="header-icon" />
            <h3>长期身份列表</h3>
          </div>
          <span class="badge count-badge">共 {{ total }} 个</span>
        </div>

        <div class="identity-cards-scroll">
          <div
            v-for="identity in identities"
            :key="identity.identity_id"
            class="identity-card-item"
            :class="{ selected: identity.identity_id === selectedId }"
          >
            <label class="checkbox-box" title="勾选以合并至选定身份">
              <input
                type="checkbox"
                class="checkbox-input"
                :checked="mergeSelection.includes(identity.identity_id)"
                @change="toggle(mergeSelection, identity.identity_id)"
              />
            </label>

            <div
              class="identity-card-body"
              @click="select(identity.identity_id)"
            >
              <div class="identity-top-row">
                <strong
                  class="identity-title"
                  :title="identity.display_name || identity.identity_id"
                >
                  {{ identity.display_name || identity.identity_id }}
                </strong>
                <span
                  class="badge status-badge"
                  :class="
                    identity.status === 'confirmed'
                      ? 'active'
                      : identity.status === 'rejected'
                        ? 'error-badge'
                        : 'warn-badge'
                  "
                >
                  <span
                    class="status-dot"
                    :class="
                      identity.status === 'confirmed'
                        ? 'dot-active'
                        : identity.status === 'rejected'
                          ? 'dot-error'
                          : 'dot-warn'
                    "
                  />
                  {{
                    identity.status === "confirmed"
                      ? "已确认"
                      : identity.status === "rejected"
                        ? "已否决"
                        : "待研判"
                  }}
                </span>
              </div>

              <div class="identity-meta-row">
                <span>{{ identity.segment_count }} 段轨迹</span>
                <span class="dot-sep">·</span>
                <span
                  >{{
                    identity.camera_ids ? identity.camera_ids.length : 0
                  }}
                  个机位</span
                >
                <span class="dot-sep">·</span>
                <span class="mono">{{
                  identity.modalities ? identity.modalities.join("+") : "人脸"
                }}</span>
              </div>

              <div class="identity-time-row">
                <Clock :size="11" class="clock-icon" />
                <span>最近 {{ formatTime(identity.last_seen_at) }}</span>
              </div>
            </div>
          </div>

          <div v-if="!identities.length" class="empty-sidebar">
            <UserRound :size="32" class="empty-icon" />
            <p>暂无符合筛选条件的长期轨迹身份</p>
          </div>
        </div>

        <!-- 批量合并工具条 -->
        <div v-if="mergeSelection.length" class="merge-actions-bar">
          <span class="merge-tip">已选 {{ mergeSelection.length }} 个身份</span>
          <button
            class="button primary tiny-btn merge-btn"
            :disabled="saving || !selectedId"
            @click="mergeInto"
          >
            <GitMerge :size="12" />合并到当前身份
          </button>
        </div>
      </aside>

      <!-- 右侧：选定身份轨迹时序轴与研判工作区 -->
      <main class="trajectory-workspace">
        <template v-if="selected">
          <!-- 头部研判与命名工具卡片 -->
          <section class="panel identity-header-card">
            <div class="identity-header-top">
              <div class="identity-title-box">
                <div class="identity-heading">
                  <h2>{{ selected.display_name || selected.identity_id }}</h2>
                  <span
                    class="badge status-badge"
                    :class="
                      selected.status === 'confirmed'
                        ? 'active'
                        : selected.status === 'rejected'
                          ? 'error-badge'
                          : 'warn-badge'
                    "
                  >
                    <span
                      class="status-dot"
                      :class="
                        selected.status === 'confirmed'
                          ? 'dot-active'
                          : selected.status === 'rejected'
                            ? 'dot-error'
                            : 'dot-warn'
                      "
                    />
                    {{ statusLabel(selected.status) }}
                  </span>
                  <span class="mono id-badge"
                    >ID: {{ selected.identity_id }}</span
                  >
                </div>
                <small class="time-range-text">
                  首次出现 {{ formatTime(selected.first_seen_at) }} · 最近出现
                  {{ formatTime(selected.last_seen_at) }}
                </small>
              </div>

              <!-- 研判状态操作 -->
              <div class="triage-actions-group">
                <button
                  class="button primary tiny-btn confirm-btn"
                  :disabled="saving || selected.status === 'confirmed'"
                  title="确认该身份聚类准确"
                  @click="
                    patchIdentity({ status: 'confirmed' }, '身份已研判确认')
                  "
                >
                  <Check :size="12" />确认身份
                </button>
                <button
                  class="button secondary tiny-btn reject-btn"
                  :disabled="saving || selected.status === 'rejected'"
                  title="否决该身份聚类"
                  @click="patchIdentity({ status: 'rejected' }, '身份已否决')"
                >
                  <X :size="12" />否决
                </button>
                <button
                  class="button secondary tiny-btn danger-btn"
                  :disabled="saving"
                  title="删除该身份及其生物特征"
                  @click="removeIdentity"
                >
                  <Trash2 :size="12" />删除
                </button>
              </div>
            </div>

            <!-- 快捷重命名栏 -->
            <div class="rename-strip">
              <span class="field-label">身份命名标注:</span>
              <input
                v-model="renameDraft"
                class="field-input rename-input"
                maxlength="256"
                placeholder="例如：张三 / 访客001"
                @keyup.enter="
                  patchIdentity({ display_name: renameDraft }, '身份名称已更新')
                "
              />
              <button
                class="button secondary tiny-btn"
                :disabled="saving || renameDraft === selected.display_name"
                @click="
                  patchIdentity({ display_name: renameDraft }, '身份名称已更新')
                "
              >
                保存名称
              </button>
            </div>
          </section>

          <!-- 跨机位轨迹时序轴 -->
          <section class="panel timeline-panel">
            <div class="panel-header">
              <div class="header-left">
                <Route :size="14" class="header-icon" />
                <h3>跨摄像头时序轨迹迁移时序图</h3>
                <span class="badge count-badge"
                  >{{ timeline.length }} 次出现记录</span
                >
              </div>
            </div>

            <div class="timeline-scroll-container">
              <ol class="timeline-list">
                <li
                  v-for="(entry, index) in timeline"
                  :key="entry.segment_id"
                  class="timeline-item"
                >
                  <div class="timeline-marker">
                    <div class="timeline-dot" />
                    <div
                      v-if="index < timeline.length - 1"
                      class="timeline-line"
                    />
                  </div>

                  <div class="timeline-card">
                    <div class="timeline-card-header">
                      <div class="timeline-cam-name">
                        <MapPin :size="12" class="cam-icon" />
                        <strong>{{
                          entry.camera_name || cameraName(entry.camera_id)
                        }}</strong>
                      </div>
                      <span class="badge method-badge">{{
                        methodLabel(entry.match_method)
                      }}</span>
                    </div>

                    <div class="timeline-card-body">
                      <span class="time-point">{{
                        formatTime(entry.first_seen_at)
                      }}</span>
                      <span class="dot-sep">·</span>
                      <span
                        >停留 {{ formatDuration(entry.duration_seconds) }}</span
                      >
                      <span v-if="entry.match_score" class="dot-sep">·</span>
                      <span v-if="entry.match_score" class="score-text mono"
                        >相似度
                        {{ (entry.match_score * 100).toFixed(1) }}%</span
                      >
                    </div>

                    <div
                      v-if="entry.transition_seconds !== null"
                      class="timeline-gap-badge"
                    >
                      <Clock :size="10" />
                      <span
                        >距上次出现迁移耗时
                        {{ formatDuration(entry.transition_seconds) }}</span
                      >
                    </div>
                  </div>
                </li>

                <li v-if="!timeline.length" class="empty-timeline">
                  <Route :size="32" class="empty-icon" />
                  <p>该身份暂无时序轨迹点记录</p>
                </li>
              </ol>
            </div>
          </section>

          <!-- 轨迹片段明细表格 -->
          <section class="panel segments-table-panel">
            <div class="panel-header">
              <div class="header-left">
                <Layers :size="14" class="header-icon" />
                <h3>时序抓拍片段明细</h3>
                <span class="badge count-badge">{{ segments.length }} 段</span>
              </div>

              <div v-if="splitSelection.length" class="header-right">
                <button
                  class="button secondary tiny-btn split-batch-btn"
                  :disabled="saving"
                  @click="splitOut()"
                >
                  <Scissors :size="11" />拆分所选
                  {{ splitSelection.length }} 段为新身份
                </button>
              </div>
            </div>

            <DataTable
              :columns="segmentColumns"
              :items="segments"
              :page-size="segmentPageSize"
              :page-size-options="[10, 20, 50]"
              table-class="trajectory-table"
              wrapper-class="trajectory-table-wrapper"
              empty-text="暂无时序抓拍片段数据"
            >
              <!-- 1. 片段标识 -->
              <template #segment_id="{ row }">
                <div class="segment-id-cell">
                  <input
                    type="checkbox"
                    class="checkbox-input"
                    :checked="splitSelection.includes(row.segment_id)"
                    :title="'勾选以拆分该片段'"
                    @change="toggle(splitSelection, row.segment_id)"
                  />
                  <span class="mono" :title="row.segment_id"
                    >{{ row.segment_id.slice(0, 16) }}…</span
                  >
                </div>
              </template>

              <!-- 2. 抓拍机位 -->
              <template #camera_id="{ row }">
                <span
                  class="single-line-text bold"
                  :title="cameraName(row.camera_id)"
                >
                  {{ cameraName(row.camera_id) }}
                </span>
              </template>

              <!-- 3. 时序区间 -->
              <template #time_range="{ row }">
                <span class="single-line-text time-text">
                  {{ formatTime(row.first_seen_at) }}
                </span>
              </template>

              <!-- 4. 跟踪质量 -->
              <template #track_quality="{ row }">
                <span class="quality-badge">
                  {{
                    typeof row.track_quality === "number"
                      ? row.track_quality.toFixed(2)
                      : "-"
                  }}
                </span>
              </template>

              <!-- 5. 匹配方式 -->
              <template #match_method="{ row }">
                <span class="badge method-badge">
                  {{ methodLabel(row.match_method) }}
                </span>
              </template>

              <!-- 6. 相似度 -->
              <template #match_score="{ row }">
                <span class="mono bold score-cell">
                  {{
                    typeof row.match_score === "number"
                      ? (row.match_score * 100).toFixed(1) + "%"
                      : "-"
                  }}
                </span>
              </template>

              <!-- 7. 操作 -->
              <template #actions="{ row }">
                <button
                  class="button secondary tiny-btn split-btn"
                  title="将该抓拍片段拆分为一个全新的独立身份"
                  :disabled="saving"
                  @click="splitOut(row.segment_id)"
                >
                  <Scissors :size="11" />拆分
                </button>
              </template>
            </DataTable>
          </section>
        </template>

        <!-- 未选择身份时 -->
        <div v-else class="panel empty-workspace">
          <UserRound :size="42" class="empty-icon" />
          <h3>未选定长期身份主体</h3>
          <p>请从左侧列表中选择一个长期轨迹身份以进行时序迁移研判与片段治理</p>
        </div>
      </main>
    </div>
  </section>
</template>

<style src="./trajectory/trajectory-view.css" scoped></style>
