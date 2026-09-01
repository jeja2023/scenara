import { defineComponent, nextTick, ref } from "vue";
import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useDebouncedRef } from "../src/composables/useDebouncedRef";

describe("useDebouncedRef", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("publishes only the latest value after the debounce interval", async () => {
    const source = ref("");
    const TestComponent = defineComponent({
      setup() {
        return { source, debounced: useDebouncedRef(source, 180) };
      },
      template: "<span>{{ debounced }}</span>",
    });
    const wrapper = mount(TestComponent);

    source.value = "s";
    source.value = "se";
    source.value = "search";
    await nextTick();
    expect(wrapper.text()).toBe("");

    vi.advanceTimersByTime(179);
    await nextTick();
    expect(wrapper.text()).toBe("");
    vi.advanceTimersByTime(1);
    await nextTick();
    expect(wrapper.text()).toBe("search");
  });
});
