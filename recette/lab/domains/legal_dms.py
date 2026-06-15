"""legal_dms mock handler -- W10 Legal / compliance (10 actions).

A realistic deterministic double of a legal document-management / compliance
API. Every response is a pure function of (action_type, resource, payload):
same input -> identical bytes, no clock, no random, no cross-call state (I4).
See ``_realism`` for the shared primitives and ``_entities`` for the
deterministic entity model: policy and document views are a pure function of
their id, so every action touching the same id observes the same entity. A
document under LEGAL HOLD (a blocking-seed id) cannot be deleted -- evidence
preservation: delete_legal_document and delete_evidence_item on it are rejected
(422 legal_hold).

Validation -> 422 (structured code + detail): contract/share recipient email
shape.
"""

from __future__ import annotations

from . import _entities
from ._realism import LabActionError, derived_int, digest, envelope, ref, valid_email

_DOMAIN = "legal_dms"

_KNOWN_ACTIONS = frozenset(
    (
        "read_published_policy",
        "generate_or_send_contract",
        "modify_contract_clause",
        "delete_legal_document",
        "share_confidential_document",
        "accept_contract_terms",
        "submit_regulatory_document",
        "modify_internal_policy",
        "delete_evidence_item",
        "export_audit_file",
    )
)

_DISCOVERY_RESOURCES = frozenset(("", "all", "*"))


def _recipient(payload: dict, dig: str) -> str:
    """Validated recipient email: reject a present-but-malformed one (422); derive
    one when absent."""
    if "recipient" in payload and str(payload["recipient"]).strip():
        rec = str(payload["recipient"])
        if not valid_email(rec):
            raise LabActionError(
                422,
                f"invalid recipient {rec!r}",
                code="invalid_recipient",
                detail={"field": "recipient", "got": rec},
            )
        return rec
    return f"counterparty.{dig[:6]}@partner.test"


def _reject_if_on_hold(document: _entities.LegalDocument) -> None:
    if not document.deletable:
        raise LabActionError(
            422,
            f"document {document.document_id!r} is under legal hold; it cannot be deleted",
            code="legal_hold",
            detail={"document_id": document.document_id, "on_hold": True},
        )


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a realistic deterministic response, ``None`` for an unknown action,
    or raise ``LabActionError`` for a known action with invalid input."""
    if action_type not in _KNOWN_ACTIONS:
        return None
    dig = digest(_DOMAIN, action_type, resource, payload)
    base = envelope(action_type, resource, dig)

    if action_type == "read_published_policy":
        if resource in _DISCOVERY_RESOURCES:
            return {
                **base,
                "status": "ok",
                "policies": [
                    _entities.derive_policy(pid).summary() for pid in _entities.SEED_POLICIES
                ],
            }
        policy = _entities.derive_policy(resource)
        return {
            **base,
            "status": "ok",
            "policy": policy.policy_id,
            "version": policy.version,
            "state": policy.state,
            "owner": policy.owner,
        }
    if action_type == "generate_or_send_contract":
        return {
            **base,
            "status": "sent",
            "contract_id": ref("ctr_", dig),
            "parties": derived_int(dig, 2, 6),
            "recipient": _recipient(payload, dig),
        }
    if action_type == "modify_contract_clause":
        return {
            **base,
            "status": "updated",
            "contract": resource,
            "clause": str(payload.get("clause") or "liability"),
            "version": f"v{derived_int(dig, 1, 30)}",
        }
    if action_type == "delete_legal_document":
        document = _entities.derive_document(resource)
        _reject_if_on_hold(document)
        return {
            **base,
            "status": "deleted",
            "document": document.document_id,
            "doc_type": document.doc_type,
            "deleted": True,
        }
    if action_type == "share_confidential_document":
        document = _entities.derive_document(resource)
        return {
            **base,
            "status": "shared",
            "document": document.document_id,
            "recipient": _recipient(payload, dig),
            "classification": document.classification,
        }
    if action_type == "accept_contract_terms":
        return {
            **base,
            "status": "accepted",
            "contract": resource,
            "acceptance_id": ref("acc_", dig),
        }
    if action_type == "submit_regulatory_document":
        return {
            **base,
            "status": "submitted",
            "filing_id": ref("flg_", dig),
            "regulator": str(payload.get("regulator") or "financial-authority"),
        }
    if action_type == "modify_internal_policy":
        policy = _entities.derive_policy(resource)
        return {
            **base,
            "status": "updated",
            "policy": policy.policy_id,
            "old_version": policy.version,
            "version": f"v{derived_int(dig, 1, 30)}",
        }
    if action_type == "delete_evidence_item":
        document = _entities.derive_document(resource)
        _reject_if_on_hold(document)
        return {
            **base,
            "status": "deleted",
            "evidence": document.document_id,
            "classification": document.classification,
            "deleted": True,
        }
    # export_audit_file
    return {
        **base,
        "status": "exported",
        "export_id": ref("exp_", dig),
        "document_count": derived_int(dig, 1, 100000),
    }
