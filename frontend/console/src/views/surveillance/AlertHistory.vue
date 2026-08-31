<script setup lang="ts">
import { Check, RefreshCw, X } from "@lucide/vue";
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
const error = ref("");
const filters = reactive({ status: "", camera_id: "" });

function format(value: number): string {
  return new Date(value * 1000).toLocaleString("zh-CN", { hour12: false });
}
function query(): string {
  const params = new URLSearchParams({ limit: "100" });
  if (filters.status) params.set("status", filters.status);
  if (filters.camera_id) params.set("camera_id", filters.camera_id);
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
async function triage(
  alert: SurveillanceAlert,
  status: "confirmed" | "false_positive" | "ignored",
): Promise<void> {
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
  }
}
async function createFeedback(alert: SurveillanceAlert): Promise<void> {
  try {
    await createAlertFeedback(alert.alert_id);
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
    <p v-if="error" class="error-message">{{ error }}</p>
    <section class="panel filters">
      <label
        >状态<select v-model="filters.status" @change="refresh">
          <option value="">全部</option>
          <option value="pending">待处置</option>
          <option value="confirmed">已确认</option>
          <option value="false_positive">误报</option>
          <option value="ignored">已忽略</option>
        </select></label
      ><label
        >摄像头<input
          v-model.trim="filters.camera_id"
          placeholder="输入摄像头编号"
          @change="refresh" /></label
      ><strong>共 {{ total }} 条</strong>
      <button class="button secondary refresh-btn" @click="refresh">
        <RefreshCw :size="15" />刷新
      </button>
    </section>
    <section class="cards">
      <article
        v-for="alert in alerts"
        :key="alert.alert_id"
        class="panel alert-card"
      >
        <img
          v-if="artifactUrl(alert)"
          :src="artifactUrl(alert)!"
          alt="告警抓拍"
        />
        <div class="details">
          <div class="title-row">
            <div>
              <h2>{{ alert.camera_id }}</h2>
              <small
                >{{ format(alert.triggered_at) }} · {{ labelModality(alert.modality) }} ·
                {{ (alert.match_score * 100).toFixed(1) }}%</small
              >
            </div>
            <span class="badge" :class="alert.status">{{ labelSurveillanceAlertStatus(alert.status) }}</span>
          </div>
          <dl>
            <div>
              <dt>目标身份</dt>
              <dd class="mono">{{ alert.portrait_identity_id }}</dd>
            </div>
            <div>
              <dt>任务</dt>
              <dd>{{ alert.task_id }}</dd>
            </div>
            <div>
              <dt>出现次数</dt>
              <dd>
                {{ alert.occurrence_count }}（最高
                {{ (alert.max_score * 100).toFixed(1) }}%）
              </dd>
            </div>
            <div>
              <dt>轨迹</dt>
              <dd>{{ alert.trajectory_identity_id || "暂无关联" }}</dd>
            </div>
          </dl>
          <div v-if="alert.status === 'pending'" class="actions">
            <button class="button confirm" @click="triage(alert, 'confirmed')">
              <Check :size="16" />确认</button
            ><button
              class="button reject"
              @click="triage(alert, 'false_positive')"
            >
              <X :size="16" />误报</button
            ><button class="button secondary" @click="triage(alert, 'ignored')">
              忽略
            </button>
          </div>
          <template v-else>
            <p class="triage">
              {{ alert.triage_reason
              }}<span v-if="alert.triaged_by"> · {{ alert.triaged_by }}</span>
            </p>
            <button
              v-if="alert.status === 'false_positive'"
              class="button secondary feedback"
              @click="createFeedback(alert)"
            >
              创建待审核反馈
            </button>
          </template>
        </div>
      </article>
      <p v-if="!alerts.length" class="panel muted">当前筛选条件下没有告警。</p>
    </section>
  </main>
</template>

<style scoped>
.alert-page {
  display: grid;
  gap: 1rem;
}
.panel {
  border: 1px solid var(--border-color, #d9e0ea);
  border-radius: 0.8rem;
  padding: 1rem;
  background: var(--panel-color, #fff);
}
.button {
  border: 0;
  border-radius: 0.5rem;
  padding: 0.45rem 0.75rem;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  cursor: pointer;
  background: var(--accent, #2563eb);
  color: #fff;
}
.button.secondary {
  background: var(--soft-color, #e2e8f0);
  color: inherit;
}
.button.confirm {
  background: #15803d;
}
.button.reject {
  background: #b91c1c;
}
.filters {
  display: flex;
  gap: 0.75rem;
  align-items: end;
}
.refresh-btn {
  margin-left: auto;
}
.filters label {
  display: grid;
  gap: 0.3rem;
  font-size: 0.84rem;
  color: var(--muted-text, #64748b);
}
input,
select {
  padding: 0.55rem;
  border: 1px solid var(--border-color, #cbd5e1);
  border-radius: 0.45rem;
  background: transparent;
  color: inherit;
}
.cards {
  display: grid;
  gap: 0.75rem;
}
.alert-card {
  display: grid;
  grid-template-columns: 180px 1fr;
  gap: 1rem;
}
.alert-card img {
  width: 180px;
  height: 130px;
  object-fit: cover;
  border-radius: 0.55rem;
  background: #e2e8f0;
}
.title-row {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
}
.badge {
  height: max-content;
  padding: 0.2rem 0.45rem;
  border-radius: 999px;
  background: var(--soft-color, #e2e8f0);
  font-size: 0.78rem;
}
.badge.pending {
  background: #fef3c7;
  color: #92400e;
}
.badge.confirmed {
  background: #dcfce7;
  color: #166534;
}
.badge.false_positive {
  background: #fee2e2;
  color: #991b1b;
}
small,
.muted {
  color: var(--muted-text, #64748b);
}
dl {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.5rem;
  margin: 0.8rem 0;
}
dt {
  font-size: 0.76rem;
  color: var(--muted-text, #64748b);
}
dd {
  margin: 0.15rem 0 0;
}
.mono {
  font-family: ui-monospace, monospace;
  font-size: 0.82rem;
}
.actions {
  display: flex;
  gap: 0.5rem;
}
.triage {
  margin: 0;
  color: var(--muted-text, #64748b);
}
.error-message {
  color: #dc2626;
}
.feedback {
  margin-top: 0.6rem;
}
@media (max-width: 700px) {
  .page-header,
  .alert-card {
    grid-template-columns: 1fr;
  }
  .filters {
    flex-wrap: wrap;
  }
  .alert-card img {
    width: 100%;
    height: 200px;
  }
  dl {
    grid-template-columns: 1fr;
  }
}
</style>
