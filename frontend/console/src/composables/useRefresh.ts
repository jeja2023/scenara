import { onBeforeUnmount, onMounted } from "vue";

export function useRefresh(onRefresh: () => void | Promise<void>): void {
  const handler = () => {
    void onRefresh();
  };

  onMounted(() => {
    window.addEventListener("scenara:refresh", handler);
  });

  onBeforeUnmount(() => {
    window.removeEventListener("scenara:refresh", handler);
  });
}
