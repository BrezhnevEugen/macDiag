import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: proxy the API + websockets to the FastAPI backend (uvicorn :8000).
// Prod: `vite build` -> dist/, served by FastAPI.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
});
