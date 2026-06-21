/**
 * proxyExport -- pure, DOM-free serialisers + a download helper for the Proxy
 * console. JSONL for any source's shown items; HAR 1.2 for wire flows (importable
 * in browser devtools / Charles / Fiddler). Pure (I4): no clock, no random; the
 * download helper is the only DOM touch and is isolated for testability.
 */

import type { WireFlow } from "../../types/platform";

/** UTF-8 byte length of a string. */
export function byteLen(s: string): number {
  return new TextEncoder().encode(s).length;
}

/** One JSON object per line (oldest first). Empty list -> empty string. */
export function toJsonl(items: readonly unknown[]): string {
  return items.map((it) => JSON.stringify(it)).join("\n");
}

/** Wire flows as a HAR 1.2 document. Headers are minimal (the WireFlow carries
 *  content_type + bodies, not the full header set); the bodies are the point. */
export function flowsToHar(flows: readonly WireFlow[]): string {
  const har = {
    log: {
      version: "1.2",
      creator: { name: "inspect_ia_agents-proxy", version: "1.0" },
      entries: flows.map((f) => ({
        // wire flows carry no wall clock (I4); seq is the order, time is unknown
        startedDateTime: "1970-01-01T00:00:00.000Z",
        time: 0,
        request: {
          method: f.method,
          url: `${f.scheme}://${f.host}:${f.port}${f.path}`,
          httpVersion: "HTTP/1.1",
          headers: f.content_type ? [{ name: "Content-Type", value: f.content_type }] : [],
          queryString: [],
          headersSize: -1,
          bodySize: byteLen(f.request_body),
          postData: f.request_body
            ? { mimeType: f.content_type || "application/octet-stream", text: f.request_body }
            : undefined,
        },
        response: {
          status: f.status_code,
          statusText: "",
          httpVersion: "HTTP/1.1",
          headers: f.content_type ? [{ name: "Content-Type", value: f.content_type }] : [],
          content: {
            size: byteLen(f.response_body),
            mimeType: f.content_type || "application/octet-stream",
            text: f.response_body,
          },
          redirectURL: "",
          headersSize: -1,
          bodySize: byteLen(f.response_body),
        },
        cache: {},
        timings: { send: 0, wait: 0, receive: 0 },
      })),
    },
  };
  return JSON.stringify(har, null, 2);
}

/** Trigger a browser download of `content` as `filename` (isolated DOM touch). */
export function downloadFile(content: string, filename: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
