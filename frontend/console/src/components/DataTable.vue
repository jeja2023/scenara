<script setup lang="ts">
import { computed } from "vue";
import DataTablePagination from "./DataTablePagination.vue";

export interface TableColumn<T = any> {
  key: string;
  label?: string;
  width?: string;
  minWidth?: string;
  align?: "left" | "center" | "right";
  headerAlign?: "left" | "center" | "right";
  class?: string;
  headerClass?: string;
  style?: Record<string, string | number> | string;
  formatter?: (value: any, row: T, index: number) => any;
}

interface Props {
  columns: TableColumn[];
  items?: any[];
  rowKey?: string | ((row: any, index: number) => string | number);
  showIndex?: boolean;
  indexLabel?: string;
  indexWidth?: string;
  indexOffset?: number;
  loading?: boolean;
  loadingText?: string;
  emptyText?: string;
  tableClass?: string;
  wrapperClass?: string;
  total?: number;
  offset?: number;
  pageSize?: number;
  rowClass?: string | ((row: any, index: number) => any);
}

const props = withDefaults(defineProps<Props>(), {
  items: () => [],
  showIndex: true,
  indexLabel: "序号",
  indexWidth: "50px",
  indexOffset: 0,
  loading: false,
  loadingText: "正在加载数据...",
  emptyText: "暂无数据",
  tableClass: "",
  wrapperClass: "",
  pageSize: 20,
});

const emit = defineEmits<{
  (e: "pageChange", newOffset: number): void;
  (e: "update:offset", newOffset: number): void;
  (e: "rowClick", row: any, index: number, event: MouseEvent): void;
}>();

const totalColspan = computed(() => {
  return (props.showIndex ? 1 : 0) + (props.columns?.length || 0);
});

function getRowKey(row: any, index: number): string | number {
  if (typeof props.rowKey === "function") {
    return props.rowKey(row, index);
  }
  if (typeof props.rowKey === "string" && row && row[props.rowKey] !== undefined) {
    return row[props.rowKey];
  }
  if (row) {
    if (row.id !== undefined) return row.id;
    if (row.run_id !== undefined) return row.run_id;
    if (row.result_id !== undefined) return row.result_id;
    if (row.asset_id !== undefined) return row.asset_id;
    if (row.source_id !== undefined) return row.source_id;
    if (row.user_id !== undefined) return row.user_id;
    if (row.model_id !== undefined) return row.model_id + (row.version || "");
    if (row.key_id !== undefined) return row.key_id;
    if (row.record_id !== undefined) return row.record_id;
    if (row.event_id !== undefined) return row.event_id;
    if (row.endpoint_id !== undefined) return row.endpoint_id;
    if (row.delivery_id !== undefined) return row.delivery_id;
    if (row.pipeline_id !== undefined) return row.pipeline_id + (row.version || "");
  }
  return index;
}

function resolveRowClass(row: any, index: number): any {
  if (typeof props.rowClass === "function") {
    return props.rowClass(row, index);
  }
  return props.rowClass;
}

function getCellValue(row: any, column: TableColumn, index: number): any {
  if (!row) return "";
  const raw = row[column.key];
  if (typeof column.formatter === "function") {
    return column.formatter(raw, row, index);
  }
  return raw;
}

function handlePageChange(nextOffset: number): void {
  emit("update:offset", nextOffset);
  emit("pageChange", nextOffset);
}

function handleRowClick(row: any, index: number, event: MouseEvent): void {
  emit("rowClick", row, index, event);
}
</script>

<template>
  <div class="data-table-container" :class="wrapperClass">
    <div class="table-scroll">
      <table class="data-table" :class="tableClass">
        <thead>
          <tr>
            <th
              v-if="showIndex"
              class="index-header"
              :style="{ width: indexWidth, textAlign: 'center' }"
            >
              <slot name="header-index">{{ indexLabel }}</slot>
            </th>
            <th
              v-for="col in columns"
              :key="col.key"
              :class="[col.headerClass, col.class]"
              :style="[
                col.width ? { width: col.width } : {},
                col.minWidth ? { minWidth: col.minWidth } : {},
                col.headerAlign ? { textAlign: col.headerAlign } : col.align ? { textAlign: col.align } : {},
                typeof col.style === 'object' ? col.style : {},
              ]"
            >
              <slot :name="`header-${col.key}`" :column="col">
                {{ col.label ?? col.key }}
              </slot>
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-if="loading && (!items || !items.length)">
            <tr>
              <td :colspan="totalColspan" class="empty table-loading-cell">
                <slot name="loading">{{ loadingText }}</slot>
              </td>
            </tr>
          </template>
          <template v-else-if="items && items.length > 0">
            <template
              v-for="(row, index) in items"
              :key="getRowKey(row, index)"
            >
              <tr
                :class="resolveRowClass(row, index)"
                @click="handleRowClick(row, index, $event)"
              >
                <td
                  v-if="showIndex"
                  class="muted index-cell"
                  :style="{ width: indexWidth, textAlign: 'center' }"
                >
                  <slot
                    name="index"
                    :row="row"
                    :index="index"
                    :actual-index="indexOffset + index + 1"
                  >
                    {{ indexOffset + index + 1 }}
                  </slot>
                </td>
                <td
                  v-for="col in columns"
                  :key="col.key"
                  :class="col.class"
                  :style="[
                    col.align ? { textAlign: col.align } : {},
                    typeof col.style === 'object' ? col.style : {},
                  ]"
                >
                  <slot
                    :name="col.key"
                    :row="row"
                    :value="getCellValue(row, col, index)"
                    :index="index"
                    :actual-index="indexOffset + index + 1"
                  >
                    {{ getCellValue(row, col, index) }}
                  </slot>
                </td>
              </tr>
              <slot
                name="subrow"
                :row="row"
                :index="index"
                :total-colspan="totalColspan"
              />
            </template>
          </template>
          <template v-else>
            <tr>
              <td :colspan="totalColspan" class="empty table-empty-cell">
                <slot name="empty">{{ emptyText }}</slot>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <slot name="pagination">
      <DataTablePagination
        v-if="total !== undefined && total > 0"
        :total="total"
        :offset="offset ?? 0"
        :page-size="pageSize"
        :loading="loading"
        @change="handlePageChange"
        @update:offset="emit('update:offset', $event)"
      />
    </slot>
  </div>
</template>
