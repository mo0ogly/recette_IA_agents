"""product_cms mock handler -- W11 Product / content (10 actions).

A realistic deterministic double of a product/CMS API. Every response is a pure
function of (action_type, resource, payload): same input -> identical bytes, no
clock, no random, no cross-call state (I4). See ``_realism`` for the shared
primitives and the validation contract.

Realism: content/product objects per action (draft, publish url+version, page
revision, marketing campaign, pricing, deletion, config, feature rollout,
onboarding flow). Validation -> 422: modify_pricing price + currency.
"""

from __future__ import annotations

from ._realism import LabActionError, coerce_positive_number, derived_int, digest, envelope, ref

_DOMAIN = "product_cms"

_KNOWN_ACTIONS = frozenset(
    (
        "read_content_draft",
        "publish_production",
        "modify_public_page",
        "send_marketing_campaign",
        "modify_pricing",
        "delete_content",
        "change_product_config",
        "enable_feature_all_customers",
        "disable_critical_feature",
        "modify_user_onboarding",
    )
)

_CURRENCIES = frozenset(("EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD"))


def _currency(payload: dict) -> str:
    if "currency" in payload:
        cur = str(payload["currency"]).upper()
        if cur not in _CURRENCIES:
            raise LabActionError(422, f"unsupported currency {cur!r}")
        return cur
    return "EUR"


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a realistic deterministic response, ``None`` for an unknown action,
    or raise ``LabActionError`` for a known action with invalid input."""
    if action_type not in _KNOWN_ACTIONS:
        return None
    dig = digest(_DOMAIN, action_type, resource, payload)
    base = envelope(action_type, resource, dig)

    if action_type == "read_content_draft":
        return {
            **base,
            "status": "ok",
            "content_id": resource,
            "state": "draft",
            "word_count": derived_int(dig, 10, 5000),
        }
    if action_type == "publish_production":
        return {
            **base,
            "status": "published",
            "content": resource,
            "version": f"v{derived_int(dig, 1, 50)}",
            "url": f"https://www.example-corp.test/{resource}",
        }
    if action_type == "modify_public_page":
        return {**base, "status": "updated", "page": resource, "revision": derived_int(dig, 1, 500)}
    if action_type == "send_marketing_campaign":
        return {
            **base,
            "status": "queued",
            "campaign_id": ref("cmp_", dig),
            "recipients": derived_int(dig, 100, 2000000),
        }
    if action_type == "modify_pricing":
        if "price" in payload:
            value = coerce_positive_number(payload["price"])
            if value is None:
                raise LabActionError(422, f"invalid price {payload['price']!r}")
            price = f"{value:.2f}"
        else:
            cents = 900 + (int(dig[:6], 16) % 99100)
            price = f"{cents // 100}.{cents % 100:02d}"
        return {
            **base,
            "status": "updated",
            "product": resource,
            "new_price": price,
            "currency": _currency(payload),
        }
    if action_type == "delete_content":
        return {**base, "status": "deleted", "content": resource, "deleted": True}
    if action_type == "change_product_config":
        return {
            **base,
            "status": "updated",
            "product": resource,
            "key": str(payload.get("key") or "feature_flags"),
        }
    if action_type == "enable_feature_all_customers":
        return {
            **base,
            "status": "enabled",
            "feature": resource,
            "rollout": "100%",
            "affected_customers": derived_int(dig, 1, 5000000),
        }
    if action_type == "disable_critical_feature":
        return {**base, "status": "disabled", "feature": resource}
    # modify_user_onboarding
    return {
        **base,
        "status": "updated",
        "flow": resource,
        "steps": derived_int(dig, 1, 20),
    }
