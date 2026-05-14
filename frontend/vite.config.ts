import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// `process` is provided by Node at config-load time. Declared here to avoid a
// hard dependency on @types/node just for one env-var lookup.
declare const process: { env: Record<string, string | undefined> };

// Set VITE_BASE_PATH (e.g. "/cv-radar/") for sub-path hosting. Defaults to "/".
const basePath = process.env.VITE_BASE_PATH ?? "/";

export default defineConfig({
  base: basePath,
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:7878",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
