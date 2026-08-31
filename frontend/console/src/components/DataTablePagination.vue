<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "@lucide/vue";

interface Props {
  total: number;
  offset: number;
  pageSize?: number;
  pageSizeOptions?: number[];
  showPageSizeSelector?: boolean;
  showJumper?: boolean;
  loading?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  pageSize: 20,
  pageSizeOptions: () => [10, 20, 50, 100],
  showPageSizeSelector: true,
  showJumper: true,
  loading: false,
});

const emit = defineEmits<{
  (e: "change", newOffset: number): void;
  (e: "update:offset", newOffset: number): void;
  (e: "pageSizeChange", newPageSize: number): void;
  (e: "update:pageSize", newPageSize: number): void;
}>();

const jumperValue = ref<number | string>("");

const startNumber = computed(() => {
  if (props.total <= 0) return 0;
  return props.offset + 1;
});

const endNumber = computed(() => {
  return Math.min(props.total, props.offset + props.pageSize);
});

const currentPage = computed(() => {
  return Math.floor(props.offset / props.pageSize) + 1;
});

const totalPages = computed(() => {
  return Math.max(1, Math.ceil(props.total / props.pageSize));
});

watch(currentPage, (page) => {
  jumperValue.value = page;
}, { immediate: true });

function goToPage(nextOffset: number): void {
  const boundedOffset = Math.max(0, Math.min(nextOffset, (totalPages.value - 1) * props.pageSize));
  emit("update:offset", boundedOffset);
  emit("change", boundedOffset);
}

function handlePageClick(page: number): void {
  goToPage((page - 1) * props.pageSize);
}

function handlePageSizeSelect(event: Event): void {
  const target = event.target as HTMLSelectElement;
  const newSize = parseInt(target.value, 10);
  if (!Number.isNaN(newSize) && newSize > 0) {
    emit("update:pageSize", newSize);
    emit("pageSizeChange", newSize);
    // 重置到第一页
    emit("update:offset", 0);
    emit("change", 0);
  }
}

function handleJumperBlurOrEnter(): void {
  const targetPage = typeof jumperValue.value === "string" ? parseInt(jumperValue.value, 10) : jumperValue.value;
  if (!Number.isNaN(targetPage) && targetPage >= 1 && targetPage <= totalPages.value) {
    handlePageClick(targetPage);
  } else {
    jumperValue.value = currentPage.value;
  }
}

// 智能计算页码列表 (如: 1, 2, 3, '...', 10)
const pageNumbers = computed<(number | string)[]>(() => {
  const total = totalPages.value;
  const curr = currentPage.value;
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }
  if (curr <= 4) {
    return [1, 2, 3, 4, 5, "...", total];
  }
  if (curr >= total - 3) {
    return [1, "...", total - 4, total - 3, total - 2, total - 1, total];
  }
  return [1, "...", curr - 1, curr, curr + 1, "...", total];
});
</script>

<template>
  <div v-if="total > 0" class="pagination data-table-pagination">
    <div class="pagination-left">
      <span class="pagination-info">
        显示第 <strong>{{ startNumber }}-{{ endNumber }}</strong> 条，共 <strong>{{ total }}</strong> 条记录
      </span>
      <div v-if="showPageSizeSelector" class="pagination-size-wrapper">
        <select
          class="pagination-size-select"
          :value="pageSize"
          :disabled="loading"
          aria-label="选择每页显示条数"
          @change="handlePageSizeSelect"
        >
          <option v-for="size in pageSizeOptions" :key="size" :value="size">
            {{ size }} 条/页
          </option>
        </select>
      </div>
    </div>

    <div class="pagination-controls">
      <!-- 首页 -->
      <button
        v-if="totalPages > 5"
        class="pagination-btn pagination-nav-btn"
        :disabled="offset <= 0 || loading"
        title="首页"
        aria-label="首页"
        @click="goToPage(0)"
      >
        <ChevronsLeft :size="13" />
      </button>

      <!-- 上一页 -->
      <button
        class="pagination-btn pagination-nav-btn"
        :disabled="offset <= 0 || loading"
        title="上一页"
        aria-label="上一页"
        @click="goToPage(offset - pageSize)"
      >
        <ChevronLeft :size="14" />
        <span class="btn-text">上一页</span>
      </button>

      <!-- 数字页码按钮 -->
      <div class="pagination-pages">
        <template v-for="(p, idx) in pageNumbers" :key="idx">
          <span v-if="p === '...'" class="pagination-ellipsis">...</span>
          <button
            v-else
            class="pagination-page-btn"
            :class="{ active: p === currentPage }"
            :disabled="loading"
            :aria-current="p === currentPage ? 'page' : undefined"
            @click="handlePageClick(Number(p))"
          >
            {{ p }}
          </button>
        </template>
      </div>

      <!-- 下一页 -->
      <button
        class="pagination-btn pagination-nav-btn"
        :disabled="offset + pageSize >= total || loading"
        title="下一页"
        aria-label="下一页"
        @click="goToPage(offset + pageSize)"
      >
        <span class="btn-text">下一页</span>
        <ChevronRight :size="14" />
      </button>

      <!-- 末页 -->
      <button
        v-if="totalPages > 5"
        class="pagination-btn pagination-nav-btn"
        :disabled="offset + pageSize >= total || loading"
        title="末页"
        aria-label="末页"
        @click="goToPage((totalPages - 1) * pageSize)"
      >
        <ChevronsRight :size="13" />
      </button>

      <!-- 快捷跳页 -->
      <div v-if="showJumper && totalPages > 5" class="pagination-jumper">
        <span class="jumper-label">跳至</span>
        <input
          v-model="jumperValue"
          type="number"
          min="1"
          :max="totalPages"
          class="pagination-jumper-input"
          :disabled="loading"
          @keydown.enter="handleJumperBlurOrEnter"
          @blur="handleJumperBlurOrEnter"
        />
        <span class="jumper-label">页</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pagination-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.pagination-size-wrapper {
  display: inline-flex;
  align-items: center;
}

.pagination-size-select {
  height: 24px;
  padding: 0 6px;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: var(--color-surface, #fff);
  color: var(--color-text, #17211f);
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  outline: none;
  transition: border-color 120ms ease;
}

.pagination-size-select:hover:not(:disabled) {
  border-color: var(--primary, #0ea5e9);
}

.pagination-pages {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.pagination-page-btn {
  min-width: 26px;
  height: 26px;
  padding: 0 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: var(--color-text, #17211f);
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all 120ms ease;
}

.pagination-page-btn:hover:not(:disabled):not(.active) {
  background: rgba(0, 0, 0, 0.05);
  border-color: var(--line, #e2e8e6);
}

.pagination-page-btn.active {
  background: var(--primary, #0ea5e9);
  color: #fff;
  font-weight: 600;
  border-color: var(--primary, #0ea5e9);
  box-shadow: 0 1px 2px rgba(14, 165, 233, 0.25);
}

.pagination-ellipsis {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 26px;
  color: var(--muted, #64716d);
  font-size: 11px;
}

.pagination-controls {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  white-space: nowrap;
}

.pagination-jumper {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 6px;
  font-size: 11.5px;
  color: var(--muted, #64716d);
  white-space: nowrap;
  flex-shrink: 0;
}

.jumper-label {
  white-space: nowrap;
  flex-shrink: 0;
}

.pagination-jumper-input {
  width: 40px !important;
  min-width: 40px !important;
  max-width: 40px !important;
  height: 24px !important;
  min-height: 24px !important;
  max-height: 24px !important;
  padding: 0 4px !important;
  line-height: 22px;
  box-sizing: border-box !important;
  text-align: center;
  border: 1px solid var(--line, #e2e8e6);
  border-radius: 4px;
  background: var(--color-surface, #fff);
  color: var(--color-text, #17211f);
  font-size: 11.5px;
  outline: none;
  flex: 0 0 40px !important;
  -moz-appearance: textfield;
}

.pagination-jumper-input::-webkit-outer-spin-button,
.pagination-jumper-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.pagination-jumper-input:focus {
  border-color: var(--primary, #0ea5e9);
}

.pagination-nav-btn {
  gap: 2px;
}

@media (max-width: 640px) {
  .btn-text {
    display: none;
  }
}
</style>
