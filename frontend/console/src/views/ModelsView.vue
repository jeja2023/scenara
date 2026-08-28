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

const domainTabs = [
  { id: "all", label: "全部模型", icon: Layers },
  { id: "portrait", label: "人像视觉", icon: User },
  { id: "ocr", label: "OCR 文档", icon: FileText },
  { id: "behavior", label: "行为动作", icon: Activity },
  { id: "fashion", label: "服饰风格", icon: Shirt },
];

const columns: TableColumn<ModelPackage>[] = [
  { key: "model", label: "模型名称与标识" },
  { key: "domain", label: "业务领域" },
  { key: "capability", label: "核心算法能力" },
  { key: "adapter", label: "运行时适配器" },
  { key: "license_id", label: "授权许可" },
  { key: "vram_mb", label: "显存占用" },
  { key: "status", label: "准入状态" },
];

// 计算过滤后的模型列表
const filteredModels = computed(() => {
  let list = models.value;
  if (selectedDomain.value !== "all") {
    list = list.filter(
      (m) => (m.domain || inferDomain(m.model_id)) === selectedDomain.value
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
    <section class="panel">
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
            <Search :size="14" class="search-icon" />
            <input
              v-model="searchQuery"
              type="text"
              placeholder="搜索模型、能力或适配器..."
              class="search-input"
            />
          </div>
        </div>
      </div>

      <DataTable
        :columns="columns"
        :items="filteredModels"
        :loading="loading"
        empty-text="暂无匹配的模型数据"
      >
        <!-- 1. 模型名称与元信息 -->
        <template #model="{ row }">
          <div class="model-cell">
            <div class="model-title">{{ labelModelName(row.model_id) }}</div>
            <div class="model-subtitle mono">
              <span>{{ row.model_id }}</span>
              <span class="dot-sep">·</span>
              <span class="ver-tag">v{{ row.version }}</span>
              <span class="dot-sep">·</span>
              <span title="SHA256 完整哈希" class="hash-tag">{{ row.sha256.slice(0, 8) }}</span>
            </div>
          </div>
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
          <div class="adapter-cell">
            <span class="adapter-name">{{ labelAdapter(row.adapter) }}</span>
            <span class="adapter-code mono">({{ row.adapter }})</span>
          </div>
        </template>

        <!-- 5. 许可证 -->
        <template #license_id="{ row }">
          <span class="license-tag mono">
            {{ labelLicense(row.license_id) }}
          </span>
        </template>

        <!-- 6. 显存 -->
        <template #vram_mb="{ row }">
          <div class="vram-cell">
            <span class="vram-text">{{ row.vram_mb }} MiB</span>
            <div class="vram-bar-wrap">
              <div
                class="vram-bar-fill"
                :style="{ width: `${Math.min(100, (row.vram_mb / 512) * 100)}%` }"
              />
            </div>
          </div>
        </template>

        <!-- 7. 状态 -->
        <template #status="{ row }">
          <span
            class="badge status-badge"
            :class="row.production_ready ? 'active' : ''"
          >
            <span class="status-dot" :class="row.production_ready ? 'dot-active' : 'dot-dev'" />
            {{ row.production_ready ? "生产准入" : "开发测试" }}
          </span>
        </template>
      </DataTable>
    </section>
  </section>
</template>

<style scoped>
.model-stats {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-bottom: 20px;
}
.stat-unit {
  font-size: 14px;
  font-weight: 500;
  color: var(--muted, #64748b);
  margin-left: 4px;
}

.panel-header-custom {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-left h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.domain-tabs {
  display: inline-flex;
  align-items: center;
  background: var(--surface-subtle, rgba(0, 0, 0, 0.04));
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 8px;
  padding: 2px;
  gap: 2px;
}

.domain-tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 500;
  color: var(--muted, #64748b);
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.domain-tab-btn:hover {
  color: var(--text-color, #0f172a);
  background: rgba(255, 255, 255, 0.5);
}

.domain-tab-btn.active {
  color: var(--primary, #0284c7);
  background: var(--surface, #ffffff);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  font-weight: 600;
}

.search-box {
  position: relative;
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: 10px;
  color: var(--muted, #94a3b8);
  pointer-events: none;
}

.search-input {
  padding: 6px 12px 6px 30px;
  font-size: 12px;
  border: 1px solid var(--border-color, #cbd5e1);
  border-radius: 6px;
  background: var(--surface, #ffffff);
  color: var(--text-color, #0f172a);
  outline: none;
  width: 220px;
  transition: border-color 0.2s ease;
}

.search-input:focus {
  border-color: var(--primary, #0284c7);
}

/* 表格列样式 */
.model-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.model-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-color, #0f172a);
}

.model-subtitle {
  font-size: 11px;
  color: var(--muted, #64748b);
  display: flex;
  align-items: center;
  gap: 4px;
}

.dot-sep {
  opacity: 0.5;
}

.ver-tag {
  color: var(--primary, #0284c7);
  font-weight: 500;
}

.hash-tag {
  background: var(--surface-subtle, rgba(0, 0, 0, 0.04));
  padding: 1px 4px;
  border-radius: 3px;
}

.domain-tag {
  display: inline-block;
  padding: 3px 8px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;
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
  font-size: 12px;
  font-weight: 500;
  color: var(--text-color, #1e293b);
}

.adapter-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.adapter-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-color, #0f172a);
}

.adapter-code {
  font-size: 11px;
  color: var(--muted, #94a3b8);
}

.license-tag {
  font-size: 11px;
  padding: 2px 6px;
  background: var(--surface-subtle, rgba(0, 0, 0, 0.04));
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 4px;
  color: var(--muted, #475569);
}

.vram-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 90px;
}

.vram-text {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-color, #0f172a);
}

.vram-bar-wrap {
  height: 4px;
  background: var(--surface-subtle, rgba(0, 0, 0, 0.08));
  border-radius: 2px;
  overflow: hidden;
}

.vram-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #38bdf8, #818cf8);
  border-radius: 2px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 500;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.dot-active {
  background: #22c55e;
  box-shadow: 0 0 6px rgba(34, 197, 94, 0.6);
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

