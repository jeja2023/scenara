<script setup lang="ts">
const modules = [
  { name: "Policy Provider", state: "not_configured", scope: "Run 创建与生命周期策略挂钩" },
  { name: "Entitlements", state: "not_installed", scope: "授权与权益" },
  { name: "Metering", state: "not_installed", scope: "用量与配额" },
  { name: "SLA & Incident", state: "not_installed", scope: "服务质量与事故" },
  { name: "Compliance Evidence", state: "not_installed", scope: "合规证据" },
];
</script>

<template><section class="page"><div class="page-header"><div><h1>企业模块</h1><p>可选模块通过 Policy Provider 接入，核心平台不反向依赖。</p></div></div><p class="callout">当前版本未安装企业模块。此页面仅呈现接入状态，不提供不可用操作。</p><section class="panel enterprise-panel"><div class="table-scroll"><table class="data-table"><thead><tr><th>模块</th><th>状态</th><th>作用域</th><th>依赖方向</th></tr></thead><tbody><tr v-for="module in modules" :key="module.name"><td><strong>{{ module.name }}</strong></td><td><span class="badge">{{ module.state }}</span></td><td>{{ module.scope }}</td><td>enterprise → platform hooks</td></tr></tbody></table></div></section></section></template>

<style scoped>.enterprise-panel { margin-top: 14px; }</style>
