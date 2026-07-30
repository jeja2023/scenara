<script setup lang="ts">
import { Plus, RefreshCw } from "@lucide/vue";
import { onMounted, reactive, ref } from "vue";

import { ApiError, api } from "../api";
import { labelCaseStatus, labelEntitlement, labelPriority, labelSeverity, labelSupportTier } from "../labels";

interface EnterpriseStatus {
  license_id: string;
  customer: string;
  entitlements: string[];
  limits: Record<string, number>;
  usage: Record<string, number>;
  support_tier: string;
  sla_targets: Record<string, number>;
  expires_at: number;
  document_sha256: string;
}
interface Incident {
  incident_id: string;
  title: string;
  severity: string;
  status: string;
  summary: string;
  created_at: number;
}
interface SupportCase { case_id: string; subject: string; priority: string; status: string; created_at: number }
interface Evidence { evidence_id: string; evidence_type: string; object_ref: string; sha256: string; signed_by: string; created_at: number }

const status = ref<EnterpriseStatus | null>(null);
const incidents = ref<Incident[]>([]);
const cases = ref<SupportCase[]>([]);
const evidence = ref<Evidence[]>([]);
const loading = ref(false);
const unavailable = ref(false);
const error = ref("");
const incidentForm = reactive({ title: "", severity: "sev3", summary: "" });
const supportForm = reactive({ subject: "", priority: "normal", description: "" });
const evidenceForm = reactive({ evidence_type: "", object_ref: "", sha256: "", signed_by: "" });

async function refresh(): Promise<void> {
  loading.value = true;
  unavailable.value = false;
  error.value = "";
  try {
    const [nextStatus, nextIncidents, nextCases, nextEvidence] = await Promise.all([
      api<EnterpriseStatus>("/api/v1/enterprise/status"),
      api<Incident[]>("/api/v1/enterprise/incidents"),
      api<SupportCase[]>("/api/v1/enterprise/support/cases"),
      api<Evidence[]>("/api/v1/enterprise/compliance/evidence"),
    ]);
    status.value = nextStatus;
    incidents.value = nextIncidents;
    cases.value = nextCases;
    evidence.value = nextEvidence;
  } catch (caught) {
    const message = caught instanceof Error ? caught.message : String(caught);
    unavailable.value = caught instanceof ApiError && caught.status === 404;
    error.value = unavailable.value ? "" : message;
  } finally {
    loading.value = false;
  }
}

async function createIncident(): Promise<void> {
  await api<Incident>("/api/v1/enterprise/incidents", {
    method: "POST",
    body: JSON.stringify(incidentForm),
  });
  Object.assign(incidentForm, { title: "", severity: "sev3", summary: "" });
  await refresh();
}

async function createSupportCase(): Promise<void> {
  await api<SupportCase>("/api/v1/enterprise/support/cases", {
    method: "POST",
    body: JSON.stringify(supportForm),
  });
  Object.assign(supportForm, { subject: "", priority: "normal", description: "" });
  await refresh();
}

async function createEvidence(): Promise<void> {
  await api<Evidence>("/api/v1/enterprise/compliance/evidence", {
    method: "POST",
    body: JSON.stringify(evidenceForm),
  });
  Object.assign(evidenceForm, { evidence_type: "", object_ref: "", sha256: "", signed_by: "" });
  await refresh();
}

onMounted(refresh);
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div><h1>企业工作区</h1><p>许可证、权益、配额、服务等级协议、事件、支持与合规证据。</p></div>
      <button class="button secondary" :disabled="loading" @click="refresh"><RefreshCw :size="16" />刷新</button>
    </div>
    <p v-if="unavailable" class="callout">此部署未安装企业模块。</p>
    <p v-if="error" class="callout error">{{ error }}</p>

    <template v-if="status">
      <div class="stats">
        <div class="stat teal"><span>许可证</span><strong>{{ status.license_id }}</strong><small>{{ status.customer }}</small></div>
        <div class="stat"><span>支持等级</span><strong>{{ labelSupportTier(status.support_tier) }}</strong><small>{{ status.entitlements.length }} 项权益</small></div>
        <div class="stat green"><span>运行用量</span><strong>{{ status.usage.runs ?? 0 }}</strong><small>上限 {{ status.limits.runs ?? "无限制" }}</small></div>
        <div class="stat coral"><span>到期</span><strong>{{ new Date(status.expires_at * 1000).toLocaleDateString() }}</strong><small class="mono">{{ status.document_sha256.slice(0, 12) }}</small></div>
      </div>

      <div class="enterprise-grid">
        <section class="panel">
          <div class="panel-header"><h2>权益与用量</h2></div>
          <div class="table-scroll"><table class="data-table"><thead><tr><th>权益</th><th>用量</th><th>上限</th></tr></thead><tbody>
            <tr v-for="entitlement in status.entitlements" :key="entitlement">
              <td><strong>{{ labelEntitlement(entitlement) }}</strong><div class="mono muted">{{ entitlement }}</div></td>
              <td>{{ status.usage[entitlement] ?? "?" }}</td>
              <td>{{ status.limits[entitlement] ?? "?" }}</td>
            </tr>
          </tbody></table></div>
        </section>

        <section class="panel">
          <div class="panel-header"><h2>创建事件</h2></div>
          <div class="panel-body">
            <div class="form-grid">
              <label class="span-2"><span>标题</span><input v-model="incidentForm.title" /></label>
              <label><span>严重级别</span><select v-model="incidentForm.severity"><option value="sev1">一级</option><option value="sev2">二级</option><option value="sev3">三级</option><option value="sev4">四级</option></select></label>
              <label class="span-2"><span>摘要</span><textarea v-model="incidentForm.summary"></textarea></label>
            </div>
            <button class="button primary submit" :disabled="!incidentForm.title" @click="createIncident"><Plus :size="16" />创建</button>
          </div>
        </section>

        <section class="panel">
          <div class="panel-header"><h2>事件</h2><span class="badge">{{ incidents.length }}</span></div>
          <div class="table-scroll"><table class="data-table"><thead><tr><th>标题</th><th>严重级别</th><th>状态</th><th>创建时间</th></tr></thead><tbody>
            <tr v-for="incident in incidents" :key="incident.incident_id"><td>{{ incident.title }}</td><td><span class="badge">{{ labelSeverity(incident.severity) }}</span></td><td>{{ labelCaseStatus(incident.status) }}</td><td>{{ new Date(incident.created_at * 1000).toLocaleString() }}</td></tr>
          </tbody></table><div v-if="!incidents.length" class="empty">暂无事件。</div></div>
        </section>

        <section class="panel">
          <div class="panel-header"><h2>支持工单</h2></div>
          <div class="panel-body">
            <div class="form-grid">
              <label class="span-2"><span>主题</span><input v-model="supportForm.subject" /></label>
              <label><span>优先级</span><select v-model="supportForm.priority"><option value="low">低</option><option value="normal">普通</option><option value="high">高</option><option value="urgent">紧急</option></select></label>
              <label class="span-2"><span>描述</span><textarea v-model="supportForm.description"></textarea></label>
            </div>
            <button class="button primary submit" :disabled="!supportForm.subject || !supportForm.description" @click="createSupportCase"><Plus :size="16" />创建工单</button>
            <div class="record-list"><div v-for="item in cases" :key="item.case_id"><strong>{{ item.subject }}</strong><span>{{ labelPriority(item.priority) }} · {{ labelCaseStatus(item.status) }}</span></div></div>
          </div>
        </section>

        <section class="panel wide">
          <div class="panel-header"><h2>合规证据</h2><span class="badge">{{ evidence.length }}</span></div>
          <div class="panel-body">
            <div class="evidence-form">
              <input v-model="evidenceForm.evidence_type" placeholder="证据类型" />
              <input v-model="evidenceForm.object_ref" placeholder="对象引用" />
              <input v-model="evidenceForm.sha256" class="mono" placeholder="SHA-256" />
              <input v-model="evidenceForm.signed_by" placeholder="签名者" />
              <button class="button primary" :disabled="!evidenceForm.evidence_type || evidenceForm.sha256.length !== 64" @click="createEvidence"><Plus :size="16" />登记</button>
            </div>
          </div>
          <div class="table-scroll"><table class="data-table"><thead><tr><th>类型</th><th>对象</th><th>签名者</th><th>SHA-256</th></tr></thead><tbody>
            <tr v-for="item in evidence" :key="item.evidence_id"><td>{{ item.evidence_type }}</td><td class="truncate">{{ item.object_ref }}</td><td>{{ item.signed_by }}</td><td class="mono">{{ item.sha256.slice(0, 16) }}</td></tr>
          </tbody></table></div>
        </section>
      </div>
    </template>
  </section>
</template>

<style scoped>
.enterprise-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; align-items: start; }
.wide { grid-column: 1 / -1; }
.submit { margin-top: 14px; }
.record-list { display: grid; gap: 8px; margin-top: 16px; }
.record-list div { display: flex; justify-content: space-between; gap: 12px; padding-top: 8px; border-top: 1px solid var(--line); font-size: 12px; }
.record-list span { color: var(--muted); }
.evidence-form { display: grid; grid-template-columns: 1fr 1.5fr 1.5fr 1fr auto; gap: 8px; }
@media (max-width: 1040px) { .enterprise-grid { grid-template-columns: 1fr; } .wide { grid-column: auto; } .evidence-form { grid-template-columns: 1fr 1fr; } }
@media (max-width: 560px) { .evidence-form { grid-template-columns: 1fr; } }
</style>

