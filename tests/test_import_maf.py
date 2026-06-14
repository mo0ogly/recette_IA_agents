"""Importing a Microsoft Agent Framework declarative spec yields a valid, faithful
agent-spec: tools keep their kind, require_approval becomes the approval gate (I6),
handoffs map to handoff capabilities, and unrecognized tools are reported as gaps
rather than fabricated."""

from __future__ import annotations

import unittest

from recette.import_maf import (
    MAF_TOOL_KINDS,
    capabilities_from_maf,
    maf_to_manifest,
    slugify,
)
from recette.manifest import validate

# A MAF declarative spec modelled on the Microsoft Learn DiagnosticAgent example,
# extended with the tool kinds the standard defines (mcp with require_approval,
# hosted web_search, a function tool) and a handoff.
MAF_SPEC = {
    "kind": "Prompt",
    "name": "Diagnostic Agent",
    "displayName": "Diagnostic Assistant",
    "instructions": "Specialized diagnostic and issue detection agent.",
    "description": "Performs diagnostics and escalates critical errors.",
    "model": {
        "id": "=Env.AZURE_OPENAI_MODEL",
        "provider": "AzureOpenAI",
        "connection": {"kind": "remote", "endpoint": "=Env.FOUNDRY_PROJECT_ENDPOINT"},
    },
    "tools": [
        {"type": "web_search"},
        {
            "type": "mcp",
            "server_label": "DiagnosticServer",
            "server_url": "https://mcp-server.example.com/mcp",
            "require_approval": "always",
        },
        {"type": "function", "name": "restart_service"},
    ],
    "handoffs": ["remediation-agent"],
}


class TestImportMaf(unittest.TestCase):
    def test_imported_spec_is_schema_valid(self) -> None:
        spec, _gaps = maf_to_manifest(MAF_SPEC)
        self.assertEqual(validate("manifest", spec), [])
        self.assertEqual(spec["kind"], "maf_agent")
        self.assertIn("azureopenai", spec["target_systems"])

    def test_identity_maps_from_model(self) -> None:
        spec, _ = maf_to_manifest(MAF_SPEC)
        self.assertEqual(spec["declared_identity"]["provider"], "AzureOpenAI")
        self.assertEqual(spec["declared_identity"]["model"], "=Env.AZURE_OPENAI_MODEL")
        self.assertEqual(spec["declared_identity"]["connection_kind"], "remote")

    def test_require_approval_becomes_approval_gate(self) -> None:
        scope, _ = capabilities_from_maf(MAF_SPEC)
        mcp = next(c for c in scope if c.get("tool_kind") == "mcp")
        self.assertEqual(mcp["approval"], "always")  # escalate / blocks (I6)
        # A tool without require_approval is never fabricated into a gate.
        ws = next(c for c in scope if c.get("tool_kind") == "web_search")
        self.assertEqual(ws["approval"], "never")

    def test_real_maf_declarative_schema(self) -> None:
        # The real MAF declarative Tool model (agent_framework_declarative._models):
        # discriminator `kind`, McpTool with `url`/`serverName` and an `approvalMode`
        # object whose kind is always|never|specify.
        spec = {
            "kind": "Prompt",
            "name": "Diagnostic Agent",
            "model": {"id": "=Env.MODEL", "provider": "AzureOpenAI"},
            "tools": [
                {"kind": "web_search", "name": "search"},
                {
                    "kind": "mcp",
                    "name": "diag",
                    "serverName": "diagnostic-mcp",
                    "url": "https://mcp.example.com/mcp",
                    "approvalMode": {"kind": "always"},
                },
                {"kind": "function", "name": "restart_service"},
            ],
        }
        manifest, gaps = maf_to_manifest(spec)
        self.assertEqual(validate("manifest", manifest), [])
        self.assertEqual(gaps, [])
        scope = manifest["capability_scope"]
        mcp = next(c for c in scope if c.get("tool_kind") == "mcp")
        self.assertEqual(mcp["target"], "https://mcp.example.com/mcp")  # McpTool.url
        self.assertEqual(mcp["approval"], "always")  # approvalMode.kind == always (I6)
        fn = next(c for c in scope if c.get("tool_kind") == "function")
        self.assertEqual(fn["target"], "restart_service")

    def test_specify_approval_mode_is_gated(self) -> None:
        # approvalMode.kind == "specify" requires approval for some tools -> gated.
        spec = {
            "kind": "Prompt",
            "name": "Agent",
            "model": {"id": "m", "provider": "p"},
            "tools": [{"kind": "mcp", "url": "https://s/mcp", "approvalMode": {"kind": "specify"}}],
        }
        scope, _ = capabilities_from_maf(spec)
        self.assertEqual(scope[0]["approval"], "always")

    def test_handoff_maps_to_capability(self) -> None:
        scope, _ = capabilities_from_maf(MAF_SPEC)
        handoffs = [c for c in scope if c["action"] == "handoff"]
        self.assertEqual(handoffs, [{"action": "handoff", "target": "remediation-agent"}])

    def test_unknown_tool_is_a_gap_not_invented(self) -> None:
        spec = {**MAF_SPEC, "tools": [{"type": "telepathy"}, {"type": "web_search"}]}
        scope, gaps = capabilities_from_maf(spec)
        self.assertIn("telepathy", gaps)
        self.assertTrue(
            all(c["action"] != "invoke_tool" or c["tool_kind"] in MAF_TOOL_KINDS for c in scope)
        )

    def test_provenance_recorded(self) -> None:
        spec, _ = maf_to_manifest(MAF_SPEC)
        self.assertEqual(spec["source"]["standard"], "microsoft-agent-framework")
        self.assertEqual(spec["source"]["maf_kind"], "Prompt")

    def test_missing_identity_is_surfaced_not_guessed(self) -> None:
        no_provider = {**MAF_SPEC, "model": {"id": "x"}}
        with self.assertRaises(ValueError):
            maf_to_manifest(no_provider)

    def test_no_capability_is_rejected(self) -> None:
        bare = {k: v for k, v in MAF_SPEC.items() if k not in ("tools", "handoffs")}
        with self.assertRaises(ValueError):
            maf_to_manifest(bare)

    def test_slugify(self) -> None:
        self.assertEqual(slugify("Diagnostic Agent"), "diagnostic-agent")
        self.assertEqual(slugify("  GPT-4o!! "), "gpt-4o")
        with self.assertRaises(ValueError):
            slugify("!!!")


if __name__ == "__main__":
    unittest.main()
