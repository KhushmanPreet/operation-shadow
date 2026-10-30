import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: "127.0.0.1",
    proxy: {
      "/health": "http://127.0.0.1:8000",
      "/mission": "http://127.0.0.1:8000",
      "/vehicle": "http://127.0.0.1:8000",
      "/events": "http://127.0.0.1:8000",
      "/map": "http://127.0.0.1:8000",
      "/emergency-stop": "http://127.0.0.1:8000",
      "/ws/dashboard": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/testSetup.ts",
  },
});
