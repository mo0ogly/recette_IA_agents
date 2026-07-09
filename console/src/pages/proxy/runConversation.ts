/**
 * runConversation -- join a run's LLM decisions with the agent<->server
 * exchanges they produced, into ONE ordered conversation.
 *
 * This is the "sophisticated Wireshark for agents" core: for any run (any agent,
 * any campaign) it interleaves what the LLM DECIDED at each step (the thought:
 * decision kind, tool, intent, tokens -- from GET /capture/llm-traces) with the
 * request the agent then sent to the server AND the server's response (from GET
 * /proxy/traces). Each tool decision is matched to the first unconsumed server
 * trace with the same (action_type == tool_name, resource); a `final` decision
 * or a denied/unexecuted tool has no exchange; any server trace with no matching
 * decision is appended as an exchange-only turn (never dropped).
 *
 * Pure and deterministic: a function of the two trace lists only (no clock, no
 * I/O). Display-only -- never a judge/decision/replay input.
 *
 * NOTE on the LLM "thought": LlmTrace carries the compact decision (tool/intent/
 * tokens), not the raw prompt text -- the full message text lives on the wire
 * overlay (decodeLlmFlow). This view works WITHOUT the wire overlay; the wire
 * timeline complements it with the full message bytes when the overlay is on.
 */

import type { LlmTrace } from "../../api/client";
import type { ProxyTrace } from "../../types/platform";

export interface ConversationExchange {
  actionType: string;
  resource: string;
  /** What the agent sent to the server. */
  request: Record<string, unknown>;
  /** The server's response body (the other half of the exchange). */
  response: Record<string, unknown>;
  status: number;
  ok: boolean;
  error: string | null;
}

export interface ConversationTurn {
  /** 1-based display order. */
  step: number;
  /** Source seq (stable React key). */
  seq: number;
  model: string | null;
  /** "tool_call" | "final" for a decision turn; null for an exchange-only turn. */
  decisionKind: string | null;
  tool: string | null;
  intent: string | null;
  tokens: { prompt: number; completion: number; total: number } | null;
  /** The server exchange this decision produced, or null (final / denied). */
  exchange: ConversationExchange | null;
}

function exchangeFrom(p: ProxyTrace): ConversationExchange {
  return {
    actionType: p.action_type,
    resource: p.resource,
    request: p.request_payload,
    response: p.response,
    status: p.status_code,
    ok: p.ok,
    error: p.error,
  };
}

export function buildRunConversation(
  llmTraces: LlmTrace[],
  proxyTraces: ProxyTrace[],
): ConversationTurn[] {
  const proxies = [...proxyTraces].sort((a, b) => a.seq - b.seq);
  const used = new Set<number>();
  const turns: ConversationTurn[] = [];

  for (const t of [...llmTraces].sort((a, b) => a.seq - b.seq)) {
    let exchange: ConversationExchange | null = null;
    if (t.kind === "tool_call") {
      const idx = proxies.findIndex(
        (p, i) => !used.has(i) && p.action_type === t.tool_name && p.resource === t.resource,
      );
      if (idx >= 0) {
        used.add(idx);
        exchange = exchangeFrom(proxies[idx]);
      }
    }
    turns.push({
      step: 0,
      seq: t.seq,
      model: t.model || null,
      decisionKind: t.kind,
      tool: t.tool_name,
      intent: t.intent || null,
      tokens: {
        prompt: t.prompt_tokens,
        completion: t.completion_tokens,
        total: t.total_tokens,
      },
      exchange,
    });
  }

  // Server traces with no matching decision -> exchange-only turns (never dropped).
  proxies.forEach((p, i) => {
    if (used.has(i)) return;
    turns.push({
      step: 0,
      seq: p.seq,
      model: null,
      decisionKind: null,
      tool: null,
      intent: null,
      tokens: null,
      exchange: exchangeFrom(p),
    });
  });

  return turns.map((turn, i) => ({ ...turn, step: i + 1 }));
}
