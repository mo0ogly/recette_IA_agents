import { describe, expect, it } from "vitest";
import type { AgentConfig, AiBackend } from "../types/platform";
import { formatBackend, isRealAi, isRealTarget } from "./aiBackend";

const backend: AiBackend = {
  id: "groq-llama",
  provider: "groq",
  model: "llama-3.3-70b-versatile",
};

function agent(partial: Partial<AgentConfig>): AgentConfig {
  return { id: "a", runtime: "lab", ...partial };
}

describe("formatBackend", () => {
  it("renders id (provider/model)", () => {
    expect(formatBackend(backend)).toBe("groq-llama (groq/llama-3.3-70b-versatile)");
  });
});

describe("isRealAi", () => {
  it("true only when ai_mode real AND a backend is bound", () => {
    expect(isRealAi(agent({ ai_mode: "real", ai_backend_id: "groq-llama" }))).toBe(true);
  });

  it("false when ai_mode real but no backend bound", () => {
    expect(isRealAi(agent({ ai_mode: "real" }))).toBe(false);
  });

  it("false when ai_mode mock even with a backend bound", () => {
    expect(isRealAi(agent({ ai_mode: "mock", ai_backend_id: "groq-llama" }))).toBe(false);
  });

  it("false when ai_mode is undefined", () => {
    expect(isRealAi(agent({ ai_backend_id: "groq-llama" }))).toBe(false);
  });
});

describe("isRealTarget", () => {
  it("true when runtime is real", () => {
    expect(isRealTarget(agent({ runtime: "real" }))).toBe(true);
  });

  it("false when runtime is lab", () => {
    expect(isRealTarget(agent({ runtime: "lab" }))).toBe(false);
  });
});
