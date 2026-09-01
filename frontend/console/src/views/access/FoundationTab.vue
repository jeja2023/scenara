<script setup lang="ts">
import {
  Boxes,
  CheckCircle2,
  Clock,
  Lock,
  Server,
  ShieldAlert,
  ShieldCheck,
  Users,
} from "@lucide/vue";

import { labelAccessCapability, labelPolicyProvider } from "../../labels";
import type {
  AccessCapabilityStatus,
  AccessFoundationStatus,
  IamSummary,
} from "../../types";

defineProps<{
  foundation: AccessFoundationStatus | null;
  iam: IamSummary | null;
  loading: boolean;
  readiness: { available: number; planned: number; gated: number };
  statusLabels: Record<AccessCapabilityStatus, string>;
  authModeLabels: Record<string, string>;
  principalSourceLabels: Record<string, string>;
  labelContext: (value: string, kind: "租户" | "项目") => string;
}>();
</script>

<template>
  <div class="inventory-grid">
    <div class="stat teal">
      <div class="stat-top-row">
        <span class="stat-title">底座就绪状态</span>
        <div class="stat-icon-badge"><ShieldCheck :size="15" /></div>
      </div>
      <div class="stat-value">
        {{ readiness.available }}/{{ (foundation?.capabilities ?? []).length }}
      </div>
      <div class="stat-desc">
        {{ readiness.available }} 项已就绪 · {{ readiness.planned }} 项规划中 ·
        {{ readiness.gated }} 项受限
      </div>
    </div>

    <div class="stat">
      <div class="stat-top-row">
        <span class="stat-title">策略提供方</span>
        <div class="stat-icon-badge"><Lock :size="15" /></div>
      </div>
      <div class="stat-value">
        {{
          foundation
            ? labelPolicyProvider(foundation.policy_provider)
            : "未连接"
        }}
      </div>
      <div class="stat-desc">
        认证模式:
        {{ foundation ? authModeLabels[foundation.auth_mode] : "未知" }}
      </div>
    </div>

    <div class="stat green">
      <div class="stat-top-row">
        <span class="stat-title">鉴权主体模型</span>
        <div class="stat-icon-badge"><Users :size="15" /></div>
      </div>
      <div class="stat-value">
        {{
          foundation
            ? principalSourceLabels[foundation.principal_source]
            : "未知"
        }}
      </div>
      <div class="stat-desc">
        租户:
        {{ foundation ? labelContext(foundation.tenant_id, "租户") : "-" }}
        · 项目:
        {{ foundation ? labelContext(foundation.project_id, "项目") : "-" }}
      </div>
    </div>

    <div class="stat coral">
      <div class="stat-top-row">
        <span class="stat-title">接入资源总览</span>
        <div class="stat-icon-badge"><Boxes :size="15" /></div>
      </div>
      <div class="stat-value">
        {{
          (iam?.inventory.service_accounts ?? 0) +
          (iam?.inventory.api_keys ?? 0)
        }}
      </div>
      <div class="stat-desc">
        {{ iam?.inventory.service_accounts ?? 0 }} 个服务账号 ·
        {{ iam?.inventory.api_keys ?? 0 }} 个密钥
      </div>
    </div>
  </div>

  <section class="panel access-panel">
    <div class="panel-header">
      <div class="header-left">
        <Server :size="16" class="header-icon" />
        <h2>访问底座</h2>
        <span class="badge" :class="foundation ? 'available' : 'gated'">
          {{
            foundation
              ? labelPolicyProvider(foundation.policy_provider)
              : "未读取"
          }}
        </span>
      </div>
    </div>

    <!-- 基础元数据栏 -->
    <div class="foundation-meta">
      <div>
        <span>认证模式</span>
        <strong>{{
          foundation ? authModeLabels[foundation.auth_mode] : "?"
        }}</strong>
      </div>
      <div>
        <span>身份来源</span>
        <strong>{{
          foundation ? principalSourceLabels[foundation.principal_source] : "?"
        }}</strong>
      </div>
      <div>
        <span>作用域</span>
        <strong>
          {{ foundation ? labelContext(foundation.tenant_id, "租户") : "?" }}
          /
          {{ foundation ? labelContext(foundation.project_id, "项目") : "?" }}
        </strong>
      </div>
      <div>
        <span>能力分布</span>
        <strong
          >{{ readiness.available }} 可用 · {{ readiness.planned }} 规划 ·
          {{ readiness.gated }} 门禁</strong
        >
      </div>
    </div>

    <!-- 访问底座核心能力分列表格 -->
    <div class="table-scroll" style="margin-top: 8px">
      <table class="data-table iam-table">
        <thead>
          <tr>
            <th style="width: 48px; text-align: center">序号</th>
            <th style="min-width: 150px">能力名称</th>
            <th style="min-width: 260px">功能职责说明</th>
            <th style="width: 90px; text-align: center">当前状态</th>
            <th style="min-width: 320px">阶段目标与演进门禁</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(item, index) in foundation?.capabilities ?? []"
            :key="item.capability_id"
          >
            <td class="muted text-center">{{ index + 1 }}</td>
            <td>
              <div class="capability-cell">
                <component
                  :is="
                    item.status === 'available'
                      ? CheckCircle2
                      : item.status === 'planned'
                        ? Clock
                        : ShieldAlert
                  "
                  :size="14"
                  class="capability-status-icon"
                  :class="item.status"
                />
                <strong>{{
                  labelAccessCapability(item.capability_id).name
                }}</strong>
              </div>
            </td>
            <td :title="labelAccessCapability(item.capability_id).summary">
              {{ labelAccessCapability(item.capability_id).summary }}
            </td>
            <td class="text-center">
              <span
                class="badge status-pill"
                :class="
                  item.status === 'available'
                    ? 'active'
                    : item.status === 'planned'
                      ? 'ghost-badge'
                      : 'failed'
                "
              >
                <span class="status-dot"></span>
                {{ statusLabels[item.status] }}
              </span>
            </td>
            <td
              class="muted"
              :title="labelAccessCapability(item.capability_id).nextGate"
            >
              {{ labelAccessCapability(item.capability_id).nextGate }}
            </td>
          </tr>
          <tr v-if="!foundation?.capabilities?.length">
            <td colspan="5" class="empty">
              {{ loading ? "正在加载访问底座状态..." : "未读取到访问底座状态" }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
