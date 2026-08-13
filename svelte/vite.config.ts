import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";

// Same proxy as every app in the gallery, so the browser sees one origin.
export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5175,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/agent": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
