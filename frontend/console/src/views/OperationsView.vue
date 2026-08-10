<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, userFacingError } from "../api";
import { labelRuntime, labelVersion } from "../labels";

interface Status {
  version: string;
  profile: string;
  state_backend: string;
  object_backend: string;
  queue_backend: string;
  production_models_required: boolean;
  auth_required: boolean;
}
const status = ref<Status | null>(null);
const error = ref("");
async function refresh(): Promise<void> {
  try {
    status.value = await api<Status>("/api/v1/system/status");
  } catch (caught) {
    error.value = userFacingError(caught, "运行状态加载失败，请稍后重试");
  }
}
onMounted(refresh);
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div>
        <h1>系统运维</h1>
        <p>运行后端与生产门禁状态。</p>
      </div>
      <button class="button secondary" @click="refresh">刷新</button>
    </div>
    <p v-if="error" class="callout error">{{ error }}</p>
    <div v-if="status" class="stats">
      <div class="stat teal">
        <span>配置档</span><strong>{{ labelRuntime(status.profile) }}</strong
        ><small>Scenara {{ labelVersion(status.version) }}</small>
      </div>
      <div class="stat">
        <span>状态存储</span
        ><strong>{{ labelRuntime(status.state_backend) }}</strong
        ><small>唯一事实源</small>
      </div>
      <div class="stat">
        <span>对象存储</span
        ><strong>{{ labelRuntime(status.object_backend) }}</strong
        ><small>媒体与结果文档</small>
      </div>
      <div class="stat green">
        <span>队列</span
        ><strong>{{ labelRuntime(status.queue_backend) }}</strong
        ><small>执行投递</small>
      </div>
    </div>
    <section class="panel">
      <div class="panel-header"><h2>门禁状态与校验</h2></div>
      <div class="table-scroll">
        <table class="data-table bordered-table">
          <thead>
            <tr>
              <th style="width: 50px">序号</th>
              <th>检查项</th>
              <th>分类</th>
              <th>校验说明</th>
              <th>当前状态</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td class="muted">1</td>
              <td><strong>接口认证</strong></td>
              <td><span class="badge">访问控制</span></td>
              <td class="muted">
                强校验 HTTP 接口访问令牌与会话认证凭据
              </td>
              <td>
                <span
                  class="badge"
                  :class="status?.auth_required ? 'active' : 'paused'"
                  >{{ status?.auth_required ? "开启" : "开发关闭" }}</span
                >
              </td>
            </tr>
            <tr>
              <td class="muted">2</td>
              <td><strong>生产模型强制</strong></td>
              <td><span class="badge">算法合规</span></td>
              <td class="muted">
                生产环境离线部署强制校验模型包文件与签名完整性
              </td>
              <td>
                <span
                  class="badge"
                  :class="
                    status?.production_models_required ? 'active' : 'paused'
                  "
                  >{{
                    status?.production_models_required ? "开启" : "开发关闭"
                  }}</span
                >
              </td>
            </tr>
            <tr>
              <td class="muted">3</td>
              <td><strong>审计持久化</strong></td>
              <td><span class="badge">合规审计</span></td>
              <td class="muted">
                存储底层具备完整安全审计事件与数据控制面结构表
              </td>
              <td>
                <span class="badge completed">数据结构已建立</span>
              </td>
            </tr>
            <tr>
              <td class="muted">4</td>
              <td><strong>备份恢复证据</strong></td>
              <td><span class="badge">容灾可靠性</span></td>
              <td class="muted">定期验证完整备份恢复与 RPO/RTO 演练签名报告</td>
              <td>
                <span class="badge paused">待验证</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
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
