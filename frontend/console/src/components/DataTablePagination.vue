<script setup lang="ts">
import { computed } from "vue";
import { ChevronLeft, ChevronRight } from "@lucide/vue";

interface Props {
  total: number;
  offset: number;
  pageSize?: number;
  loading?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  pageSize: 20,
  loading: false,
});

const emit = defineEmits<{
  (e: "change", newOffset: number): void;
  (e: "update:offset", newOffset: number): void;
}>();

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

function goToPage(nextOffset: number): void {
  const boundedOffset = Math.max(0, nextOffset);
  emit("update:offset", boundedOffset);
  emit("change", boundedOffset);
}
</script>

<template>
  <div v-if="total > 0" class="pagination data-table-pagination">
    <span class="pagination-info">
      显示第 <strong>{{ startNumber }}-{{ endNumber }}</strong> 条，共 <strong>{{ total }}</strong> 条记录
    </span>
    <div class="pagination-controls">
      <button
        class="pagination-btn"
        :disabled="offset <= 0 || loading"
        aria-label="上一页"
        @click="goToPage(offset - pageSize)"
      >
        <ChevronLeft :size="14" />上一页
      </button>
      <span class="pagination-page-indicator">{{ currentPage }} / {{ totalPages }}</span>
      <button
        class="pagination-btn"
        :disabled="offset + pageSize >= total || loading"
        aria-label="下一页"
        @click="goToPage(offset + pageSize)"
      >
        下一页<ChevronRight :size="14" />
      </button>
    </div>
  </div>
</template>
