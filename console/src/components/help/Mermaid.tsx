/**
 * Render a mermaid diagram inside the help modal.
 *
 * mermaid is heavy (~2.8 MB), so it is loaded with a DYNAMIC import inside the
 * effect: vite code-splits it into its own chunk that is only fetched when a
 * diagram actually mounts (i.e. when an operator opens a help topic that has
 * one), keeping the main bundle lean.
 *
 * Legibility-first + test-safe: the raw chart source is ALWAYS rendered first as
 * a <pre> fallback. On success the rendered SVG replaces it; on any failure (or
 * in a jsdom test where mermaid cannot draw) the legible source stays. The
 * source is a static literal supplied by the topic (never user input), so the
 * SVG injected here is trusted.
 */

import { useEffect, useRef, useState } from "react";

// mermaid.render mutates shared DOM state keyed by the render id, so two diagrams
// (or React StrictMode's double-invoked effect reusing one id) collide and one
// comes back empty. Two defences: (1) serialize every render through a single
// module-level promise chain, and (2) give EACH render call a globally-unique id
// from a module counter -- never the component's useId, which StrictMode would
// reuse across its double mount and corrupt the first diagram.
let renderQueue: Promise<unknown> = Promise.resolve();
let renderSeq = 0;

function enqueueRender(chart: string): Promise<string> {
  const uid = `help-mermaid-${(renderSeq += 1)}`;
  const run = renderQueue.then(async () => {
    const { default: mermaid } = await import("mermaid");
    mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "neutral" });
    const { svg } = await mermaid.render(uid, chart);
    return svg;
  });
  // Keep the chain alive even if this render rejects (one bad chart must not
  // wedge the queue for the next diagram).
  renderQueue = run.catch(() => undefined);
  return run;
}

export default function Mermaid({ chart, title }: { chart: string; title?: string }): JSX.Element {
  const [svg, setSvg] = useState<string | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    enqueueRender(chart)
      .then((rendered) => {
        if (alive.current) setSvg(rendered);
      })
      .catch(() => {
        // Keep the <pre> source fallback (legible) -- never crash the modal.
      });
    return () => {
      alive.current = false;
    };
  }, [chart]);

  return (
    <figure className="help-mermaid" data-testid="help-mermaid">
      {title && <figcaption className="help-mermaid-title">{title}</figcaption>}
      {svg ? (
        // Trusted static literal source rendered by mermaid (securityLevel strict).
        <div
          className="help-mermaid-svg"
          data-testid="help-mermaid-svg"
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      ) : (
        <pre className="help-mermaid-source" data-testid="help-mermaid-source">
          {chart}
        </pre>
      )}
    </figure>
  );
}
