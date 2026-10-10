import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The SPA is served by Flask under /app (see crypto/spa.py). In development
// `npm run dev` serves it on :5173 and proxies everything else to Flask on :5000.
const backend = process.env.PULSETRADE_BACKEND ?? "http://127.0.0.1:5000";

export default defineConfig({
  base: "/app/",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../crypto/static/app",
    emptyOutDir: true,
    sourcemap: false,
    chunkSizeWarningLimit: 700,
  },
  server: {
    port: 5173,
    proxy: {
      "/socket.io": { target: backend, ws: true, changeOrigin: true },
      "^/(?!app/|app$|@|src/|node_modules/).*": { target: backend, changeOrigin: true },
    },
  },
});
