import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// FastAPI runs on :8000. The SPA dev server proxies /api and /admin so
// that cookies (session, CSRF) flow through without CORS gymnastics.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/admin": "http://127.0.0.1:8000",
      "/static": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
