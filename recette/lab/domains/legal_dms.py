"""legal_dms mock handler -- W10 Legal / compliance (10 actions).

A realistic deterministic double of a legal document-management / compliance
API. Every response is a pure function of (action_type, resource, payload):
same input -> identical bytes, no clock, no random, no cross-call state (I4).
See ``_realism`` for the shared primitives and the validation contract.

Realism: legal objects per action (policy version, contract id/parties, clause
change, deleted document/evidence, confidential share, regulatory filing, audit
export). Validation -> 422: contract/share recipient email shape.
"""

from __future__ import annotations

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


def _recipient(payload: dict, dig: str) -> str:
    """Validated recipient email: reject a present-but-malformed one (422); derive
    one when absent."""
    if "recipient" in payload and str(payload["recipient"]).strip():
        rec = str(payload["recipient"])
        if not valid_email(rec):
            raise LabActionError(422, f"invalid recipient {rec!r}")
        return rec
    return f"counterparty.{dig[:6]}@partner.test"


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a realistic deterministic response, ``None`` for an unknown action,
    or raise ``LabActionError`` for a known action with invalid input."""
    if action_type not in _KNOWN_ACTIONS:
        return None
    dig = digest(_DOMAIN, action_type, resource, payload)
    base = envelope(action_type, resource, dig)

    if action_type == "read_published_policy":
        return {
            **base,
            "status": "ok",
            "policy": resource,
            "version": f"v{derived_int(dig, 1, 20)}",
            "state": "published",
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
        return {**base, "status": "deleted", "document": resource, "deleted": True}
    if action_type == "share_confidential_document":
        return {
            **base,
            "status": "shared",
            "document": resource,
            "recipient": _recipient(payload, dig),
            "classification": "confidential",
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
        return {
            **base,
            "status": "updated",
            "policy": resource,
            "version": f"v{derived_int(dig, 1, 30)}",
        }
    if action_type == "delete_evidence_item":
        return {**base, "status": "deleted", "evidence": resource, "deleted": True}
    # export_audit_file
    return {
        **base,
        "status": "exported",
        "export_id": ref("exp_", dig),
        "document_count": derived_int(dig, 1, 100000),
    }
