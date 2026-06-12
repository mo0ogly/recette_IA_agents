import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Vite + Vitest configuration for the AgentRail console.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
  },
});
