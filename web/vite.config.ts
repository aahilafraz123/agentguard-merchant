import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The FastAPI app serves web/dist in production; in dev, Vite proxies the API to it.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  // The console chunk is mostly AG Grid and is lazy-loaded, so a larger limit is fine.
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 1000 },
});
