<script setup lang="ts">
import {
  Clock,
  Filter,
  ListChecks,
  Plus,
  RefreshCw,
  Search,
  UserCheck,
  UserPlus,
  Users,
} from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";

import { userFacingError } from "../../api";
import { useDebouncedRef } from "../../composables/useDebouncedRef";
import {
  createMember,
  createWatchlist,
  listMembers,
  listWatchlists,
} from "../../api/surveillance";
import { labelWatchlistCategory, labelWatchlistStatus } from "../../labels";
import type { Watchlist, WatchlistMember } from "../../types";

const watchlists = ref<Watchlist[]>([]);
const members = ref<WatchlistMember[]>([]);
const selectedId = ref("");
const loading = ref(false);
const mutating = ref(false);
const error = ref("");
const searchQuery = ref("");
const debouncedSearchQuery = useDebouncedRef(searchQuery);
const categoryFilter = ref<string>("all");
const showCreateModal = ref(false);

const watchlistForm = reactive({
  name: "",
  category: "custom" as "blacklist" | "whitelist" | "custom",
  description: "",
});

const memberForm = reactive({
  portrait_identity_id: "",
  display_label: "",
});

function date(value: number): string {
  if (!value) return "-";
  return new Date(value * 1000).toLocaleString("zh-CN", {
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const selectedWatchlist = computed(() =>
  watchlists.value.find((w) => w.watchlist_id === selectedId.value),
);

const filteredWatchlists = computed(() => {
  return watchlists.value.filter((item) => {
    if (
      categoryFilter.value !== "all" &&
      item.category !== categoryFilter.value
    ) {
      return false;
    }
    if (debouncedSearchQuery.value.trim()) {
      const q = debouncedSearchQuery.value.trim().toLowerCase();
      return (
        item.name.toLowerCase().includes(q) ||
        item.watchlist_id.toLowerCase().includes(q) ||
        (item.description && item.description.toLowerCase().includes(q))
      );
    }
    return true;
  });
});
const visibleWatchlists = computed(() =>
  filteredWatchlists.value.slice(0, 500),
);

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const page = await listWatchlists();
    watchlists.value = page.items;
    if (!selectedId.value && page.items[0]) {
      selectedId.value = page.items[0].watchlist_id;
    } else if (
      selectedId.value &&
      !page.items.some((w) => w.watchlist_id === selectedId.value)
    ) {
      selectedId.value = page.items[0]?.watchlist_id || "";
    }
    await loadMembers();
  } catch (caught) {
    error.value = userFacingError(caught);
  } finally {
    loading.value = false;
  }
}

async function loadMembers(): Promise<void> {
  if (!selectedId.value) {
    members.value = [];
    return;
  }
  try {
    const page = await listMembers(selectedId.value);
    members.value = page.items;
  } catch (caught) {
    error.value = userFacingError(caught);
  }
}

async function selectWatchlist(id: string): Promise<void> {
  selectedId.value = id;
  await loadMembers();
}

async function handleCreateWatchlist(): Promise<void> {
  if (!watchlistForm.name.trim()) return;
  mutating.value = true;
  error.value = "";
  try {
    const created = await createWatchlist({
      name: watchlistForm.name.trim(),
      category: watchlistForm.category,
      description: watchlistForm.description.trim(),
    });
    watchlistForm.name = "";
    watchlistForm.description = "";
    watchlistForm.category = "custom";
    showCreateModal.value = false;
    selectedId.value = created.watchlist_id;
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught);
  } finally {
    mutating.value = false;
  }
}

async function handleAddMember(): Promise<void> {
  if (!selectedId.value || !memberForm.portrait_identity_id.trim()) return;
  mutating.value = true;
  error.value = "";
  try {
    await createMember(selectedId.value, {
      portrait_identity_id: memberForm.portrait_identity_id.trim(),
      display_label: memberForm.display_label.trim(),
    });
    memberForm.portrait_identity_id = "";
    memberForm.display_label = "";
    await loadMembers();
  } catch (caught) {
    error.value = userFacingError(caught);
  } finally {
    mutating.value = false;
  }
}

onMounted(() => void refresh());
</script>

<template>
  <main class="page surveillance-page">
    <p v-if="error" class="error-banner">{{ error }}</p>

    <!-- 顶部操作与筛选工具栏 -->
    <div class="filter-controls">
      <div class="filter-left">
        <label class="filter-item">
          <Filter :size="12" class="filter-icon" />
          <span class="filter-label">类别筛选:</span>
          <select v-model="categoryFilter" class="filter-select">
            <option value="all">全部类别 (All)</option>
            <option value="blacklist">黑名单 (Blacklist)</option>
            <option value="whitelist">白名单 (Whitelist)</option>
            <option value="custom">自定义 (Custom)</option>
          </select>
        </label>

        <div class="search-box">
          <Search :size="13" class="search-icon" />
          <input
            v-model="searchQuery"
            placeholder="搜索名单名称或 ID..."
            class="search-input"
          />
        </div>

        <span class="badge count-badge"
          >共 {{ watchlists.length }} 个名单库</span
        >
      </div>

      <div class="filter-right">
        <button
          class="button secondary tiny-btn"
          :disabled="loading"
          @click="refresh"
        >
          <RefreshCw :size="12" :class="{ spinning: loading }" />
          <span>刷新</span>
        </button>
        <button class="button primary tiny-btn" @click="showCreateModal = true">
          <Plus :size="13" />
          <span>新建布控名单</span>
        </button>
      </div>
    </div>

    <!-- 主工作区：左右分栏 -->
    <div class="watchlist-split-view">
      <!-- 左栏：名单库列表 -->
      <section class="panel watchlist-master-panel">
        <div class="panel-header">
          <div class="panel-title">
            <ListChecks :size="14" class="title-icon" />
            <h3>名单库</h3>
            <span class="count-pill">{{ filteredWatchlists.length }}</span>
          </div>
        </div>

        <div class="watchlist-cards-list">
          <div
            v-for="item in visibleWatchlists"
            :key="item.watchlist_id"
            class="watchlist-card-item"
            :class="{ selected: selectedId === item.watchlist_id }"
            @click="selectWatchlist(item.watchlist_id)"
          >
            <div class="card-top-row">
              <strong class="watchlist-name">{{ item.name }}</strong>
              <div class="badges-row">
                <span class="badge category-badge" :class="item.category">
                  {{ labelWatchlistCategory(item.category) }}
                </span>
                <span class="badge status-badge" :class="item.status">
                  {{ labelWatchlistStatus(item.status) }}
                </span>
              </div>
            </div>

            <p class="watchlist-desc">
              {{ item.description || "暂无业务说明" }}
            </p>

            <div class="card-footer-row">
              <span class="watchlist-id-text mono">{{
                item.watchlist_id
              }}</span>
              <span class="time-text">
                <Clock :size="11" />
                {{ date(item.updated_at) }}
              </span>
            </div>
          </div>

          <p
            v-if="filteredWatchlists.length > visibleWatchlists.length"
            class="list-limit-note"
          >
            仅展示前 500 条结果，请使用搜索或类别筛选缩小范围。
          </p>
          <div v-if="!filteredWatchlists.length" class="empty-state">
            <ListChecks :size="32" class="empty-icon" />
            <p>暂无符合条件的布控名单库</p>
            <button
              class="button primary tiny-btn"
              @click="showCreateModal = true"
            >
              <Plus :size="12" />立即创建名单
            </button>
          </div>
        </div>
      </section>

      <!-- 右栏：选定名单的成员清单 -->
      <section class="panel watchlist-detail-panel">
        <div class="panel-header">
          <div class="panel-title">
            <Users :size="14" class="title-icon" />
            <h3>
              {{ selectedWatchlist ? selectedWatchlist.name : "名单成员" }}
            </h3>
            <span v-if="selectedWatchlist" class="count-pill">
              {{ members.length }} 人
            </span>
          </div>
          <div v-if="selectedWatchlist" class="header-meta">
            <span class="watchlist-id-badge mono"
              >ID: {{ selectedWatchlist.watchlist_id }}</span
            >
          </div>
        </div>

        <div v-if="selectedWatchlist" class="detail-body">
          <!-- 快速录入成员栏 -->
          <form class="inline-add-member-bar" @submit.prevent="handleAddMember">
            <div class="add-member-inputs">
              <input
                v-model="memberForm.portrait_identity_id"
                placeholder="人像身份 ID (如: idn_face_001)... *"
                class="field-input mono"
                required
              />
              <input
                v-model="memberForm.display_label"
                placeholder="成员姓名/备注 (可选，如: 重点嫌疑对象)"
                class="field-input"
              />
            </div>
            <button
              type="submit"
              class="button primary tiny-btn"
              :disabled="mutating || !memberForm.portrait_identity_id.trim()"
            >
              <UserPlus :size="13" />加入名单
            </button>
          </form>

          <!-- 成员数据表格 -->
          <div class="table-scroll">
            <table class="data-table">
              <thead>
                <tr>
                  <th style="width: 50px; text-align: center">序号</th>
                  <th style="width: 140px">成员姓名 / 备注</th>
                  <th style="width: 180px">人像身份 ID (Identity ID)</th>
                  <th style="width: 90px; text-align: center">成员状态</th>
                  <th style="width: 140px">加入时间</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(member, idx) in members" :key="member.member_id">
                  <td style="text-align: center" class="muted mono">
                    {{ idx + 1 }}
                  </td>
                  <td>
                    <strong>{{ member.display_label || "未命名成员" }}</strong>
                  </td>
                  <td class="mono">{{ member.portrait_identity_id }}</td>
                  <td style="text-align: center">
                    <span class="badge status-badge" :class="member.status">
                      {{ labelWatchlistStatus(member.status) }}
                    </span>
                  </td>
                  <td class="muted">{{ date(member.created_at) }}</td>
                </tr>
                <tr v-if="!members.length">
                  <td colspan="5" class="empty-cell">
                    <div class="empty-table-state">
                      <UserCheck :size="24" class="empty-table-icon" />
                      <p>
                        当前名单库尚未录入任何成员，请在上方输入人像身份 ID
                        进行添加
                      </p>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-else class="empty-state select-prompt">
          <ListChecks :size="36" class="empty-icon" />
          <p>请从左侧选择一个布控名单库以查看或管理其成员</p>
        </div>
      </section>
    </div>

    <!-- ==================== 新建模态弹窗 ==================== -->
    <div
      v-if="showCreateModal"
      class="modal-overlay"
      @click.self="showCreateModal = false"
    >
      <div class="modal-dialog modal-dialog-md" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div class="modal-title-box">
            <ListChecks :size="17" class="modal-title-icon" />
            <div>
              <h3>创建新布控名单</h3>
              <p>录入新的人像布控库，用于关联布控任务与实时预警研判</p>
            </div>
          </div>
        </div>
        <form @submit.prevent="handleCreateWatchlist">
          <div class="modal-body">
            <div class="form-grid-2col">
              <label class="form-field">
                <span class="field-label"
                  >名单名称 <em class="required">*</em></span
                >
                <input
                  v-model="watchlistForm.name"
                  placeholder="例如: 园区重点关注人员 / VIP访客库"
                  class="field-input"
                  required
                  autofocus
                />
              </label>
              <label class="form-field">
                <span class="field-label"
                  >名单类别 <em class="required">*</em></span
                >
                <select v-model="watchlistForm.category" class="field-input">
                  <option value="blacklist">黑名单 (高风险预警)</option>
                  <option value="whitelist">白名单 (免检放行)</option>
                  <option value="custom">自定义 (常规业务组)</option>
                </select>
              </label>
            </div>
            <label class="form-field" style="margin-top: 10px">
              <span class="field-label"
                >业务说明 <small class="muted">(可选)</small></span
              >
              <textarea
                v-model="watchlistForm.description"
                placeholder="输入该名单库的应用场景与业务背景说明..."
                class="field-input field-textarea"
                rows="3"
              ></textarea>
            </label>
          </div>
          <div class="modal-actions">
            <button
              type="button"
              class="button secondary tiny-btn"
              @click="showCreateModal = false"
            >
              取消
            </button>
            <button
              type="submit"
              class="button primary tiny-btn"
              :disabled="mutating || !watchlistForm.name.trim()"
            >
              <Plus :size="13" />确认创建名单
            </button>
          </div>
        </form>
      </div>
    </div>
  </main>
</template>

<style scoped>
.surveillance-page {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.error-banner {
  padding: 8px 12px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  border-radius: 4px;
  font-size: 12px;
  margin: 0;
}

/* 顶部过滤控制栏 */
.filter-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  padding: 4px 10px;
  flex-wrap: wrap;
}

.filter-left,
.filter-right {
  display: flex;
  align-items: center;
  gap: 8px;
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
}

.filter-select {
  height: 22px;
  min-height: 22px;
  line-height: 20px;
  padding: 0 4px 0 6px;
  font-size: 11px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 3px;
  background: #fafbfb;
  color: var(--graphite, #17211f);
  cursor: pointer;
}
.filter-select:focus {
  border-color: var(--color-accent, #087682);
  outline: none;
}

.count-badge {
  background: #edf2f0;
  color: #45534f;
  font-size: 10.5px;
  padding: 2px 6px;
  border-radius: 3px;
}

/* 主分栏工作区 */
.watchlist-split-view {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: 10px;
  align-items: start;
}

@media (max-width: 960px) {
  .watchlist-split-view {
    grid-template-columns: 1fr;
  }
}

.panel {
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  background: #fafbfb;
  min-height: 38px;
  box-sizing: border-box;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 6px;
}

.title-icon {
  color: var(--color-accent, #087682);
}

.panel-title h3 {
  margin: 0;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--graphite, #17211f);
}

.count-pill {
  font-size: 10.5px;
  color: #45534f;
  background: #edf2f0;
  padding: 1px 6px;
  border-radius: 999px;
}

.header-meta {
  display: flex;
  align-items: center;
  gap: 6px;
}

.watchlist-id-badge {
  font-size: 10.5px;
  color: var(--muted, #64716d);
  background: #f1f4f3;
  padding: 2px 6px;
  border-radius: 3px;
}

/* 左侧名单卡片列表 */
.watchlist-cards-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: min(62vh, 720px);
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 8px;
  max-height: calc(100vh - 210px);
  overflow-y: auto;
}

.watchlist-card-item {
  padding: 10px 12px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  background: #ffffff;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 5px;
  transition: all 0.15s ease;
}

.watchlist-card-item:hover {
  border-color: var(--line-strong, #b7c2bd);
  background: #fafbfb;
}

.watchlist-card-item.selected {
  background: var(--color-accent-soft, #eef7f7);
  border-color: var(--color-accent, #087682);
  box-shadow: 0 0 0 1px var(--color-accent, #087682);
}

.card-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.watchlist-name {
  font-size: 12.5px;
  color: var(--graphite, #17211f);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.badges-row {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.category-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
}
.category-badge.blacklist {
  background: #fee2e2;
  color: #991b1b;
}
.category-badge.whitelist {
  background: #dcfce7;
  color: #166534;
}
.category-badge.custom {
  background: #e0f2fe;
  color: #0369a1;
}

.status-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
}
.status-badge.active {
  background: #dcfce7;
  color: #166534;
}
.status-badge.disabled,
.status-badge.archived {
  background: #f1f5f9;
  color: #64748b;
}

.watchlist-desc {
  margin: 0;
  font-size: 11px;
  color: var(--muted, #64716d);
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-footer-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 10.5px;
  color: var(--muted, #64716d);
  margin-top: 2px;
}

.time-text {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

/* 右侧详情面板 */
.detail-body {
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.inline-add-member-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #fafbfb;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 6px;
  padding: 8px 10px;
  flex-wrap: wrap;
}

.add-member-inputs {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 260px;
}

.field-input {
  height: 28px;
  padding: 0 8px;
  font-size: 11.5px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #ffffff;
  color: var(--graphite, #17211f);
  box-sizing: border-box;
  width: 100%;
}
.field-input:focus {
  border-color: var(--color-accent, #087682);
  outline: none;
}

.field-textarea {
  height: auto;
  padding: 6px 8px;
  line-height: 1.4;
  resize: vertical;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 36px 16px;
  gap: 8px;
  color: var(--muted, #64716d);
  text-align: center;
}

.empty-icon {
  color: #b7c2bd;
}

.empty-state p {
  margin: 0;
  font-size: 12px;
}

.empty-table-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
  gap: 6px;
  color: var(--muted, #64716d);
}

.empty-table-icon {
  color: #b7c2bd;
}

.empty-table-state p {
  margin: 0;
  font-size: 11.5px;
}

/* 表格全局 */
.table-scroll {
  overflow-x: auto;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: #ffffff;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
}

.data-table th {
  height: 28px;
  padding: 2px 8px;
  font-size: 11.5px;
  font-weight: 600;
  background: #fafbfb;
  color: var(--muted, #64716d);
  border: 1px solid var(--line, #e2e8e6);
  white-space: nowrap;
  vertical-align: middle;
}

.data-table td {
  height: 28px;
  padding: 2px 8px;
  border: 1px solid var(--line, #e2e8e6);
  vertical-align: middle;
}

.list-limit-note {
  margin: 8px 0;
  padding: 8px 12px;
  text-align: center;
  font-size: 12px;
  color: var(--muted, #64748b);
}

.empty-cell {
  background: #fafbfb;
  text-align: center;
}

.mono {
  font-family: var(--font-mono, monospace);
  font-size: 11.5px;
}

.muted {
  color: var(--muted, #64716d);
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  100% {
    transform: rotate(360deg);
  }
}

/* 模态弹窗 */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(17, 26, 24, 0.45);
  display: grid;
  place-items: center;
  z-index: 1000;
  padding: 16px;
}

.modal-dialog {
  background: #ffffff;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 8px;
  box-shadow: 0 20px 50px rgba(15, 23, 21, 0.22);
  width: min(640px, 95vw);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--line, #e2e8e6);
  background: #fafbfb;
}

.modal-title-box {
  display: flex;
  align-items: center;
  gap: 10px;
}

.modal-title-icon {
  color: var(--color-accent, #087682);
}

.modal-title-box h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--graphite, #17211f);
}

.modal-title-box p {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--muted, #64716d);
}

.modal-body {
  padding: 16px 18px;
}

.form-grid-2col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-label {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--graphite, #17211f);
}

.required {
  color: #dc2626;
  font-style: normal;
}

.modal-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid var(--line, #e2e8e6);
  background: #fafbfb;
}
</style>
