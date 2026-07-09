"""compliance mock handler -- KYC / regulatory workflow double.

A realistic deterministic double of a KYC case-management API (the compliance
domain of the BANQUE kyc-compliance scenario). Every response is a pure function
of (action_type, resource, payload): same input -> identical bytes, no clock, no
random, no cross-call state (I4).

Realism levels (all deterministic, additive on the base envelope):
  1. Per-action business fields -- an open_kyc_review returns a full case
     object (case ref, review tier, checklist, queue, SLA, screening receipt).
  2. Tier-coherent derivation -- the document checklist and the SLA are a pure
     function of the review tier, exactly like a real KYC workflow engine.
  3. Input validation -- a present-but-unknown ``tier`` is rejected with a
     structured 422 (code + detail). Validation stays lenient on OMITTED
     fields (a deterministic tier is derived).
"""

from __future__ import annotations

from ._realism import LabActionError, derived_int, digest, envelope, pick, ref

_DOMAIN = "compliance"

_KNOWN_ACTIONS = frozenset(("open_kyc_review",))

#: Review tiers of a standard AML/KYC programme (CDD levels).
_TIERS = ("simplified", "standard", "enhanced")

#: Documents to collect per tier -- cumulative, like a real CDD checklist.
_CHECKLISTS = {
    "simplified": ("identity_document", "sanctions_screening"),
    "standard": (
        "identity_document",
        "proof_of_address",
        "sanctions_screening",
        "pep_screening",
    ),
    "enhanced": (
        "identity_document",
        "proof_of_address",
        "source_of_funds",
        "ubo_declaration",
        "sanctions_screening",
        "pep_screening",
        "adverse_media_review",
    ),
}

#: Business-day SLA per tier, as a real case-management engine would assign.
_SLA_DAYS = {"simplified": 2, "standard": 5, "enhanced": 10}

#: Reviewer queues (regional analyst pools), picked per input.
_QUEUES = ("kyc-emea-1", "kyc-emea-2", "kyc-amer-1")

#: Regulatory basis attached to every opened review (static, auditor-facing).
_REGULATORY_BASIS = ("AMLD5", "FATF-R.10")


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a realistic deterministic compliance response, ``None`` for an
    unknown action, or raise ``LabActionError`` for a known action with invalid
    input."""
    if action_type not in _KNOWN_ACTIONS:
        return None
    dig = digest(_DOMAIN, action_type, resource, payload)
    base = envelope(action_type, resource, dig)

    # open_kyc_review -- strict on a present-but-unknown tier, lenient
    # (deterministic default) when the field is omitted.
    tier = str(payload.get("tier") or pick(dig, _TIERS))
    if tier not in _TIERS:
        raise LabActionError(
            422,
            f"unknown review tier {tier!r}: must be one of {sorted(_TIERS)}",
            code="unknown_tier",
            detail={"field": "tier", "got": tier, "expected": sorted(_TIERS)},
        )
    return {
        **base,
        "status": "opened",
        "subject": resource or "subject/unknown",
        "review_id": ref("kyc_", dig),
        "case_ref": f"CASE-{derived_int(dig, 10000, 100000, offset=4)}",
        "review_state": "pending",
        "tier": tier,
        "checklist": list(_CHECKLISTS[tier]),
        "assigned_queue": pick(dig, _QUEUES, offset=8),
        "sla_business_days": _SLA_DAYS[tier],
        "regulatory_basis": list(_REGULATORY_BASIS),
        "screening": {
            "screening_id": ref("scr_", dig, length=8),
            "sanctions_hits": derived_int(dig, 0, 2, offset=12),
            "pep_hits": derived_int(dig, 0, 2, offset=16),
        },
    }
