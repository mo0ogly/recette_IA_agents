#!/usr/bin/env node
/**
 * recette_sh_gate.cjs - PreToolUse(Bash) hook.
 *
 * Enforces the single-entry-point rule (user mandate 2026-06-13): every
 * build / test / gate invocation MUST go through ./recette.sh. Direct calls
 * to the underlying tools are blocked with the recette.sh equivalent.
 *
 * Allowed automatically:
 * - any command that itself invokes recette.sh (the wrapper's own
 *   subprocesses never pass through this hook, only top-level Bash calls);
 * - cicd/*.sh direct invocations (they ARE the wrapper's delegates);
 * - everything that is not a build/test command.
 *
 * Exit codes: 0 = allow, 2 = block (stderr is fed back to the model).
 */

"use strict";

function readStdin() {
  try {
    const fs = require("fs");
    return fs.readFileSync(0, "utf8");
  } catch {
    return "";
  }
}

const raw = readStdin();
let command = "";
try {
  const payload = JSON.parse(raw);
  command = String((payload.tool_input && payload.tool_input.command) || "");
} catch {
  process.exit(0); // unparsable input: never block on hook failure
}

if (command === "") {
  process.exit(0);
}

// The wrapper itself (or its cicd delegates) is always allowed.
if (
  /(^|[\s;&|/])recette\.sh\b/.test(command) ||
  /(^|[\s;&|])\.?\/?cicd\/[a-z_]+\.sh\b/.test(command)
) {
  process.exit(0);
}

/** Forbidden direct invocations -> recette.sh equivalent. */
const RULES = [
  { re: /\b(python3?\s+-m\s+unittest|pytest)\b/, eq: "./recette.sh test" },
  { re: /\b(ruff|mypy|bandit)\b/, eq: "./recette.sh gates" },
  { re: /\bmake\s+(test|gates|validate|run|discovery|report)\b/, eq: "./recette.sh <same target>" },
  { re: /\bvitest\b/, eq: "./recette.sh console-test" },
  { re: /\b(tsc|vite\s+build)\b/, eq: "./recette.sh console-build" },
  { re: /\bnpm\s+(run\s+build|test|run\s+test)\b/, eq: "./recette.sh console-build / console-test" },
  { re: /\bcargo\s+(build|test|clippy)\b/, eq: "./recette.sh (add a rust target to cicd/checks.sh first)" },
  { re: /\bpython3?\s+-m\s+recette\s+(validate|run|discovery|report)\b/, eq: "./recette.sh <same target>" },
];

for (const rule of RULES) {
  if (rule.re.test(command)) {
    process.stderr.write(
      "BLOCKED by recette_sh_gate: direct build/test invocation is forbidden. " +
        `Use the single entry point instead: ${rule.eq} ` +
        "(rule: all compilation/tests go through ./recette.sh).\n",
    );
    process.exit(2);
  }
}

process.exit(0);
