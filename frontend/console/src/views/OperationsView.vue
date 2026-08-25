<script setup lang="ts">
import { Cpu, Database, HardDrive, Server } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { api, userFacingError } from "../api";
import { labelRuntime, labelVersion } from "../labels";
import DataTable from "../components/DataTable.vue";
import type { TableColumn } from "../types";

interface Status {
  version: string;
  profile: string;
  state_backend: string;
  object_backend: string;
  queue_backend: string;
  production_models_required: boolean;
  auth_required: boolean;
}

interface GateCheck {
  id: string;
  name: string;
  category: string;
  description: string;
  status: string;
  statusClass: string;
}

const status = ref<Status | null>(null);
const loading = ref(false);
const error = ref("");

const checkColumns: TableColumn<GateCheck>[] = [
  { key: "name", label: "检查项" },
  { key: "category", label: "分类" },
  { key: "description", label: "校验说明", class: "muted" },
  { key: "status", label: "当前状态" },
];

const checkRows = computed<GateCheck[]>(() => [
  {
    id: "auth",
    name: "接口认证",
    category: "访问控制",
    description: "强校验 HTTP 接口访问令牌与会话认证凭据",
    status: status.value?.auth_required ? "开启" : "开发关闭",
    statusClass: status.value?.auth_required ? "active" : "paused",
  },
  {
    id: "models",
    name: "生产模型强制",
    category: "算法合规",
    description: "生产环境离线部署强制校验模型包文件与签名完整性",
    status: status.value?.production_models_required ? "开启" : "开发关闭",
    statusClass: status.value?.production_models_required ? "active" : "paused",
  },
  {
    id: "audit",
    name: "审计持久化",
    category: "合规审计",
    description: "存储底层具备完整安全审计事件与数据控制面结构表",
    status: "数据结构已建立",
    statusClass: "completed",
  },
  {
    id: "backup",
    name: "备份恢复证据",
    category: "容灾可靠性",
    description: "定期验证完整备份恢复与 RPO/RTO 演练签名报告",
    status: "待验证",
    statusClass: "paused",
  },
]);

async function refresh(): Promise<void> {
  loading.value = true;
  try {
    status.value = await api<Status>("/api/v1/system/status");
  } catch (caught) {
    error.value = userFacingError(caught, "运行状态加载失败，请稍后重试");
  } finally {
    loading.value = false;
  }
}
onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page">
    <p v-if="error" class="callout error">{{ error }}</p>
    <div v-if="status" class="stats">
      <div class="stat teal">
        <div class="stat-top-row">
          <span class="stat-title">配置档</span>
          <div class="stat-icon-badge">
            <Server :size="15" />
          </div>
        </div>
        <div class="stat-value">{{ status.profile }}</div>
        <div class="stat-desc">环境模式</div>
      </div>

      <div class="stat green">
        <div class="stat-top-row">
          <span class="stat-title">持久化状态</span>
          <div class="stat-icon-badge">
            <Database :size="15" />
          </div>
        </div>
        <div class="stat-value">{{ labelRuntime(status.state_backend) }}</div>
        <div class="stat-desc">系统元数据</div>
      </div>

      <div class="stat coral">
        <div class="stat-top-row">
          <span class="stat-title">对象存储</span>
          <div class="stat-icon-badge">
            <HardDrive :size="15" />
          </div>
        </div>
        <div class="stat-value">{{ labelRuntime(status.object_backend) }}</div>
        <div class="stat-desc">产物与原始资产</div>
      </div>

      <div class="stat teal">
        <div class="stat-top-row">
          <span class="stat-title">消息队列</span>
          <div class="stat-icon-badge">
            <Cpu :size="15" />
          </div>
        </div>
        <div class="stat-value">{{ labelRuntime(status.queue_backend) }}</div>
        <div class="stat-desc">执行调度投递</div>
      </div>
    </div>
    <section class="panel">
      <div class="panel-header"><h2>门禁状态与校验</h2></div>
      <DataTable
        :columns="checkColumns"
        :items="checkRows"
        :loading="loading"
      >
        <template #name="{ row }">
          <strong>{{ row.name }}</strong>
        </template>
        <template #category="{ row }">
          <span class="badge">{{ row.category }}</span>
        </template>
        <template #status="{ row }">
          <span class="badge" :class="row.statusClass">{{ row.status }}</span>
        </template>
      </DataTable>
    </section>
  </section>
</template>

<style scoped>
.checks {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  padding: 0;
  background: var(--line);
}
.checks div {
  display: flex;
  justify-content: space-between;
  padding: 15px;
  background: #fff;
  font-size: 13px;
}
.ok {
  color: var(--green);
}
.warn {
  color: var(--amber);
}
</style>
