/**
 * MonacoJsonViewer -- the lazy-loaded Monaco chunk (local, offline-safe).
 *
 * This module is ONLY reached through React.lazy from FluxAnalyzer, so the
 * monaco-editor payload stays out of the base bundle. Two lab-posture rules
 * are enforced here:
 * - loader.config({ monaco }) points @monaco-editor/react at the LOCAL
 *   monaco-editor package. Without it the default loader fetches Monaco from
 *   a CDN at runtime -- forbidden in the offline lab (R5, reproducibility).
 * - MonacoEnvironment.getWorker serves the editor/json workers from the Vite
 *   bundle (?worker imports), not from a CDN. Only the JSON worker is wired:
 *   this viewer renders JSON exclusively.
 *
 * Sophisticated mode: callers may pass per-line `decorations` (verdict colour,
 * approval glyph, risk-heatmap minimap tint). Decorations are a DISPLAY layer
 * over the immutable audit log (I1); the editor stays read-only. The minimap is
 * enabled only when at least one decoration carries a heatmap colour, so the
 * plain single-event view keeps its clean look.
 */

import Editor, { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import jsonWorker from "monaco-editor/esm/vs/language/json/json.worker?worker";
import { useCallback, useEffect, useRef } from "react";

import type { FluxDecoration } from "./fluxModel";

(self as typeof self & { MonacoEnvironment?: monaco.Environment }).MonacoEnvironment = {
  getWorker(_workerId: string, label: string): Worker {
    return label === "json" ? new jsonWorker() : new editorWorker();
  },
};
loader.config({ monaco });

export interface MonacoJsonViewerProps {
  value: string;
  /** Per-line governance decorations; empty/undefined renders a plain view. */
  decorations?: FluxDecoration[];
  /** Editor height (any CSS height). Defaults to a tall 60vh viewer. */
  height?: string;
}

type Editor = monaco.editor.IStandaloneCodeEditor;

/** Translate Monaco-agnostic descriptors into model delta decorations. */
function toModelDecorations(decos: FluxDecoration[]): monaco.editor.IModelDeltaDecoration[] {
  return decos.map((d) => ({
    range: new monaco.Range(d.line, 1, d.line, 1),
    options: {
      isWholeLine: true,
      className: d.className,
      glyphMarginClassName: d.glyphMarginClassName,
      hoverMessage: { value: d.hover },
      minimap:
        d.minimapColor === undefined
          ? undefined
          : {
              color: d.minimapColor,
              position: monaco.editor.MinimapPosition.Inline,
            },
    },
  }));
}

export default function MonacoJsonViewer({
  value,
  decorations = [],
  height = "60vh",
}: MonacoJsonViewerProps): JSX.Element {
  const collectionRef = useRef<monaco.editor.IEditorDecorationsCollection | null>(null);
  const hasHeatmap = decorations.some((d) => d.minimapColor !== undefined);
  const hasGlyph = decorations.some((d) => d.glyphMarginClassName !== undefined);

  // Latest decorations reachable from the async onMount (Monaco mounts after
  // the first render/effect pass, when no collection exists yet).
  const decorationsRef = useRef<FluxDecoration[]>(decorations);
  decorationsRef.current = decorations;

  const onMount = useCallback((editor: Editor) => {
    collectionRef.current = editor.createDecorationsCollection(
      toModelDecorations(decorationsRef.current),
    );
  }, []);

  // Re-apply whenever the decoration set changes on an already-mounted editor.
  // An empty set clears: switching event<->stream must not leave stale lines lit.
  useEffect(() => {
    collectionRef.current?.set(toModelDecorations(decorations));
  }, [decorations]);

  return (
    <Editor
      height={height}
      language="json"
      theme="vs-dark"
      value={value}
      onMount={onMount}
      options={{
        readOnly: true,
        // Relayout when the container is sized/shown after mount (e.g. a tab or a
        // dynamically-revealed panel) -- otherwise a width-0 mount renders only
        // the line-number gutter with no visible text.
        automaticLayout: true,
        minimap: { enabled: hasHeatmap },
        glyphMargin: hasGlyph,
        wordWrap: "on",
        fontSize: 12,
        scrollBeyondLastLine: false,
      }}
    />
  );
}
