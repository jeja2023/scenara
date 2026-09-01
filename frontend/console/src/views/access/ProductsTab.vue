<script setup lang="ts">
import { Plus, Search, ShieldCheck, X } from "@lucide/vue";

import DataTablePagination from "../../components/DataTablePagination.vue";
import {
  labelEntitlementSource,
  labelProduct,
  labelProductSummary,
} from "../../labels";
import type { ProductEntitlement } from "../../types";

const {
  entitlements,
  items,
  filteredCount,
  search,
  offset,
  pageSize,
  formatTime,
} = defineProps<{
  entitlements: ProductEntitlement[];
  items: ProductEntitlement[];
  filteredCount: number;
  search: string;
  offset: number;
  pageSize: number;
  formatTime: (value: number) => string;
}>();
const emit = defineEmits<{
  (event: "update:search", value: string): void;
  (event: "update:offset", value: number): void;
  (event: "update:pageSize", value: number): void;
  (event: "open-create"): void;
}>();
</script>

<template>
  <section class="panel">
    <div class="panel-header">
      <div class="header-left">
        <ShieldCheck :size="16" class="header-icon" />
        <h2>项目产品授权</h2>
        <span class="badge">{{ entitlements.length }}</span>
      </div>
      <div class="header-actions">
        <div class="search-box">
          <Search :size="13" class="search-icon" />
          <input
            :value="search"
            placeholder="搜索产品授权 / 项目..."
            class="search-input"
            @input="
              emit('update:search', ($event.target as HTMLInputElement).value)
            "
          />
          <button
            v-if="search"
            class="clear-search-btn"
            @click="emit('update:search', '')"
          >
            <X :size="12" />
          </button>
        </div>
        <button class="button primary tiny-btn" @click="emit('open-create')">
          <Plus :size="13" />配置产品授权
        </button>
      </div>
    </div>

    <!-- 产品授权数据表格 -->
    <div class="table-scroll">
      <table class="data-table iam-table">
        <thead>
          <tr>
            <th style="width: 48px; text-align: center">序号</th>
            <th style="min-width: 150px">产品名称</th>
            <th style="min-width: 110px">产品标识</th>
            <th style="min-width: 220px">产品职责与能力范围</th>
            <th style="min-width: 110px">所属项目</th>
            <th style="width: 100px; text-align: center">授权来源</th>
            <th style="width: 90px; text-align: center">授权状态</th>
            <th style="width: 140px">更新时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, index) in items" :key="item.product_id">
            <td class="muted text-center">
              {{ index + 1 + offset }}
            </td>
            <td>
              <strong>{{ labelProduct(item.product_id) }}</strong>
            </td>
            <td class="mono muted-id">{{ item.product_id }}</td>
            <td class="muted" :title="labelProductSummary(item.product_id)">
              {{ labelProductSummary(item.product_id) }}
            </td>
            <td class="mono muted">{{ item.project_id }}</td>
            <td class="text-center">
              <span class="badge ghost-badge">{{
                labelEntitlementSource(item.source)
              }}</span>
            </td>
            <td class="text-center">
              <span
                class="badge status-pill"
                :class="item.status === 'active' ? 'active' : 'failed'"
              >
                <span class="status-dot"></span>
                {{ item.status === "active" ? "启用" : "暂停" }}
              </span>
            </td>
            <td class="muted">{{ formatTime(item.updated_at) }}</td>
          </tr>
          <tr v-if="!filteredCount">
            <td colspan="8" class="empty">
              {{
                entitlements.length
                  ? "未找到符合条件的产品授权"
                  : "当前项目没有产品授权"
              }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <DataTablePagination
      v-if="filteredCount"
      :total="filteredCount"
      :offset="offset"
      :page-size="pageSize"
      :page-size-options="[10, 20, 50, 100]"
      @update:offset="emit('update:offset', $event)"
      @update:page-size="emit('update:pageSize', $event)"
    />
  </section>
</template>
