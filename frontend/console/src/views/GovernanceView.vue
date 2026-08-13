<script setup lang="ts">
import { Check, ShieldCheck } from "@lucide/vue";
import { onMounted, reactive, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";

import { api, userFacingError } from "../api";

type RecordMap = {
  record_id: string;
  period_started_at: number;
  [key: string]: string | number | boolean;
};

const lifecycle = ref<RecordMap[]>([]);
const identityProviders = ref<RecordMap[]>([]);
const annotationProviders = ref<RecordMap[]>([]);
const indexBackends = ref<RecordMap[]>([]);
const rerankers = ref<RecordMap[]>([]);
const retention = ref<RecordMap | null>(null);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const lifecycleForm = reactive({
  project_id: "default",
  action: "disable",
  reason: "",
});
const retentionForm = reactive({
  retention_days: 365,
  export_approval_required: true,
  enabled: true,
});

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [requests, policy, adapters, indexes, rerank] = await Promise.all([
      api<RecordMap[]>("/api/v1/platform/projects/lifecycle-requests"),
      api<RecordMap>("/api/v1/platform/audit/retention"),
      api<RecordMap[]>("/api/v1/platform/identity-providers"),
      api<RecordMap[]>("/api/v1/search/index-backends"),
      api<RecordMap[]>("/api/v1/search/rerankers"),
    ]);
    lifecycle.value = requests;
    retention.value = policy;
    Object.assign(retentionForm, policy);
    identityProviders.value = adapters;
    indexBackends.value = indexes;
    rerankers.value = rerank;
    annotationProviders.value = await api<RecordMap[]>(
      "/api/v1/data/annotation-providers",
    );
  } catch (caught) {
    error.value = userFacingError(caught, "Platform data could not be loaded");
  } finally {
    loading.value = false;
  }
}

async function mutate(action: () => Promise<void>): Promise<void> {
  saving.value = true;
  error.value = "";
  try {
    await action();
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught, "Operation failed");
  } finally {
    saving.value = false;
  }
}

async function requestLifecycle(): Promise<void> {
  await mutate(async () => {
    await api("/api/v1/platform/projects/lifecycle-requests", {
      method: "POST",
      body: JSON.stringify(lifecycleForm),
    });
    lifecycleForm.reason = "";
  });
}

async function decide(request: RecordMap, approved: boolean): Promise<void> {
  await mutate(() =>
    api(
      `/api/v1/platform/projects/lifecycle-requests/${encodeURIComponent(String(request.record_id))}/decide`,
      {
        method: "POST",
        body: JSON.stringify({
          approved,
          comment: approved ? "approved in Console" : "rejected in Console",
        }),
      },
    ).then(() => undefined),
  );
}

async function saveRetention(): Promise<void> {
  await mutate(() =>
    api("/api/v1/platform/audit/retention", {
      method: "PUT",
      body: JSON.stringify(retentionForm),
    }).then(() => undefined),
  );
}

async function probe(
  path: string,
  target: RecordMap | RecordMap[],
): Promise<void> {
  const item = Array.isArray(target) ? target[0] : target;
  if (!item) return;
  await mutate(() =>
    api(`/api/v1/${path}/${encodeURIComponent(String(item.record_id))}/probe`, {
      method: "POST",
    }).then(() => undefined),
  );
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page">
    <p v-if="error" class="callout error">{{ error }}</p>
    <div class="governance-grid">
      <section class="panel">
        <div class="panel-header"><h2>项目生命周期</h2></div>
        <div class="panel-body form-grid">
          <label
            ><span>项目</span
            ><input v-model="lifecycleForm.project_id" /></label
          ><label
            ><span>动作</span
            ><select v-model="lifecycleForm.action">
              <option value="disable">停用</option>
              <option value="restore">恢复</option>
              <option value="delete">删除</option>
            </select></label
          ><label class="span-2"
            ><span>原因</span><input v-model="lifecycleForm.reason" /></label
          ><button
            class="button primary"
            :disabled="saving || !lifecycleForm.reason"
            @click="requestLifecycle"
          >
            <ShieldCheck :size="16" />提交审批
          </button>
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width: 50px">序号</th>
                <th>项目</th>
                <th>动作</th>
                <th>状态</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in lifecycle" :key="item.record_id">
                <td class="muted">{{ index + 1 }}</td>
                <td>{{ item.project_id }}</td>
                <td>{{ item.action }}</td>
                <td>{{ item.status }}</td>
                <td>
                  <button
                    v-if="item.status === 'pending'"
                    class="button ghost"
                    @click="decide(item, true)"
                  >
                    <Check :size="14" />批准
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
      <section class="panel">
        <div class="panel-header"><h2>审计保留</h2></div>
        <div class="panel-body form-grid">
          <label
            ><span>天数</span
            ><input
              v-model.number="retentionForm.retention_days"
              type="number"
              min="1" /></label
          ><label class="toggle"
            ><input
              v-model="retentionForm.enabled"
              type="checkbox"
            />启用</label
          ><button
            class="button primary"
            :disabled="saving"
            @click="saveRetention"
          >
            保存策略</button
          ><span v-if="retention" class="muted"
            >当前：{{ retention.retention_days }} 天</span
          >
        </div>
      </section>
      <section class="panel">
        <div class="panel-header"><h2>适配器健康</h2></div>
        <div class="adapter-list">
          <div v-for="item in identityProviders" :key="item.record_id">
            <span>身份 · {{ item.display_name }}</span
            ><strong>{{ item.last_health }}</strong
            ><button
              class="button ghost"
              @click="probe('platform/identity-providers', item)"
            >
              探测
            </button>
          </div>
          <div v-for="item in annotationProviders" :key="item.record_id">
            <span>标注 · {{ item.name }}</span
            ><strong>{{ item.last_health }}</strong
            ><button
              class="button ghost"
              @click="probe('data/annotation-providers', item)"
            >
              探测
            </button>
          </div>
          <div v-for="item in indexBackends" :key="item.record_id">
            <span>索引 · {{ item.name }}</span
            ><strong>{{ item.health }}</strong
            ><button
              class="button ghost"
              @click="probe('search/index-backends', item)"
            >
              探测
            </button>
          </div>
          <div v-for="item in rerankers" :key="item.record_id">
            <span>重排 · {{ item.name }}</span
            ><strong>{{ item.health }}</strong
            ><button
              class="button ghost"
              @click="probe('search/rerankers', item)"
            >
              探测
            </button>
          </div>
          <p
            v-if="
              !identityProviders.length &&
              !annotationProviders.length &&
              !indexBackends.length &&
              !rerankers.length
            "
            class="empty"
          >
            暂未配置适配器
          </p>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.governance-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.governance-grid > .panel:first-child,
.governance-grid > .panel:nth-child(3) {
  grid-column: span 2;
}
.adapter-list {
  display: grid;
  gap: 1px;
  background: var(--line);
}
.adapter-list > div {
  display: grid;
  grid-template-columns: 1fr auto auto;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #fff;
}
.adapter-list strong {
  color: var(--green);
  font-size: 12px;
}
.toggle {
  display: flex;
  align-items: center;
  gap: 8px;
}
@media (max-width: 900px) {
  .governance-grid {
    grid-template-columns: 1fr;
  }
  .governance-grid > .panel:first-child,
  .governance-grid > .panel:nth-child(3) {
    grid-column: auto;
  }
}
</style>
