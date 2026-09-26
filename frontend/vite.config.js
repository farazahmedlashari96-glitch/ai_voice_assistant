import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, /api/* is proxied to Django, so no CORS setup is needed.
export default defineConfig({
  plugins: [react()],
  test: { environment: "jsdom" },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
