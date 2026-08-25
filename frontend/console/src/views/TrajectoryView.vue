<script setup lang="ts">
import { computed, onMounted, reactive, ref, type Ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { Check, GitMerge, Route, Scissors, Trash2, X } from "@lucide/vue";
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
  // 日期输入是本地时间，接口按秒级 epoch 过滤。
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
    message.value = `已合并 ${sources.length} 个身份`;
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
      `/api/v1/portrait/trajectories/identities/${encodeURIComponent(selectedId.value)}/split`,
      {
        method: "POST",
        body: JSON.stringify({ segment_ids: splitSelection.value }),
      },
    );
    message.value = "误合并的片段已拆分为新身份";
    await refresh();
    await select(created.identity_id);
  } catch (caught) {
    error.value = userFacingError(caught, "身份拆分失败");
  } finally {
    saving.value = false;
  }
}

function toggle(list: string[] | Ref<string[]>, value: string): void {
  const values = Array.isArray(list) ? list : list.value;
  const index = values.indexOf(value);
  if (index >= 0) values.splice(index, 1);
  else values.push(value);
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page">
    <p v-if="error" class="callout error">{{ error }}</p>
    <p v-if="message" class="callout success">{{ message }}</p>

    <section class="panel">
      <div class="panel-body filter-bar">
        <label
          >状态<select v-model="filters.status" @change="refresh">
            <option value="">全部</option>
            <option value="auto">待研判</option>
            <option value="confirmed">已确认</option>
            <option value="rejected">已否决</option>
          </select></label
        >
        <label
          >摄像头<select v-model="filters.camera_id" @change="refresh">
            <option value="">全部</option>
            <option
              v-for="camera in cameras"
              :key="camera.camera_id"
              :value="camera.camera_id"
            >
              {{ camera.display_name || camera.camera_id }}
            </option>
          </select></label
        >
        <label
          >起始<input
            v-model="filters.since"
            type="datetime-local"
            @change="refresh"
        /></label>
        <label
          >截止<input
            v-model="filters.until"
            type="datetime-local"
            @change="refresh"
        /></label>
      </div>
    </section>

    <div class="trajectory-grid">
      <section class="panel">
        <div class="panel-header">
          <h2>身份</h2>
          <span class="muted">{{ total }} 个</span>
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
              :checked="mergeSelection.includes(identity.identity_id)"
              :title="'选择以合并到当前身份'"
              @change="toggle(mergeSelection, identity.identity_id)"
            />
            <button class="identity-main" @click="select(identity.identity_id)">
              <strong>{{
                identity.display_name || identity.identity_id
              }}</strong>
              <small>
                {{ identity.segment_count }} 段 ·
                {{ identity.camera_ids.length }} 个机位 ·
                {{ identity.modalities.join("+") || "无特征" }}
              </small>
              <small>最近出现 {{ formatTime(identity.last_seen_at) }}</small>
            </button>
            <em :class="['status', identity.status]">{{
              statusLabel(identity.status)
            }}</em>
          </div>
          <div v-if="!identities.length" class="empty">还没有长期轨迹身份</div>
        </div>
        <div v-if="mergeSelection.length" class="panel-body merge-bar">
          <span class="muted">已选 {{ mergeSelection.length }} 个身份</span>
          <button
            class="button tiny primary"
            :disabled="saving || !selectedId"
            @click="mergeInto"
          >
            <GitMerge :size="14" />合并到当前身份
          </button>
        </div>
      </section>

      <section v-if="selected" class="panel">
        <div class="panel-header">
          <div>
            <h2>{{ selected.display_name || selected.identity_id }}</h2>
            <p>
              首次 {{ formatTime(selected.first_seen_at) }} · 最近
              {{ formatTime(selected.last_seen_at) }}
            </p>
          </div>
          <em :class="['status', selected.status]">{{
            statusLabel(selected.status)
          }}</em>
        </div>
        <div class="panel-body adjudication">
          <label class="rename"
            >命名<input
              v-model="renameDraft"
              maxlength="256"
              placeholder="例如：张三"
              @keyup.enter="
                patchIdentity({ display_name: renameDraft }, '名称已更新')
              "
          /></label>
          <div class="actions">
            <button
              class="button tiny"
              :disabled="saving || renameDraft === selected.display_name"
              @click="
                patchIdentity({ display_name: renameDraft }, '名称已更新')
              "
            >
              保存名称</button
            ><button
              class="button tiny primary"
              :disabled="saving || selected.status === 'confirmed'"
              @click="patchIdentity({ status: 'confirmed' }, '身份已确认')"
            >
              <Check :size="14" />确认</button
            ><button
              class="button tiny"
              :disabled="saving || selected.status === 'rejected'"
              @click="patchIdentity({ status: 'rejected' }, '身份已否决')"
            >
              <X :size="14" />否决</button
            ><button
              class="button tiny danger"
              :disabled="saving"
              @click="removeIdentity"
            >
              <Trash2 :size="14" />删除
            </button>
          </div>
        </div>

        <div class="subhead">
          <strong>跨摄像头时间线</strong
          ><span>{{ timeline.length }} 次出现</span>
        </div>
        <ol class="timeline">
          <li v-for="entry in timeline" :key="entry.segment_id">
            <div class="timeline-mark" />
            <div class="timeline-body">
              <strong>{{
                entry.camera_name || cameraName(entry.camera_id)
              }}</strong>
              <small>
                {{ formatTime(entry.first_seen_at) }} · 停留
                {{ formatDuration(entry.duration_seconds) }} ·
                {{ methodLabel(entry.match_method) }}
              </small>
              <small v-if="entry.transition_seconds !== null" class="gap">
                距上次出现 {{ formatDuration(entry.transition_seconds) }}
              </small>
            </div>
          </li>
          <li v-if="!timeline.length" class="empty">该身份还没有轨迹片段</li>
        </ol>

        <div class="subhead">
          <strong>片段</strong>
          <button
            class="button tiny"
            :disabled="saving || !splitSelection.length"
            @click="splitOut"
          >
            <Scissors :size="14" />拆分所选片段
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
              :checked="splitSelection.includes(segment.segment_id)"
              @change="toggle(splitSelection, segment.segment_id)"
            />
            <span>
              <strong>{{ cameraName(segment.camera_id) }}</strong>
              <small>
                {{ formatTime(segment.first_seen_at) }} ·
                {{ segment.frame_count }} 帧 · 质量
                {{ segment.track_quality.toFixed(2) }} ·
                {{ methodLabel(segment.match_method) }}
                {{
                  segment.match_method === "reid"
                    ? `（${segment.match_score.toFixed(3)}）`
                    : ""
                }}
              </small>
            </span>
          </label>
          <div v-if="!segments.length" class="empty">没有片段</div>
        </div>
      </section>
      <section v-else class="panel">
        <div class="empty">选择左侧身份查看跨摄像头轨迹</div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.trajectory-grid {
  display: grid;
  grid-template-columns: minmax(300px, 0.9fr) minmax(0, 1.1fr);
  gap: 16px;
}
.panel-header h2 {
  display: flex;
  align-items: center;
  gap: 8px;
}
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
}
label {
  display: grid;
  gap: 6px;
  font-size: 13px;
  color: var(--muted);
}
input,
select {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 8px 10px;
  font: inherit;
  color: var(--text);
  background: #fff;
}
.identity-list,
.segment-list {
  display: grid;
  gap: 1px;
  background: var(--line);
}
.identity-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: #fff;
}
.identity-row.selected {
  background: #edf8f7;
  box-shadow: inset 3px 0 var(--teal);
}
.identity-main {
  flex: 1;
  display: grid;
  gap: 3px;
  border: 0;
  background: none;
  text-align: left;
  cursor: pointer;
  min-width: 0;
  padding: 0;
}
small {
  color: var(--muted);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.status {
  font-size: 12px;
  font-style: normal;
  white-space: nowrap;
  padding: 3px 7px;
  border-radius: 4px;
  background: #eef1f2;
  color: var(--muted);
}
.status.confirmed {
  color: #0b7557;
  background: #e4f5ed;
}
.status.rejected {
  color: #a33a33;
  background: #fbeceb;
}
.merge-bar,
.adjudication {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.rename {
  flex: 1;
  min-width: 180px;
}
.button.tiny {
  min-height: 30px;
  padding: 5px 9px;
  font-size: 12px;
}
.button.danger {
  color: #a33a33;
  border-color: #e7c9c6;
}
.subhead {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 13px;
}
.timeline {
  list-style: none;
  margin: 0;
  padding: 4px 16px 16px;
  display: grid;
  gap: 2px;
}
.timeline li {
  display: grid;
  grid-template-columns: 16px 1fr;
  gap: 10px;
  padding-bottom: 12px;
  position: relative;
}
.timeline li:not(:last-child)::before {
  content: "";
  position: absolute;
  left: 7px;
  top: 14px;
  bottom: 0;
  width: 1px;
  background: var(--line);
}
.timeline-mark {
  width: 9px;
  height: 9px;
  margin-top: 5px;
  border-radius: 50%;
  background: var(--teal);
}
.timeline-body {
  display: grid;
  gap: 2px;
  min-width: 0;
}
.gap {
  color: #2264a6;
}
.segment-row {
  display: flex;
  align-items: start;
  gap: 10px;
  padding: 10px 14px;
  background: #fff;
}
.segment-row span {
  display: grid;
  gap: 3px;
  min-width: 0;
}
.segment-row small {
  white-space: normal;
}
.muted {
  color: var(--muted);
  font-size: 12px;
}
.empty {
  padding: 22px;
  color: var(--muted);
  text-align: center;
  background: #fff;
}
@media (max-width: 900px) {
  .trajectory-grid {
    grid-template-columns: 1fr;
  }
}
</style>
