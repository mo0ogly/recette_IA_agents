/**
 * Shared render helpers for the explain modals. Pure presentation over the
 * free-form manifest / ground-truth JSON (shapes vary across families), so each
 * renderer shows the well-known fields when present and the modals also expose a
 * raw-JSON tab so nothing is ever hidden.
 */
import type { ReactNode } from "react";

function asText(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
    return String(v);
  }
  return JSON.stringify(v);
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** A two-column key/value block; rows whose value is empty are dropped. */
export function KvList({ entries }: { entries: Array<[string, ReactNode]> }): JSX.Element {
  const rows = entries.filter(([, v]) => v !== null && v !== undefined && v !== "");
  return (
    <dl className="tm-kv">
      {rows.map(([k, v]) => (
        <div key={k} style={{ display: "contents" }}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Pretty-printed raw JSON (the complete, never-hidden view). */
export function RawJson({ value }: { value: unknown }): JSX.Element {
  return <pre className="tm-pre">{JSON.stringify(value, null, 2)}</pre>;
}

/** Bullet list of strings, or an italic empty note. */
export function StringList({ items, empty }: { items: string[]; empty: string }): JSX.Element {
  if (items.length === 0) return <p className="tm-empty">{empty}</p>;
  return (
    <ul className="tm-list">
      {items.map((s) => (
        <li key={s}>{s}</li>
      ))}
    </ul>
  );
}

/** The declared identity + capabilities of a corpus subject's manifest. */
export function ManifestView({ manifest }: { manifest: Record<string, unknown> }): JSX.Element {
  const identity = isRecord(manifest.declared_identity) ? manifest.declared_identity : {};
  const systems = Array.isArray(manifest.target_systems)
    ? manifest.target_systems.map(asText)
    : [];
  const scope = Array.isArray(manifest.capability_scope) ? manifest.capability_scope : [];
  return (
    <>
      <KvList
        entries={[
          ["Nom", asText(manifest.name)],
          ["Description", asText(manifest.description)],
          ["Principal", asText(identity.principal)],
          ["Auth", asText(identity.auth_method)],
          ["Systemes", systems.join(", ")],
        ]}
      />
      <h3>Capability scope declare</h3>
      {scope.length === 0 ? (
        <p className="tm-empty">Aucune capacite declaree.</p>
      ) : (
        <ul className="tm-list">
          {scope.map((c, i) => {
            const rec = isRecord(c) ? c : {};
            const action = asText(rec.action) || asText(c);
            const mode = asText(rec.mode);
            const resources = Array.isArray(rec.resources) ? rec.resources.map(asText).join(", ") : "";
            return (
              <li key={`${action}-${i}`}>
                <code>{action}</code>
                {mode ? <span className="tm-pill">{mode}</span> : null} {resources}
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}

const DIMENSIONS: Array<[string, string]> = [
  ["identity", "match"],
  ["capabilities", "conforms"],
  ["policy", "compliant"],
  ["behavior", "expected"],
];

/** The ground-truth posture: expected verdict + the four recette dimensions. */
export function GroundTruthView({
  groundTruth,
}: {
  groundTruth: Record<string, unknown>;
}): JSX.Element {
  if (Object.keys(groundTruth).length === 0) {
    return <p className="tm-empty">Aucun ground-truth pour ce sujet.</p>;
  }
  const verdict = asText(groundTruth.expected_verdict);
  const ident = isRecord(groundTruth.expected_identification)
    ? groundTruth.expected_identification
    : {};
  return (
    <>
      <KvList
        entries={[
          [
            "Verdict attendu",
            verdict ? (
              <span className={`tm-pill ${verdict === "correct" ? "tm-pill-ok" : "tm-pill-bad"}`}>
                {verdict}
              </span>
            ) : (
              ""
            ),
          ],
          ["Categorie", asText(groundTruth.category)],
          ["Violation", asText(groundTruth.violation_type)],
        ]}
      />
      <h3>Quatre dimensions</h3>
      <ul className="tm-list">
        {DIMENSIONS.map(([dim, flagKey]) => {
          const block = isRecord(ident[dim]) ? (ident[dim] as Record<string, unknown>) : null;
          if (block === null) return null;
          const ok = block[flagKey] === true;
          const note = asText(block.note ?? block.notes);
          return (
            <li key={dim}>
              <strong>{dim}</strong>{" "}
              <span className={`tm-pill ${ok ? "tm-pill-ok" : "tm-pill-bad"}`}>
                {ok ? "conforme" : "casse"}
              </span>
              {note ? ` -- ${note}` : ""}
            </li>
          );
        })}
      </ul>
    </>
  );
}

/**
 * The inline runtime-agent ground-truth posture. Unlike a corpus subject (whose
 * dimensions are nested per-axis blocks under expected_identification), a runtime
 * agent carries a flat shape: expected_verdict + a dimensions map of booleans +
 * expected_identity. Rendered as-is so an agent that declares its own truth (e.g.
 * a campaign probe with an empty scope) is not shown as "no ground-truth".
 */
export function InlineGroundTruthView({
  groundTruth,
}: {
  groundTruth: Record<string, unknown>;
}): JSX.Element {
  const verdict = asText(groundTruth.expected_verdict);
  const dims = isRecord(groundTruth.dimensions) ? groundTruth.dimensions : {};
  const identity = asText(groundTruth.expected_identity);
  const detectable = groundTruth.detectable === true;
  return (
    <>
      <KvList
        entries={[
          [
            "Verdict attendu",
            verdict ? (
              <span className={`tm-pill ${verdict === "correct" ? "tm-pill-ok" : "tm-pill-bad"}`}>
                {verdict}
              </span>
            ) : (
              ""
            ),
          ],
          ["Identite attendue", identity],
          ["Detectable", detectable ? "oui" : "non"],
        ]}
      />
      <h3>Quatre dimensions</h3>
      <ul className="tm-list">
        {DIMENSIONS.map(([dim]) => {
          const raw = dims[dim];
          if (raw === undefined) return null;
          const ok = raw === true;
          return (
            <li key={dim}>
              <strong>{dim}</strong>{" "}
              <span className={`tm-pill ${ok ? "tm-pill-ok" : "tm-pill-bad"}`}>
                {ok ? "conforme" : "casse"}
              </span>
            </li>
          );
        })}
      </ul>
    </>
  );
}
