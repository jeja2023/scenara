import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

export default defineConfig({
  base: "/console/",
  plugins: [vue()],
  server: {
    host: "127.0.0.1",
    proxy: { "/api": "http://127.0.0.1:8000", "/healthz": "http://127.0.0.1:8000" },
  },
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false },
  test: { environment: "jsdom", include: ["tests/**/*.test.ts"] },
});
