<script setup lang="ts">
import { BellPlus, Plus, Radio, Search, Trash2, X } from "@lucide/vue";

import DataTablePagination from "../../components/DataTablePagination.vue";
import { labelDeliveryStatus, labelEventType } from "../../labels";
import type { WebhookDelivery, WebhookSubscription } from "../../types";

const {
  subscriptions,
  deliveries,
  subscriptionItems,
  subscriptionTotal,
  deliveryItems,
  deliveryTotal,
  removeHook,
  formatTime,
} = defineProps<{
  subscriptions: WebhookSubscription[];
  deliveries: WebhookDelivery[];
  subscriptionItems: WebhookSubscription[];
  subscriptionTotal: number;
  deliveryItems: WebhookDelivery[];
  deliveryTotal: number;
  removeHook: (endpointId: string) => void | Promise<void>;
  formatTime: (value: number) => string;
}>();
const emit = defineEmits<{ (event: "open-create"): void }>();
const eventTab = defineModel<"subscriptions" | "deliveries">("eventTab", {
  required: true,
});
const subscriptionSearch = defineModel<string>("subscriptionSearch", {
  required: true,
});
const deliveryStatus = defineModel<
  "all" | "queued" | "delivered" | "dead_letter"
>("deliveryStatus", { required: true });
const subscriptionPagination = defineModel<{
  offset: number;
  pageSize: number;
}>("subscriptionPagination", { required: true });
const deliveryPagination = defineModel<{ offset: number; pageSize: number }>(
  "deliveryPagination",
  { required: true },
);
</script>

<template>
  <!-- 事件回调子模块 Tab 切换栏 -->
  <div class="tabs-header-bar subtabs-bar">
    <div class="domain-tabs" role="tablist" aria-label="事件回调子视图">
      <button
        type="button"
        class="domain-tab-btn"
        :class="{ active: eventTab === 'subscriptions' }"
        @click="eventTab = 'subscriptions'"
      >
        <BellPlus :size="13" />
        <span>事件回调订阅</span>
        <span class="tab-badge">{{ subscriptions.length }}</span>
      </button>
      <button
        type="button"
        class="domain-tab-btn"
        :class="{ active: eventTab === 'deliveries' }"
        @click="eventTab = 'deliveries'"
      >
        <Radio :size="13" />
        <span>投递日志</span>
        <span class="tab-badge">{{ deliveries.length }}</span>
      </button>
    </div>
  </div>

  <!-- 子视图 1：事件回调订阅 (Subscriptions) -->
  <section v-if="eventTab === 'subscriptions'" class="panel">
    <div class="panel-header">
      <div class="header-left">
        <BellPlus :size="16" class="header-icon" />
        <h2>事件回调订阅</h2>
        <span class="badge">{{ subscriptions.length }}</span>
      </div>
      <div class="header-actions">
        <div class="search-box">
          <Search :size="13" class="search-icon" />
          <input
            v-model="subscriptionSearch"
            placeholder="搜索订阅名称 / 端点 / URL..."
            class="search-input"
          />
          <button
            v-if="subscriptionSearch"
            class="clear-search-btn"
            @click="subscriptionSearch = ''"
          >
            <X :size="12" />
          </button>
        </div>
        <button class="button primary tiny-btn" @click="emit('open-create')">
          <Plus :size="13" />添加订阅
        </button>
      </div>
    </div>

    <!-- 订阅表格 -->
    <div class="table-scroll">
      <table class="data-table iam-table">
        <thead>
          <tr>
            <th style="width: 48px; text-align: center">序号</th>
            <th style="min-width: 150px">订阅名称</th>
            <th style="min-width: 130px">端点标识</th>
            <th style="min-width: 200px">HTTPS 回调地址</th>
            <th style="min-width: 160px">监听事件类型</th>
            <th style="width: 80px; text-align: center">状态</th>
            <th style="width: 60px; text-align: center">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(item, index) in subscriptionItems"
            :key="item.endpoint_id"
          >
            <td class="muted text-center">
              {{ index + 1 + subscriptionPagination.offset }}
            </td>
            <td>
              <strong>{{ item.name }}</strong>
            </td>
            <td class="mono muted-id">{{ item.endpoint_id }}</td>
            <td class="mono muted">{{ item.url }}</td>
            <td>
              <div class="role-tags-cell">
                <span
                  v-for="et in item.event_types"
                  :key="et"
                  class="badge event-pill"
                >
                  {{ labelEventType(et) }}
                </span>
              </div>
            </td>
            <td class="text-center">
              <span
                class="badge status-pill"
                :class="item.enabled ? 'active' : 'failed'"
              >
                <span class="status-dot"></span>
                {{ item.enabled ? "启用" : "停用" }}
              </span>
            </td>
            <td class="text-center">
              <button
                class="icon-button danger-icon"
                title="删除订阅"
                @click="removeHook(item.endpoint_id)"
              >
                <Trash2 :size="13" />
              </button>
            </td>
          </tr>
          <tr v-if="!subscriptionTotal">
            <td colspan="7" class="empty">
              {{
                subscriptions.length
                  ? "未找到符合条件的回调订阅"
                  : "暂无事件回调订阅"
              }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <DataTablePagination
      v-if="subscriptionTotal"
      :total="subscriptionTotal"
      :offset="subscriptionPagination.offset"
      :page-size="subscriptionPagination.pageSize"
      :page-size-options="[10, 20, 50, 100]"
      @update:offset="subscriptionPagination.offset = $event"
      @update:page-size="subscriptionPagination.pageSize = $event"
    />
  </section>

  <!-- 子视图 2：投递日志 (Deliveries) -->
  <section v-else-if="eventTab === 'deliveries'" class="panel">
    <div class="panel-header">
      <div class="header-left">
        <Radio :size="16" class="header-icon" />
        <h2>投递日志</h2>
        <span class="badge">{{ deliveries.length }}</span>
      </div>
      <div class="header-actions">
        <select v-model="deliveryStatus" class="filter-select-sm">
          <option value="all">全部投递状态 ({{ deliveries.length }})</option>
          <option value="delivered">仅已成功投递</option>
          <option value="dead_letter">仅死信失败</option>
          <option value="queued">仅排队重试中</option>
        </select>
      </div>
    </div>

    <div class="table-scroll">
      <table class="data-table iam-table">
        <thead>
          <tr>
            <th style="width: 48px; text-align: center">序号</th>
            <th style="min-width: 140px">事件类型</th>
            <th style="min-width: 140px">事件标识</th>
            <th style="min-width: 130px">目标端点</th>
            <th style="width: 100px; text-align: center">投递状态</th>
            <th style="width: 80px; text-align: center">尝试次数</th>
            <th style="width: 90px; text-align: center">HTTP 状态码</th>
            <th style="width: 150px">记录时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, index) in deliveryItems" :key="item.delivery_id">
            <td class="muted text-center">
              {{ index + 1 + deliveryPagination.offset }}
            </td>
            <td>
              <strong>{{ labelEventType(item.event_type) }}</strong>
            </td>
            <td class="mono muted-id">{{ item.event_id }}</td>
            <td class="mono muted">{{ item.endpoint_id }}</td>
            <td class="text-center">
              <span
                class="badge"
                :class="
                  item.status === 'delivered'
                    ? 'status-pill active'
                    : item.status === 'dead_letter'
                      ? 'status-pill failed'
                      : 'ghost-badge'
                "
              >
                <span class="status-dot"></span>
                {{ labelDeliveryStatus(item.status) }}
              </span>
            </td>
            <td class="text-center">
              <span class="badge ghost-badge">{{ item.attempts }} 次</span>
            </td>
            <td class="text-center">
              <span
                v-if="item.status_code"
                class="badge http-status-badge"
                :class="
                  item.status_code >= 200 && item.status_code < 300
                    ? 'status-2xx'
                    : 'status-err'
                "
              >
                {{ item.status_code }}
              </span>
              <span v-else class="muted">-</span>
            </td>
            <td class="muted">{{ formatTime(item.updated_at) }}</td>
          </tr>
          <tr v-if="!deliveryTotal">
            <td colspan="8" class="empty">暂无投递记录</td>
          </tr>
        </tbody>
      </table>
    </div>
    <DataTablePagination
      v-if="deliveryTotal"
      :total="deliveryTotal"
      :offset="deliveryPagination.offset"
      :page-size="deliveryPagination.pageSize"
      :page-size-options="[10, 20, 50, 100]"
      @update:offset="deliveryPagination.offset = $event"
      @update:page-size="deliveryPagination.pageSize = $event"
    />
  </section>
</template>
