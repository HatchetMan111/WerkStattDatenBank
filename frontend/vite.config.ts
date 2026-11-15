import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Entwicklung: `npm run dev` leitet /api an ein lokal laufendes Backend (Port 8080) weiter.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8080" } },
  build: { outDir: "dist", emptyOutDir: true },
  test: { environment: "jsdom" },
});
