"""Loading and schema validation for corpus artifacts (manifest, ground-truth, scenario)."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

# Repo-root-relative schema directory. Resolved from this file's location so the
# package works regardless of the current working directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCHEMA_DIR = _REPO_ROOT / "corpus" / "schemas"

_SCHEMAS = {
    "manifest": _SCHEMA_DIR / "agent-manifest.schema.json",
    "ground_truth": _SCHEMA_DIR / "ground-truth.schema.json",
    "scenario": _SCHEMA_DIR / "scenario.schema.json",
}


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _validator(kind: str) -> jsonschema.protocols.Validator:
    schema = _load_json(_SCHEMAS[kind])
    cls = jsonschema.validators.validator_for(schema)
    cls.check_schema(schema)
    return cls(schema)


def validate(kind: str, data: dict) -> list[str]:
    """Return a list of human-readable validation errors (empty = valid)."""
    validator = _validator(kind)
    return [
        f"{kind}: {e.message} at {'/'.join(map(str, e.path)) or '<root>'}"
        for e in sorted(validator.iter_errors(data), key=str)
    ]


def load_validated(kind: str, path: Path) -> dict:
    """Load a JSON artifact and raise ValueError if it does not match its schema."""
    data = _load_json(path)
    errors = validate(kind, data)
    if errors:
        raise ValueError(f"{path}:\n  " + "\n  ".join(errors))
    return data


def load_manifest(path: Path) -> dict:
    return load_validated("manifest", path)


def load_ground_truth(path: Path) -> dict:
    return load_validated("ground_truth", path)


def load_scenario(path: Path) -> dict:
    return load_validated("scenario", path)
