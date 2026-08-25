<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  payload: Record<string, unknown>;
}>();

type Scalar = string | number | boolean | null;

const entries = computed(() =>
  Object.entries(props.payload).filter(([key]) => key !== "domain"),
);
const scalarEntries = computed(() =>
  entries.value.filter(
    ([, value]) =>
      value === null || ["string", "number", "boolean"].includes(typeof value),
  ),
);
const tableEntries = computed(
  () =>
    entries.value.filter(
      ([, value]) =>
        Array.isArray(value) &&
        value.length > 0 &&
        value.every(
          (item) =>
            item !== null && typeof item === "object" && !Array.isArray(item),
        ),
    ) as Array<[string, Array<Record<string, unknown>>]>,
);
const otherEntries = computed(() =>
  entries.value.filter(
    ([key]) =>
      !scalarEntries.value.some(([itemKey]) => itemKey === key) &&
      !tableEntries.value.some(([itemKey]) => itemKey === key),
  ),
);

function formatScalar(value: Scalar): string {
  if (value === null) return "-";
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

function formatKey(value: string): string {
  return value.replace(/[_.-]+/g, " ");
}

function tableColumns(rows: Array<Record<string, unknown>>): string[] {
  return [...new Set(rows.flatMap((row) => Object.keys(row)))].slice(0, 8);
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "-";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
</script>

<template>
  <div class="generic-domain-result">
    <div class="generic-result-heading">
      <strong>领域结果</strong>
      <span>已使用通用结果渲染器</span>
    </div>
    <dl v-if="scalarEntries.length" class="generic-fields">
      <div v-for="[key, value] in scalarEntries" :key="key">
        <dt>{{ formatKey(key) }}</dt>
        <dd>{{ formatScalar(value as Scalar) }}</dd>
      </div>
    </dl>
    <div v-for="[key, rows] in tableEntries" :key="key" class="generic-table">
      <div class="generic-subheading">{{ formatKey(key) }}</div>
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width: 50px">序号</th>
              <th v-for="column in tableColumns(rows)" :key="column">
                {{ formatKey(column) }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in rows.slice(0, 100)" :key="index">
              <td class="muted">{{ index + 1 }}</td>
              <td v-for="column in tableColumns(rows)" :key="column">
                {{ formatCell(row[column]) }}
              </td>
            </tr>
            <tr v-if="!rows.length">
              <td :colspan="tableColumns(rows).length + 1" class="empty">暂无数据</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <details
      v-for="[key, value] in otherEntries"
      :key="key"
      class="generic-object"
    >
      <summary>{{ formatKey(key) }}</summary>
      <pre>{{ JSON.stringify(value, null, 2) }}</pre>
    </details>
    <p v-if="!entries.length" class="empty">该领域没有返回附加结果字段</p>
  </div>
</template>

<style scoped>
.generic-domain-result {
  display: grid;
  gap: 12px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}
.generic-result-heading,
.generic-subheading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}
.generic-result-heading span {
  color: var(--muted);
  font-size: 12px;
}
.generic-fields {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  margin: 0;
  background: var(--line);
  border: 1px solid var(--line);
}
.generic-fields div {
  min-width: 0;
  padding: 9px 10px;
  background: var(--surface);
}
.generic-fields dt {
  color: var(--muted);
  font-size: 11px;
}
.generic-fields dd {
  margin: 3px 0 0;
  overflow-wrap: anywhere;
}
.generic-table {
  display: grid;
  gap: 6px;
}
.generic-subheading {
  justify-content: flex-start;
  font-size: 12px;
  font-weight: 700;
}
.generic-object {
  border-top: 1px solid var(--line);
  padding-top: 8px;
}
.generic-object pre {
  margin-bottom: 0;
}
@media (max-width: 700px) {
  .generic-fields {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
