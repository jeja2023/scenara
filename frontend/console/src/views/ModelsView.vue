<script setup lang="ts">
import { Box, CheckCircle2, Cpu } from "@lucide/vue";
import { onMounted, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { api, userFacingError } from "../api";
import { labelCapability } from "../labels";
import DataTable from "../components/DataTable.vue";
import type { ModelPackage, TableColumn } from "../types";

const models = ref<ModelPackage[]>([]);
const error = ref("");
const loading = ref(false);

const columns: TableColumn<ModelPackage>[] = [
  { key: "model", label: "模型" },
  { key: "capability", label: "能力" },
  { key: "adapter", label: "适配器", class: "mono" },
  { key: "license_id", label: "许可证" },
  { key: "vram_mb", label: "显存" },
  { key: "status", label: "状态" },
];

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    models.value = await api<ModelPackage[]>("/api/v1/models");
  } catch (caught) {
    error.value = userFacingError(caught, "模型数据加载失败，请稍后重试");
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
    <div class="stats model-stats">
      <div class="stat teal">
        <div class="stat-top-row">
          <span class="stat-title">已登记</span>
          <div class="stat-icon-badge">
            <Box :size="15" />
          </div>
        </div>
        <div class="stat-value">{{ models.length }}</div>
        <div class="stat-desc">不可变版本</div>
      </div>

      <div class="stat green">
        <div class="stat-top-row">
          <span class="stat-title">生产就绪</span>
          <div class="stat-icon-badge">
            <CheckCircle2 :size="15" />
          </div>
        </div>
        <div class="stat-value">
          {{ models.filter((item) => item.production_ready).length }}
        </div>
        <div class="stat-desc">许可与回归已确认</div>
      </div>

      <div class="stat amber">
        <div class="stat-top-row">
          <span class="stat-title">显存预算</span>
          <div class="stat-icon-badge">
            <Cpu :size="15" />
          </div>
        </div>
        <div class="stat-value">
          {{ models.reduce((sum, item) => sum + item.vram_mb, 0) }}
        </div>
        <div class="stat-desc">总额度 MiB</div>
      </div>
    </div>
    <section class="panel">
      <div class="panel-header">
        <h2>安装清单</h2>
        <span class="badge">{{ models.length }}</span>
      </div>
      <DataTable
        :columns="columns"
        :items="models"
        :loading="loading"
        empty-text="没有已登记模型"
      >
        <template #model="{ row }">
          <strong>{{ row.model_id }}</strong>
          <div class="mono muted">
            {{ row.version }} · {{ row.sha256.slice(0, 12) }}
          </div>
        </template>
        <template #capability="{ row }">
          {{ labelCapability(row.capability) }}
        </template>
        <template #vram_mb="{ row }">
          {{ row.vram_mb }} MiB
        </template>
        <template #status="{ row }">
          <span
            class="badge"
            :class="row.production_ready ? 'active' : ''"
          >
            {{ row.production_ready ? "生产" : "开发" }}
          </span>
        </template>
      </DataTable>
    </section>
  </section>
</template>

<style scoped>
.model-stats {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
@media (max-width: 700px) {
  .model-stats {
    grid-template-columns: 1fr;
  }
}
</style>
