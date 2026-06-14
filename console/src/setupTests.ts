// Vitest setup: registers jest-dom matchers (toBeInTheDocument, toHaveClass, ...).
import "@testing-library/jest-dom/vitest";

// Unmount every rendered tree after each test so the jsdom document does not
// accumulate DOM across tests/files (files share one jsdom here). Without this,
// a modal/tab left by one test makes a global screen.getByRole(...) ambiguous in
// a later test -- a cross-test flake, not a real failure.
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
