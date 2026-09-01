import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Backend runs on :8000 by default; proxy /api during development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000",
        ws: true,
        changeOrigin: true,
      },
    },
  },
});
