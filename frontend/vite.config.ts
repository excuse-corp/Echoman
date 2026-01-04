import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0', // 监听所有网络接口，允许远程访问
      port: Number(env.VITE_DEV_SERVER_PORT ?? 5173),
      // 远程访问前端时，浏览器无法访问服务器的 localhost:8778；
      // 使用代理让前端通过同源 `/api/v1` 访问后端。
      proxy: {
        "/api/v1": {
          target: env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8778",
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: "dist",
    },
  };
});
