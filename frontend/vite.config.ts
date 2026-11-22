import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En desarrollo, /graphql (HTTP y WebSocket) se reenvía al gateway local (run_services.py).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/graphql": { target: "http://localhost:8000", ws: true, changeOrigin: true },
    },
  },
});
