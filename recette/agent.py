"""TestAgent: a corpus subject that replays a scripted scenario against a forge.

An agent is fully described by two files in its directory:
- manifest.json     : what it DECLARES (identity + capability_scope)
- scenario.json     : what it ACTUALLY does (ordered, deterministic actions)
- ground-truth.json : what the recette EXPECTS the tools to conclude (loaded by the harness)

Running an agent against a forge produces a deterministic action log.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .events import AgentAction
from .forge import GitForge, LabForge
from .manifest import load_manifest, load_scenario


@dataclass
class TestAgent:
    agent_id: str
    directory: Path
    manifest: dict
    scenario: dict

    @classmethod
    def from_dir(cls, directory: Path | str) -> "TestAgent":
        directory = Path(directory)
        manifest = load_manifest(directory / "manifest.json")
        scenario = load_scenario(directory / "scenario.json")
        if manifest["agent_id"] != scenario["agent_id"]:
            raise ValueError(
                f"{directory}: agent_id mismatch manifest={manifest['agent_id']} "
                f"scenario={scenario['agent_id']}"
            )
        return cls(
            agent_id=manifest["agent_id"],
            directory=directory,
            manifest=manifest,
            scenario=scenario,
        )

    @property
    def target_system(self) -> str:
        # The platform an agent acts on is taken from its first declared target.
        return self.manifest["target_systems"][0]

    def run(self, forge: GitForge | None = None) -> list[AgentAction]:
        """Replay the scenario against the forge and return the action log."""
        forge = forge or LabForge()
        principal = self.scenario["credential_principal"]
        for step in self.scenario["actions"]:
            forge.execute(
                agent_id=self.agent_id,
                principal=principal,
                target_system=self.target_system,
                action_type=step["action"],
                resource=step["resource"],
                approved=bool(step.get("approved", False)),
                params=step.get("params"),
            )
        return forge.action_log
