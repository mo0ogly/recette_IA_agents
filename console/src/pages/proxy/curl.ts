/**
 * curl -- pure helper turning a captured wire flow into a copy-pasteable curl
 * command so an expert can replay the call. Pure (I4), no DOM.
 */
import type { WireFlow } from "../../types/platform";

/** Escape a string for safe inclusion inside shell single quotes. */
function shq(s: string): string {
  return `'${s.replace(/'/g, "'\\''")}'`;
}

/** A curl command reproducing a wire flow (method, url, content-type, body). */
export function wireFlowToCurl(f: WireFlow): string {
  const url = `${f.scheme}://${f.host}:${f.port}${f.path}`;
  const parts = [`curl -X ${f.method}`, shq(url)];
  if (f.content_type) {
    parts.push(`-H ${shq(`Content-Type: ${f.content_type}`)}`);
  }
  if (f.request_body) {
    parts.push(`--data ${shq(f.request_body)}`);
  }
  return parts.join(" ");
}
