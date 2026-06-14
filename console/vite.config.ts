import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Vite + Vitest configuration for the inspect_ia_agents console.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
  },
});
