/**
 * MonacoDiffViewer -- lazy-loaded Monaco DiffEditor for comparing two events.
 *
 * Same offline-lab posture as MonacoJsonViewer (local monaco package, bundled
 * JSON/editor workers, no CDN). Used by the analyzer's "diff" mode to put two
 * audited events side by side -- e.g. an action_requested vs its
 * approval_resolved, or a declared vs effective shape. Read-only on both sides:
 * the audit log is immutable (I1), the diff is an inspection surface only.
 */

import { DiffEditor, loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import jsonWorker from "monaco-editor/esm/vs/language/json/json.worker?worker";

(self as typeof self & { MonacoEnvironment?: monaco.Environment }).MonacoEnvironment = {
  getWorker(_workerId: string, label: string): Worker {
    return label === "json" ? new jsonWorker() : new editorWorker();
  },
};
loader.config({ monaco });

export interface MonacoDiffViewerProps {
  /** Left-hand side (the "original" / reference event). */
  original: string;
  /** Right-hand side (the "modified" / compared event). */
  modified: string;
}

export default function MonacoDiffViewer({
  original,
  modified,
}: MonacoDiffViewerProps): JSX.Element {
  return (
    <DiffEditor
      height="60vh"
      language="json"
      theme="vs-dark"
      original={original}
      modified={modified}
      options={{
        readOnly: true,
        originalEditable: false,
        renderSideBySide: true,
        minimap: { enabled: false },
        wordWrap: "on",
        fontSize: 12,
        scrollBeyondLastLine: false,
      }}
    />
  );
}
