<script setup lang="ts">
import {
  Activity,
  Box,
  CheckCircle2,
  Cpu,
  FileText,
  Layers,
  Search,
  Shirt,
  User,
  X,
} from "@lucide/vue";
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

const domainTabs = [
  { id: "all", label: "全部模型", icon: Layers },
  { id: "portrait", label: "人像视觉", icon: User },
  { id: "ocr", label: "OCR 文档", icon: FileText },
  { id: "behavior", label: "行为动作", icon: Activity },
  { id: "fashion", label: "服饰风格", icon: Shirt },
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
        <div class="stat-desc">4 大业务领域预置算法</div>
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
        <div class="stat-desc">签名校验与合规已确认</div>
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
          <h2>已装配模型库</h2>
          <span class="badge">{{ filteredModels.length }} / {{ models.length }}</span>
        </div>

        <div class="header-actions">
          <!-- 领域切换 Tabs -->
          <div class="domain-tabs">
            <button
              v-for="tab in domainTabs"
              :key="tab.id"
              type="button"
              class="domain-tab-btn"
              :class="{ active: selectedDomain === tab.id }"
              @click="selectedDomain = tab.id"
            >
              <component :is="tab.icon" :size="13" />
              <span>{{ tab.label }}</span>
            </button>
          </div>

          <!-- 快速搜索框 -->
          <div class="search-box">
            <Search :size="13" class="search-icon" />
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
          <span class="model-name-text" :title="`${row.model_id} (v${row.version})`">
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
          <span class="badge status-badge" :class="row.production_ready ? 'active' : ''">
            <span class="status-dot" :class="row.production_ready ? 'dot-active' : 'dot-dev'" />
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
  gap: 10px;
  flex-wrap: wrap;
}

/* 领域分类 Tabs */
.domain-tabs {
  display: inline-flex;
  align-items: center;
  background: #eef2f1;
  padding: 2px;
  border-radius: 6px;
  gap: 2px;
}

.domain-tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 9px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: var(--muted, #64716d);
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.domain-tab-btn:hover {
  color: var(--graphite, #17211f);
  background: rgba(255, 255, 255, 0.6);
}

.domain-tab-btn.active {
  color: var(--primary, #0ea5e9);
  background: #ffffff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  font-weight: 600;
}

/* 搜索框：固定尺寸、不因 focus 改变宽度、居中对齐图标与清除按钮 */
.search-box {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--muted, #64716d);
  pointer-events: none;
  z-index: 1;
}

.search-input {
  height: 28px;
  line-height: 28px;
  width: 185px;
  padding: 0 24px 0 32px;
  font-size: 11.5px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  background: #ffffff;
  color: var(--graphite, #17211f);
  outline: none;
  box-sizing: border-box;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
}


.search-input:focus {
  border-color: var(--primary, #0ea5e9);
  box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.12);
  /* 严格禁止改变 width */
}

.search-input::placeholder {
  color: #94a3b8;
  font-size: 11.5px;
}

.search-clear-btn {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 15px;
  height: 15px;
  border: none;
  border-radius: 50%;
  background: #e2e8e6;
  color: #64716d;
  cursor: pointer;
  padding: 0;
  transition: all 0.12s ease;
}

.search-clear-btn:hover {
  background: #cbd5e1;
  color: #17211f;
}

/* 固定表格区域最小高度，防止切换页码（如10条切到8条）或筛选时表格区域发生高度抖动 */
:deep(.models-table-wrapper .table-scroll) {
  min-height: 428px;
}

/* 单行表格列样式 */
:deep(.models-table td),
:deep(.models-table th) {
  white-space: nowrap !important;
  vertical-align: middle;
  padding: 8px 12px;
  height: 39px;
  box-sizing: border-box;
}

.model-name-text {
  font-size: 12px;
  font-weight: 600;
  color: var(--graphite, #17211f);
  white-space: nowrap;
}

.domain-tag {
  display: inline-block;
  padding: 2px 7px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;
  white-space: nowrap;
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
}

.adapter-text {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--graphite, #17211f);
  white-space: nowrap;
}

.license-tag {
  font-size: 11px;
  padding: 2px 6px;
  background: #f1f5f4;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  color: var(--muted, #64716d);
  font-family: var(--font-mono, monospace);
  white-space: nowrap;
}

.vram-text {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--graphite, #17211f);
  white-space: nowrap;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  white-space: nowrap;
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
