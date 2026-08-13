import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

// Same proxy as every app in the gallery, so the browser sees one origin.
// `isCustomElement` is the Vue-specific half: without it the compiler treats
// <ag-ui-chat> as an unresolved Vue component and warns on every render.
export default defineConfig({
  plugins: [
    vue({
      template: {
        compilerOptions: {
          isCustomElement: (tag) => tag === "ag-ui-chat",
        },
      },
    }),
  ],
  server: {
    port: 5174,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/agent": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
