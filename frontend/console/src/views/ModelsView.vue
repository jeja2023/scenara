<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { api, userFacingError } from "../api";
import { labelCapability } from "../labels";
import type { ModelPackage } from "../types";

const models = ref<ModelPackage[]>([]);
const error = ref("");
const loading = ref(false);

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
        <span>已登记</span><strong>{{ models.length }}</strong
        ><small>不可变版本</small>
      </div>
      <div class="stat green">
        <span>生产就绪</span
        ><strong>{{
          models.filter((item) => item.production_ready).length
        }}</strong
        ><small>许可与回归已确认</small>
      </div>
      <div class="stat">
        <span>显存预算</span
        ><strong>{{
          models.reduce((sum, item) => sum + item.vram_mb, 0)
        }}</strong
        ><small>MiB</small>
      </div>
    </div>
    <section class="panel">
      <div class="panel-header">
        <h2>安装清单</h2>
        <span class="badge">{{ models.length }}</span>
      </div>
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width: 50px">序号</th>
              <th>模型</th>
              <th>能力</th>
              <th>适配器</th>
              <th>许可证</th>
              <th>显存</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(model, index) in models"
              :key="model.model_id + model.version"
            >
              <td class="muted">{{ index + 1 }}</td>
              <td>
                <strong>{{ model.model_id }}</strong>
                <div class="mono muted">
                  {{ model.version }} · {{ model.sha256.slice(0, 12) }}
                </div>
              </td>
              <td>{{ labelCapability(model.capability) }}</td>
              <td class="mono">{{ model.adapter }}</td>
              <td>{{ model.license_id }}</td>
              <td>{{ model.vram_mb }} MiB</td>
              <td>
                <span
                  class="badge"
                  :class="model.production_ready ? 'active' : ''"
                  >{{ model.production_ready ? "生产" : "开发" }}</span
                >
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!models.length" class="empty">没有已登记模型</div>
      </div>
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
