<script setup lang="ts">
import { Box, CheckCircle2, Cpu, Filter, Search, X } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { useRefresh } from "../composables/useRefresh";
import { api, userFacingError } from "../api";
import {
  labelAdapter,
  labelCapability,
  labelDomain,
  labelLicense,
  labelModelName,
} from "../labels";
import DataTable from "../components/DataTable.vue";
import type { ModelPackage, TableColumn } from "../types";

const models = ref<ModelPackage[]>([]);
const error = ref("");
const loading = ref(false);
const searchQuery = ref("");
const selectedDomain = ref<string>("all");
const pageSize = ref(10);

const domainOptions = [
  { id: "all", label: "全部模型" },
  { id: "portrait", label: "人像视觉" },
  { id: "ocr", label: "OCR 文档" },
  { id: "behavior", label: "行为动作" },
  { id: "fashion", label: "服饰风格" },
];

const columns: TableColumn<ModelPackage>[] = [
  { key: "model", label: "模型名称" },
  { key: "domain", label: "业务领域" },
  { key: "capability", label: "算法能力" },
  { key: "adapter", label: "适配器" },
  { key: "license_id", label: "授权许可" },
  { key: "vram_mb", label: "显存占用" },
  { key: "status", label: "准入状态" },
];

// 计算过滤后的模型列表
const filteredModels = computed(() => {
  let list = models.value;
  if (selectedDomain.value !== "all") {
    list = list.filter(
      (m) => (m.domain || inferDomain(m.model_id)) === selectedDomain.value,
    );
  }
  const q = searchQuery.value.trim().toLowerCase();
  if (q) {
    list = list.filter((m) => {
      const name = labelModelName(m.model_id).toLowerCase();
      const cap = labelCapability(m.capability).toLowerCase();
      const adapter = labelAdapter(m.adapter).toLowerCase();
      const rawId = m.model_id.toLowerCase();
      return (
        name.includes(q) ||
        cap.includes(q) ||
        adapter.includes(q) ||
        rawId.includes(q)
      );
    });
  }
  return list;
});

function clearSearch(): void {
  searchQuery.value = "";
}

function inferDomain(modelId: string): string {
  if (modelId.includes(".ocr.") || modelId.includes("/ocr")) return "ocr";
  if (modelId.includes(".behavior.") || modelId.includes("/behavior"))
    return "behavior";
  if (modelId.includes(".fashion.") || modelId.includes("/fashion"))
    return "fashion";
  return "portrait";
}

function domainBadgeClass(domain: string): string {
  switch (domain) {
    case "portrait":
      return "domain-badge-portrait";
    case "ocr":
      return "domain-badge-ocr";
    case "behavior":
      return "domain-badge-behavior";
    case "fashion":
      return "domain-badge-fashion";
    default:
      return "";
  }
}

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

    <!-- 顶部核心指标看板 -->
    <div class="stats model-stats">
      <div class="stat teal">
        <div class="stat-top-row">
          <span class="stat-title">已登记模型</span>
          <div class="stat-icon-badge">
            <Box :size="15" />
          </div>
        </div>
        <div class="stat-value">{{ models.length }}</div>
        <div class="stat-desc">仅统计已登记、可追溯的模型包</div>
      </div>

      <div class="stat green">
        <div class="stat-top-row">
          <span class="stat-title">生产准入就绪</span>
          <div class="stat-icon-badge">
            <CheckCircle2 :size="15" />
          </div>
        </div>
        <div class="stat-value">
          {{ models.filter((item) => item.production_ready).length }}
        </div>
        <div class="stat-desc">已登记模型中通过生产准入的数量</div>
      </div>

      <div class="stat amber">
        <div class="stat-top-row">
          <span class="stat-title">预估显存预算</span>
          <div class="stat-icon-badge">
            <Cpu :size="15" />
          </div>
        </div>
        <div class="stat-value">
          {{ models.reduce((sum, item) => sum + item.vram_mb, 0) }}
          <span class="stat-unit">MiB</span>
        </div>
        <div class="stat-desc">全量模型并发显存峰值</div>
      </div>
    </div>

    <!-- 模型清单主卡片 -->
    <section class="panel models-panel">
      <div class="panel-header-custom">
        <div class="header-left">
          <h2>已登记模型包</h2>
          <span class="badge"
            >{{ filteredModels.length }} / {{ models.length }}</span
          >
        </div>

        <div class="header-actions">
          <!-- 模型类型筛选下拉框 -->
          <label class="filter-item">
            <Filter :size="12" class="filter-icon" />
            <span class="filter-label">模型类型:</span>
            <select v-model="selectedDomain" class="filter-select">
              <option
                v-for="opt in domainOptions"
                :key="opt.id"
                :value="opt.id"
              >
                {{ opt.label }}
              </option>
            </select>
          </label>

          <!-- 快速搜索框 -->
          <div class="search-box search-sm">
            <Search :size="12" class="search-icon" />
            <input
              v-model="searchQuery"
              type="text"
              placeholder="搜索模型、能力..."
              class="search-input"
            />
            <button
              v-if="searchQuery"
              type="button"
              class="search-clear-btn"
              title="清空搜索"
              @click="clearSearch"
            >
              <X :size="11" />
            </button>
          </div>
        </div>
      </div>

      <DataTable
        :columns="columns"
        :items="filteredModels"
        :loading="loading"
        :page-size="pageSize"
        :page-size-options="[10, 20, 50, 100]"
        :show-page-size-selector="true"
        :show-jumper="true"
        table-class="models-table"
        wrapper-class="models-table-wrapper"
        empty-text="暂无匹配的模型数据"
      >
        <!-- 1. 模型名称 -->
        <template #model="{ row }">
          <span
            class="model-name-text"
            :title="`${row.model_id} (v${row.version})`"
          >
            {{ labelModelName(row.model_id) }}
          </span>
        </template>

        <!-- 2. 领域 -->
        <template #domain="{ row }">
          <span
            class="domain-tag"
            :class="domainBadgeClass(row.domain || inferDomain(row.model_id))"
          >
            {{ labelDomain(row.domain || inferDomain(row.model_id)) }}
          </span>
        </template>

        <!-- 3. 能力 -->
        <template #capability="{ row }">
          <span class="cap-tag">
            {{ labelCapability(row.capability) }}
          </span>
        </template>

        <!-- 4. 适配器 -->
        <template #adapter="{ row }">
          <span class="adapter-text" :title="row.adapter">
            {{ labelAdapter(row.adapter) }}
          </span>
        </template>

        <!-- 5. 许可证 -->
        <template #license_id="{ row }">
          <span class="license-tag" :title="labelLicense(row.license_id)">
            {{ row.license_id }}
          </span>
        </template>

        <!-- 6. 显存 -->
        <template #vram_mb="{ row }">
          <span class="vram-text">{{ row.vram_mb }} MiB</span>
        </template>

        <!-- 7. 准入状态 -->
        <template #status="{ row }">
          <span
            class="badge status-badge"
            :class="row.production_ready ? 'active' : ''"
          >
            <span
              class="status-dot"
              :class="row.production_ready ? 'dot-active' : 'dot-dev'"
            />
            {{ row.production_ready ? "生产准入" : "开发测试" }}
          </span>
        </template>
      </DataTable>
    </section>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 统计卡片微调 */
.model-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}

.stat-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.stat-icon-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.04);
  color: inherit;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
  margin-bottom: 2px;
}

.stat-unit {
  font-size: 13px;
  font-weight: 500;
  margin-left: 2px;
  opacity: 0.8;
}

.stat-desc {
  font-size: 11.5px;
  color: var(--muted, #64716d);
}

/* 主面板头部 */
.panel-header-custom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  flex-wrap: wrap;
  gap: 12px;
  background: #fafbfb;
  border-top-left-radius: var(--radius-md, 8px);
  border-top-right-radius: var(--radius-md, 8px);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-left h2 {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  color: var(--graphite, #17211f);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--muted, #64716d);
}

.filter-icon {
  color: var(--muted, #64716d);
}

.filter-label {
  font-weight: 500;
  font-size: 11px;
  white-space: nowrap;
  color: var(--muted, #64716d);
}

.filter-select {
  height: 22px;
  min-height: 22px;
  line-height: 20px;
  padding: 0 4px 0 6px;
  font-size: 11px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 3px;
  background: #ffffff;
  color: var(--graphite, #17211f);
  cursor: pointer;
  outline: none;
}
.filter-select:focus {
  border-color: var(--color-accent, #087682);
}

/* 固定表格区域最小高度（10条数据），防止切换页码或筛选时表格区域发生高度抖动 */
:deep(.models-table-wrapper .table-scroll) {
  min-height: 310px;
}

/* 严格使用全局统一的 28px 表格行高与 3px 8px 内边距 */
:deep(.models-table td),
:deep(.models-table th) {
  white-space: nowrap !important;
  vertical-align: middle;
  padding: 3px 8px !important;
  height: 28px !important;
  min-height: 28px !important;
  box-sizing: border-box;
  line-height: 1.3;
}

:deep(.models-table tr) {
  height: 28px;
}

.model-name-text {
  font-size: 12px;
  font-weight: 600;
  color: var(--graphite, #17211f);
  white-space: nowrap;
  line-height: 20px;
}

.domain-tag {
  display: inline-block;
  padding: 1px 6px;
  font-size: 10.5px;
  font-weight: 600;
  border-radius: 3px;
  white-space: nowrap;
  line-height: 16px;
}

.domain-badge-portrait {
  background: rgba(14, 165, 233, 0.12);
  color: #0284c7;
}

.domain-badge-ocr {
  background: rgba(168, 85, 247, 0.12);
  color: #9333ea;
}

.domain-badge-behavior {
  background: rgba(245, 158, 11, 0.12);
  color: #d97706;
}

.domain-badge-fashion {
  background: rgba(236, 72, 153, 0.12);
  color: #db2777;
}

.cap-tag {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--graphite, #17211f);
  white-space: nowrap;
  line-height: 20px;
}

.adapter-text {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--graphite, #17211f);
  white-space: nowrap;
  line-height: 20px;
}

.license-tag {
  font-size: 10.5px;
  padding: 1px 5px;
  background: #f1f5f4;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 3px;
  color: var(--muted, #64716d);
  font-family: var(--font-mono, monospace);
  white-space: nowrap;
  line-height: 16px;
}

.vram-text {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--graphite, #17211f);
  white-space: nowrap;
  line-height: 20px;
}

/* 按钮、徽章尺寸严格控制，绝不撑大表格行高 */
:deep(.models-table .badge),
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 18px;
  line-height: 18px;
  padding: 0 6px;
  font-size: 11px;
  white-space: nowrap;
}

:deep(.models-table .button),
:deep(.models-table .icon-button) {
  height: 20px !important;
  min-height: 20px !important;
  padding: 0 5px !important;
  font-size: 11px !important;
  line-height: 1 !important;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}

.dot-active {
  background: #22c55e;
  box-shadow: 0 0 5px rgba(34, 197, 94, 0.6);
}

.dot-dev {
  background: #38bdf8;
}

@media (max-width: 900px) {
  .header-actions {
    width: 100%;
    justify-content: space-between;
  }
  .domain-tabs {
    flex-wrap: wrap;
  }
}

@media (max-width: 700px) {
  .model-stats {
    grid-template-columns: 1fr;
  }
  .search-input {
    width: 100%;
  }
}
</style>
