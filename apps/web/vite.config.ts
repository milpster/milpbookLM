/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "MILPBOOKLM_");
  return {
    plugins: [react()],
    server: {
      host: "0.0.0.0",
      port: 5173,
      strictPort: true,
      // Security: exact-host allowlist for the nginx TLS proxy (port 20001) — never widen to `true`.
      allowedHosts: ["wur5t.dyndns.org"],
      proxy: {
        "/api": {
          target: env["MILPBOOKLM_API_ORIGIN"] ?? "http://127.0.0.1:8000",
          changeOrigin: false,
        },
      },
    },
    build: {
      sourcemap: true,
      target: "es2022",
    },
    test: {
      environment: "happy-dom",
    },
  };
});
