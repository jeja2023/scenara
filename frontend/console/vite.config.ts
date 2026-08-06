import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

const apiTarget = process.env.SCENARA_DEV_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  base: "/console/",
  plugins: [vue()],
  server: {
    host: "127.0.0.1",
    proxy: { "/api": apiTarget, "/healthz": apiTarget },
  },
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false },
  test: { environment: "jsdom", include: ["tests/**/*.test.ts"] },
});
