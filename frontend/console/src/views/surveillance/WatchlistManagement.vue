<script setup lang="ts">
import { Plus, RefreshCw, UserPlus } from "@lucide/vue";
import { onMounted, reactive, ref } from "vue";

import { userFacingError } from "../../api";
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
const error = ref("");
const watchlistForm = reactive({
  name: "",
  category: "custom",
  description: "",
});
const memberForm = reactive({ portrait_identity_id: "", display_label: "" });

function date(value: number): string {
  return new Date(value * 1000).toLocaleString("zh-CN", { hour12: false });
}

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const page = await listWatchlists();
    watchlists.value = page.items;
    if (!selectedId.value && page.items[0])
      selectedId.value = page.items[0].watchlist_id;
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
  const page = await listMembers(selectedId.value);
  members.value = page.items;
}

async function create(): Promise<void> {
  try {
    const created = await createWatchlist(watchlistForm);
    watchlistForm.name = "";
    watchlistForm.description = "";
    selectedId.value = created.watchlist_id;
    await refresh();
  } catch (caught) {
    error.value = userFacingError(caught);
  }
}

async function addMember(): Promise<void> {
  if (!selectedId.value) return;
  try {
    await createMember(selectedId.value, memberForm);
    memberForm.portrait_identity_id = "";
    memberForm.display_label = "";
    await loadMembers();
  } catch (caught) {
    error.value = userFacingError(caught);
  }
}

onMounted(() => void refresh());
</script>

<template>
  <main class="page surveillance-page">
    <p v-if="error" class="error-message">{{ error }}</p>

    <section class="panel form-grid">
      <label
        >名单名称<input
          v-model.trim="watchlistForm.name"
          placeholder="例如：重点关注人员"
      /></label>
      <label
        >类别<select v-model="watchlistForm.category">
          <option value="blacklist">黑名单</option>
          <option value="whitelist">白名单</option>
          <option value="custom">自定义</option>
        </select></label
      >
      <label class="wide"
        >说明<input
          v-model.trim="watchlistForm.description"
          placeholder="业务说明（可选）"
      /></label>
      <button class="button" :disabled="!watchlistForm.name" @click="create">
        <Plus :size="16" />创建名单
      </button>
    </section>

    <section class="split-grid">
      <article class="panel">
        <div class="panel-header-row">
          <h2>名单库</h2>
          <button class="button secondary refresh-btn" :disabled="loading" @click="refresh">
            <RefreshCw :size="14" />刷新
          </button>
        </div>
        <button
          v-for="item in watchlists"
          :key="item.watchlist_id"
          class="list-row"
          :class="{ selected: selectedId === item.watchlist_id }"
          @click="
            selectedId = item.watchlist_id;
            loadMembers();
          "
        >
          <span
            ><strong>{{ item.name }}</strong
            ><small>{{ labelWatchlistCategory(item.category) }} · {{ labelWatchlistStatus(item.status) }}</small></span
          >
          <small>{{ date(item.updated_at) }}</small>
        </button>
        <p v-if="!watchlists.length" class="muted">暂无名单库。</p>
      </article>
      <article class="panel">
        <h2>名单成员</h2>
        <div v-if="selectedId" class="inline-form">
          <input
            v-model.trim="memberForm.portrait_identity_id"
            placeholder="人像身份 ID（idn_...）"
          />
          <input
            v-model.trim="memberForm.display_label"
            placeholder="名单显示名（可选）"
          />
          <button
            class="button"
            :disabled="!memberForm.portrait_identity_id"
            @click="addMember"
          >
            <UserPlus :size="16" />加入
          </button>
        </div>
        <div
          v-for="member in members"
          :key="member.member_id"
          class="member-row"
        >
          <span
            ><strong>{{
              member.display_label || member.portrait_identity_id
            }}</strong
            ><small>{{ member.portrait_identity_id }}</small></span
          >
          <span class="badge">{{ labelWatchlistStatus(member.status) }}</span>
        </div>
        <p v-if="selectedId && !members.length" class="muted">尚未添加成员。</p>
      </article>
    </section>
  </main>
</template>

<style scoped>
.surveillance-page {
  display: grid;
  gap: 1rem;
}
.split-grid {
  display: grid;
  gap: 1rem;
}
.panel-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.8rem;
}
h2 {
  font-size: 1rem;
  margin: 0;
}
.panel {
  border: 1px solid var(--border-color, #d9e0ea);
  border-radius: 0.8rem;
  background: var(--panel-color, #fff);
  padding: 1rem;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 180px;
  gap: 0.8rem;
  align-items: end;
}
.wide {
  grid-column: span 2;
}
label {
  display: grid;
  gap: 0.35rem;
  font-size: 0.86rem;
  color: var(--muted-text, #64748b);
}
input,
select {
  min-width: 0;
  padding: 0.6rem 0.7rem;
  border: 1px solid var(--border-color, #cbd5e1);
  border-radius: 0.45rem;
  background: transparent;
  color: inherit;
}
.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  min-height: 2.35rem;
  border: 0;
  border-radius: 0.5rem;
  padding: 0.45rem 0.8rem;
  cursor: pointer;
  background: var(--accent, #2563eb);
  color: #fff;
}
.button.secondary {
  background: var(--soft-color, #e2e8f0);
  color: inherit;
}
.button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.split-grid {
  grid-template-columns: minmax(220px, 0.85fr) minmax(360px, 1.4fr);
}
.list-row,
.member-row {
  width: 100%;
  display: flex;
  justify-content: space-between;
  gap: 0.7rem;
  padding: 0.75rem 0;
  text-align: left;
  border: 0;
  border-bottom: 1px solid var(--border-color, #e2e8f0);
  background: transparent;
  color: inherit;
}
.list-row {
  cursor: pointer;
}
.list-row.selected {
  color: var(--accent, #2563eb);
}
strong,
small {
  display: block;
}
small,
.muted {
  color: var(--muted-text, #64748b);
  font-size: 0.8rem;
}
.inline-form {
  display: grid;
  grid-template-columns: 1.3fr 1fr auto;
  gap: 0.6rem;
  margin-bottom: 0.8rem;
}
.badge {
  align-self: center;
  padding: 0.2rem 0.45rem;
  border-radius: 999px;
  background: var(--soft-color, #e2e8f0);
  font-size: 0.78rem;
}
.error-message {
  color: #dc2626;
}
@media (max-width: 800px) {
  .page-header,
  .split-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }
  .wide {
    grid-column: auto;
  }
  .inline-form {
    grid-template-columns: 1fr;
  }
}
</style>
