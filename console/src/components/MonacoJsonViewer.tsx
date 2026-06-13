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
 */

import Editor, { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import jsonWorker from "monaco-editor/esm/vs/language/json/json.worker?worker";

(self as typeof self & { MonacoEnvironment?: monaco.Environment }).MonacoEnvironment = {
  getWorker(_workerId: string, label: string): Worker {
    return label === "json" ? new jsonWorker() : new editorWorker();
  },
};
loader.config({ monaco });

export interface MonacoJsonViewerProps {
  value: string;
}

export default function MonacoJsonViewer({ value }: MonacoJsonViewerProps): JSX.Element {
  return (
    <Editor
      height="60vh"
      language="json"
      theme="vs-dark"
      value={value}
      options={{
        readOnly: true,
        minimap: { enabled: false },
        wordWrap: "on",
        fontSize: 12,
        scrollBeyondLastLine: false,
      }}
    />
  );
}
