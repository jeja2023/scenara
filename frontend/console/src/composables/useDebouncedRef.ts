import { onBeforeUnmount, ref, watch, type Ref } from "vue";

/** Keep high-frequency text filters from recomputing large lists per keystroke. */
export function useDebouncedRef<T>(source: Ref<T>, delayMs = 180): Ref<T> {
  const debounced = ref(source.value) as Ref<T>;
  let timer: ReturnType<typeof setTimeout> | undefined;

  watch(source, (value) => {
    if (timer !== undefined) clearTimeout(timer);
    timer = setTimeout(() => {
      debounced.value = value;
      timer = undefined;
    }, delayMs);
  });

  onBeforeUnmount(() => {
    if (timer !== undefined) clearTimeout(timer);
  });

  return debounced;
}
