/**
 * wireLlmDecode -- turn a raw wire flow into a semantic LLM exchange.
 *
 * The wire panel captures agent <-> target HTTP(S) bytes, but an LLM call shown
 * as raw HTTP (method/host/path/body) is hard to read. This pure decoder lifts a
 * flow whose target is a known LLM API (OpenAI chat/responses, Anthropic
 * messages, or a generic {messages:[...]} JSON shape) into the fields an
 * operator actually reasons about: model, the prompt messages, the tools offered
 * and the tools the model invoked, the answer, and token usage.
 *
 * Pure and deterministic (I4): a function of the flow bytes only -- no clock, no
 * random, no I/O. Display-only: never a judge/decision/replay input. Best-effort
 * and fail-safe: any flow that is not a recognisable LLM call, or whose body does
 * not parse (e.g. clamped/truncated by wire.py), decodes to null and the panel
 * falls back to the raw body pane rather than showing a wrong decode.
 */

import type { WireFlow } from "../../types/platform";

export type LlmProvider = "openai" | "anthropic" | "generic";

export interface LlmMessage {
  role: string;
  /** Flattened text of the message (string content, or the joined text parts of
   *  a multi-part / block content). Empty when the message carried no text. */
  text: string;
}

export interface LlmExchange {
  provider: LlmProvider;
  /** Requested model, when the request body carries it; null otherwise. */
  model: string | null;
  /** Prompt messages sent to the model (system prompt included when present). */
  messages: LlmMessage[];
  /** Names of the tools/functions OFFERED to the model in the request. */
  tools: string[];
  /** Names of the tools/functions the model INVOKED in the response. */
  toolCalls: string[];
  /** The model's textual answer, when the response parsed; null otherwise. */
  responseText: string | null;
  /** Token usage when the response carried it; null otherwise. */
  usage: { input: number | null; output: number | null } | null;
  /** finish_reason (OpenAI) / stop_reason (Anthropic) when present. */
  stop: string | null;
}

/** Known LLM endpoints, matched on the flow path (host is a secondary hint). */
const OPENAI_PATH = /\/v1\/(chat\/completions|responses|completions)\b/;
const ANTHROPIC_PATH = /\/v1\/(messages|complete)\b/;
const OPENAI_HOST = /(^|\.)openai\.com$|(^|\.)azure\.com$/;
const ANTHROPIC_HOST = /(^|\.)anthropic\.com$/;

/** Parse a JSON body, tolerating the wire truncation marker by refusing rather
 *  than guessing: a clamped body is not valid JSON, so decode to null. */
function parseJson(body: string): Record<string, unknown> | null {
  const trimmed = body.trim();
  if (trimmed === "") return null;
  try {
    const value: unknown = JSON.parse(trimmed);
    return typeof value === "object" && value !== null
      ? (value as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

/** Flatten a message `content` (string, or an array of text/blocks) to text. */
function contentToText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") return part;
        if (part !== null && typeof part === "object") {
          const p = part as Record<string, unknown>;
          if (typeof p.text === "string") return p.text;
          if (typeof p.content === "string") return p.content;
        }
        return "";
      })
      .filter((s) => s !== "")
      .join("\n");
  }
  return "";
}

/** Read a messages array (role/content) into flat LlmMessage[]. */
function readMessages(raw: unknown): LlmMessage[] {
  if (!Array.isArray(raw)) return [];
  const out: LlmMessage[] = [];
  for (const m of raw) {
    if (m === null || typeof m !== "object") continue;
    const obj = m as Record<string, unknown>;
    const role = typeof obj.role === "string" ? obj.role : "?";
    out.push({ role, text: contentToText(obj.content) });
  }
  return out;
}

/** Tool/function names OFFERED in a request (OpenAI `tools`/`functions` or
 *  Anthropic `tools`), tolerant of both shapes. */
function readOfferedTools(req: Record<string, unknown>): string[] {
  const names: string[] = [];
  const tools = req.tools;
  if (Array.isArray(tools)) {
    for (const t of tools) {
      if (t === null || typeof t !== "object") continue;
      const to = t as Record<string, unknown>;
      // OpenAI: { type:"function", function:{ name } }; Anthropic: { name }.
      const fn = to.function;
      if (fn !== null && typeof fn === "object" && typeof (fn as Record<string, unknown>).name === "string") {
        names.push((fn as Record<string, unknown>).name as string);
      } else if (typeof to.name === "string") {
        names.push(to.name);
      }
    }
  }
  const functions = req.functions; // legacy OpenAI function-calling
  if (Array.isArray(functions)) {
    for (const f of functions) {
      if (f !== null && typeof f === "object" && typeof (f as Record<string, unknown>).name === "string") {
        names.push((f as Record<string, unknown>).name as string);
      }
    }
  }
  return names;
}

/** Decode an OpenAI chat/completions style response. */
function decodeOpenAiResponse(res: Record<string, unknown> | null): {
  text: string | null;
  toolCalls: string[];
  usage: { input: number | null; output: number | null } | null;
  stop: string | null;
} {
  if (res === null) return { text: null, toolCalls: [], usage: null, stop: null };
  const toolCalls: string[] = [];
  let text: string | null = null;
  let stop: string | null = null;
  const choices = res.choices;
  if (Array.isArray(choices) && choices.length > 0 && choices[0] !== null && typeof choices[0] === "object") {
    const c0 = choices[0] as Record<string, unknown>;
    if (typeof c0.finish_reason === "string") stop = c0.finish_reason;
    const msg = c0.message;
    if (msg !== null && typeof msg === "object") {
      const mo = msg as Record<string, unknown>;
      if (typeof mo.content === "string") text = mo.content;
      const tc = mo.tool_calls;
      if (Array.isArray(tc)) {
        for (const call of tc) {
          if (call !== null && typeof call === "object") {
            const fn = (call as Record<string, unknown>).function;
            if (fn !== null && typeof fn === "object" && typeof (fn as Record<string, unknown>).name === "string") {
              toolCalls.push((fn as Record<string, unknown>).name as string);
            }
          }
        }
      }
    }
  }
  const usage = readUsage(res, "prompt_tokens", "completion_tokens");
  return { text, toolCalls, usage, stop };
}

/** Decode an Anthropic messages style response (content blocks). */
function decodeAnthropicResponse(res: Record<string, unknown> | null): {
  text: string | null;
  toolCalls: string[];
  usage: { input: number | null; output: number | null } | null;
  stop: string | null;
} {
  if (res === null) return { text: null, toolCalls: [], usage: null, stop: null };
  const toolCalls: string[] = [];
  const texts: string[] = [];
  const content = res.content;
  if (Array.isArray(content)) {
    for (const block of content) {
      if (block === null || typeof block !== "object") continue;
      const b = block as Record<string, unknown>;
      if (b.type === "text" && typeof b.text === "string") texts.push(b.text);
      if (b.type === "tool_use" && typeof b.name === "string") toolCalls.push(b.name);
    }
  }
  const stop = typeof res.stop_reason === "string" ? res.stop_reason : null;
  const usage = readUsage(res, "input_tokens", "output_tokens");
  return { text: texts.length > 0 ? texts.join("\n") : null, toolCalls, usage, stop };
}

/** Read a usage object under `usage`, mapping provider-specific token keys. */
function readUsage(
  res: Record<string, unknown>,
  inKey: string,
  outKey: string,
): { input: number | null; output: number | null } | null {
  const usage = res.usage;
  if (usage === null || typeof usage !== "object") return null;
  const u = usage as Record<string, unknown>;
  const input = typeof u[inKey] === "number" ? (u[inKey] as number) : null;
  const output = typeof u[outKey] === "number" ? (u[outKey] as number) : null;
  if (input === null && output === null) return null;
  return { input, output };
}

/** Pick the provider from the flow's path first, then host; null if unknown. */
function detectProvider(flow: WireFlow): LlmProvider | null {
  if (OPENAI_PATH.test(flow.path)) return "openai";
  if (ANTHROPIC_PATH.test(flow.path)) return "anthropic";
  if (OPENAI_HOST.test(flow.host)) return "openai";
  if (ANTHROPIC_HOST.test(flow.host)) return "anthropic";
  return null;
}

/**
 * Decode a wire flow into a semantic LLM exchange, or null when the flow is not
 * a recognisable LLM call or its request body does not parse. When the provider
 * is unknown but the request body is a generic `{messages:[...]}` chat shape, it
 * is decoded as "generic" so self-hosted / gateway endpoints still read well.
 */
export function decodeLlmFlow(flow: WireFlow): LlmExchange | null {
  const req = parseJson(flow.request_body);
  if (req === null) return null;

  let provider = detectProvider(flow);
  const hasMessages = Array.isArray(req.messages);
  if (provider === null) {
    if (!hasMessages) return null; // not an LLM call we can read
    provider = "generic";
  }

  const model = typeof req.model === "string" ? req.model : null;
  const messages: LlmMessage[] = [];
  // Anthropic carries the system prompt outside `messages`; surface it first.
  if (typeof req.system === "string" && req.system !== "") {
    messages.push({ role: "system", text: req.system });
  }
  messages.push(...readMessages(req.messages));
  const tools = readOfferedTools(req);

  const res = parseJson(flow.response_body);
  const decoded =
    provider === "anthropic" ? decodeAnthropicResponse(res) : decodeOpenAiResponse(res);

  return {
    provider,
    model,
    messages,
    tools,
    toolCalls: decoded.toolCalls,
    responseText: decoded.text,
    usage: decoded.usage,
    stop: decoded.stop,
  };
}
