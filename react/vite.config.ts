import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies both backend prefixes, so from the browser's point of
// view the app and the API share an origin. That is deliberate: it keeps CORS
// and cross-site cookie policy out of a demo whose subject is something else.
// Every app in the gallery does the same thing its own way.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/agent": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
