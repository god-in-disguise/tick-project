import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const apiProxyTarget = env.VITE_DEV_API_PROXY_TARGET || "http://127.0.0.1:8787";

  return {
    plugins: [react()],
    server: {
      host: "0.0.0.0",
      port: 5173,
      strictPort: true,
      allowedHosts: [".lhr.life", ".trycloudflare.com"],
      proxy: {
        "/api": {
          target: apiProxyTarget,
          changeOrigin: true
        },
        "/health": {
          target: apiProxyTarget,
          changeOrigin: true
        },
        "/ready": {
          target: apiProxyTarget,
          changeOrigin: true
        }
      }
    }
  };
});
