/**
 * MonacoPromptEditor -- lazy-loaded editable Monaco chunk (local, offline-safe).
 *
 * Only reached through React.lazy from PromptEditModal, so the monaco-editor
 * payload stays out of the base bundle. Same lab-posture rules as
 * MonacoJsonViewer: local loader (no CDN) and bundled workers (R5).
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

export default function MonacoPromptEditor({
  value,
  language,
  onChange,
}: {
  value: string;
  language: "plaintext" | "json";
  onChange: (next: string) => void;
}): JSX.Element {
  return (
    <Editor
      height="46vh"
      language={language}
      value={value}
      onChange={(next) => onChange(next ?? "")}
      options={{
        minimap: { enabled: false },
        wordWrap: "on",
        fontSize: 13,
        lineNumbers: "off",
        scrollBeyondLastLine: false,
        automaticLayout: true,
      }}
    />
  );
}
