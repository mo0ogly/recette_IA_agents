/**
 * WireLayersView — the layered network decode of one wire flow.
 *
 * Renders the "Wireshark for AI agents" layer stack the mitmproxy addon captures
 * on top of the HTTP bodies: L3/L4 (real IPs/ports), TLS (version, cipher, SNI,
 * ALPN, upstream cert, client JA3), L7 HTTP (version, reason, full headers), and
 * a per-phase timing waterfall. Extracted from WirePanel to keep that file under
 * the size ceiling; it is a pure read-only projection of `flow.layers`.
 *
 * Absent layers/fields are simply not rendered (or shown as "-") — never faked.
 */

import type { WireFlow } from "../../types/platform";
import { readLayers, endpoint, instanceId, sessionId } from "./wireLayers";

function Row({ k, v }: { k: string; v: string | number | null | undefined }): JSX.Element | null {
  if (v === null || v === undefined || v === "") return null;
  return (
    <div className="wire-layer-row">
      <span className="wire-layer-k">{k}</span>
      <code className="wire-layer-v">{String(v)}</code>
    </div>
  );
}

function Headers({ headers }: { headers: Record<string, string> }): JSX.Element {
  const entries = Object.entries(headers ?? {});
  if (entries.length === 0) return <span className="wire-layer-empty">(aucun)</span>;
  return (
    <div className="wire-layer-headers">
      {entries.map(([k, v]) => (
        <div className="wire-layer-row" key={k}>
          <span className="wire-layer-k">{k}</span>
          <code className="wire-layer-v">{v}</code>
        </div>
      ))}
    </div>
  );
}

/** Multi-session tracking identity (rendered even without a layer decode). */
function Identity({ flow }: { flow: WireFlow }): JSX.Element | null {
  const iid = instanceId(flow);
  const sid = sessionId(flow);
  if (!iid && !sid) return null;
  return (
    <details className="wire-layer wire-layer-identity" open data-testid="wire-layers-identity">
      <summary>Instance — tracking multi-session</summary>
      <div className="wire-layer-body">
        <Row k="instance" v={iid} />
        <Row k="session" v={sid} />
      </div>
    </details>
  );
}

export default function WireLayersView({ flow }: { flow: WireFlow }): JSX.Element | null {
  const layers = readLayers(flow);
  const identity = <Identity flow={flow} />;
  if (layers === null) {
    return (
      <div className="wire-layers" data-testid="wire-layers">
        {identity}
        <p className="wire-layer-none" data-testid="wire-layers-none">
          Pas de décodage réseau pour ce flux (overlay hérité, avant la capture en couches).
        </p>
      </div>
    );
  }
  const { l3l4, tls, http, timing } = layers;

  return (
    <div className="wire-layers" data-testid="wire-layers">
      {identity}
      {l3l4 && (
        <details className="wire-layer wire-layer-l34" open>
          <summary>L3/L4 — transport</summary>
          <div className="wire-layer-body">
            <Row k="source" v={endpoint(l3l4.src_ip, l3l4.src_port)} />
            <Row k="destination" v={endpoint(l3l4.dst_ip, l3l4.dst_port)} />
            <Row k="transport" v={l3l4.transport} />
            <Row k="IP" v={l3l4.ip_version ? `IPv${l3l4.ip_version}` : null} />
          </div>
        </details>
      )}
      {tls && (
        <details className="wire-layer wire-layer-tls" open>
          <summary>TLS — chiffrement + JA3</summary>
          <div className="wire-layer-body">
            <Row k="version" v={tls.version} />
            <Row k="cipher" v={tls.cipher} />
            <Row k="SNI" v={tls.sni} />
            <Row k="ALPN" v={tls.alpn} />
            <Row k="JA3" v={tls.ja3} />
            <Row k="JA3 (brut)" v={tls.ja3_string} />
            <Row k="cert (CN)" v={tls.cert_subject} />
            <Row k="cert (émetteur)" v={tls.cert_issuer} />
            <Row k="cert (expire)" v={tls.cert_not_after} />
            <Row k="upstream TLS" v={tls.upstream_version} />
            <Row k="upstream cipher" v={tls.upstream_cipher} />
          </div>
        </details>
      )}
      {http && (
        <details className="wire-layer wire-layer-http">
          <summary>L7 HTTP — en-têtes</summary>
          <div className="wire-layer-body">
            <Row k="version" v={http.version} />
            <Row k="raison" v={http.reason} />
            <div className="wire-layer-sub">en-têtes requête</div>
            <Headers headers={http.request_headers} />
            <div className="wire-layer-sub">en-têtes réponse</div>
            <Headers headers={http.response_headers} />
          </div>
        </details>
      )}
      {timing && (
        <details className="wire-layer wire-layer-timing">
          <summary>Timing — waterfall</summary>
          <div className="wire-layer-body">
            <Row k="TCP connect" v={timing.tcp_setup_ms != null ? `${timing.tcp_setup_ms} ms` : null} />
            <Row k="TLS handshake" v={timing.tls_setup_ms != null ? `${timing.tls_setup_ms} ms` : null} />
            <Row k="TTFB" v={timing.ttfb_ms != null ? `${timing.ttfb_ms} ms` : null} />
            <Row k="total" v={timing.total_ms != null ? `${timing.total_ms} ms` : null} />
          </div>
        </details>
      )}
    </div>
  );
}
