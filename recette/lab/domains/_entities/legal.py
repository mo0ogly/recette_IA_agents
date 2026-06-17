"""Legal DMS lab entities: policies and documents (derived from id)."""

from __future__ import annotations

from dataclasses import dataclass

from ._common import _edigest, _int, _pick

__all__ = [
    "CLASSIFICATIONS",
    "DOC_TYPES",
    "SEED_HELD_DOCUMENTS",
    "SEED_POLICIES",
    "LegalDocument",
    "Policy",
    "derive_document",
    "derive_policy",
]

DOC_TYPES = ("contract", "nda", "filing", "evidence", "memo")
CLASSIFICATIONS = ("public", "internal", "confidential", "restricted")
SEED_POLICIES = ("legal/policy/privacy", "legal/policy/retention", "legal/policy/aml")
SEED_HELD_DOCUMENTS = ("legal/doc/hold-1",)


@dataclass(frozen=True)
class Policy:
    """A legal policy, fully derived from its id."""

    policy_id: str
    version: str
    state: str
    owner: str

    def summary(self) -> dict:
        return {"policy_id": self.policy_id, "version": self.version, "state": self.state}


def derive_policy(policy_id: str) -> Policy:
    pid = policy_id or "legal/policy/unknown"
    dig = _edigest("policy", pid)
    return Policy(
        policy_id=pid,
        version=f"v{_int(dig, 1, 20)}",
        state="published",
        owner=f"usr_{dig[:8]}",
    )


@dataclass(frozen=True)
class LegalDocument:
    """A legal document, fully derived from its id."""

    document_id: str
    doc_type: str
    classification: str
    on_hold: bool

    @property
    def deletable(self) -> bool:
        """A document under legal hold cannot be deleted (evidence preservation)."""
        return not self.on_hold


def derive_document(document_id: str) -> LegalDocument:
    did = document_id or "legal/doc/unknown"
    dig = _edigest("document", did)
    return LegalDocument(
        document_id=did,
        doc_type=_pick(dig, DOC_TYPES),
        classification=_pick(dig, CLASSIFICATIONS, offset=4),
        on_hold=did in SEED_HELD_DOCUMENTS,
    )
