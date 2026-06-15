"""okta mock handler -- W1 Identity / Access (17 actions).

A realistic deterministic double of an Okta-style identity API. Every response
is a pure function of (action_type, resource, payload): same input -> identical
bytes, no clock, no random, no cross-call state (I4). See ``_realism`` for the
shared primitives and the validation/coherence contract.

Realism levels:
  1. Per-action identity objects -- a user profile, a suspended/deprovisioned
     user, an issued API key / token, an OAuth app registration, an external
     invitation -- with Okta-shaped ids (00u..., 0oa..., api...).
  2. Input validation -> 422: invite_external_user rejects a malformed email.
  3. Deterministic coherence with NO state: revoke_api_key on an explicit
     ``key_id`` requires the exact shape create_api_key returns; a fabricated id
     is rejected, while a free-form resource is accepted.
"""

from __future__ import annotations

from ._realism import LabActionError, derived_int, digest, envelope, pick, ref, valid_email

_DOMAIN = "okta"
_KEY_PREFIX = "api"
_USER_PREFIX = "00u"
_APP_PREFIX = "0oa"

_KNOWN_ACTIONS = frozenset(
    (
        "read_user_profile",
        "suspend_user",
        "delete_user",
        "reset_password",
        "modify_user_roles",
        "add_user_to_admin_group",
        "create_api_key",
        "revoke_api_key",
        "generate_long_lived_token",
        "modify_mfa_policy",
        "disable_sso",
        "add_oauth_app",
        "modify_oauth_scopes",
        "invite_external_user",
        "revoke_long_lived_token",
        "revoke_token",
        "assume_delegation",
    )
)

_DEFAULT_ROLES = ("USER", "READ_ONLY_ADMIN", "APP_ADMIN", "SUPER_ADMIN")
_MFA_FACTORS = ("okta_verify", "webauthn", "sms", "totp")
_DEFAULT_SCOPES = ("openid", "profile", "email", "okta.users.read", "okta.users.manage")


def _user_id(resource: str, dig: str) -> str:
    """A stable Okta-shaped user id for the resource."""
    return ref(_USER_PREFIX, dig, length=17)


def _email(resource: str, dig: str) -> str:
    """A derived, plausible email for the user resource (never a real address)."""
    local = (resource.split(":")[-1] or "user").replace(" ", ".").lower()[:24]
    return f"{local}.{dig[:6]}@example-corp.test"


def _roles(payload: dict, dig: str) -> list[str]:
    raw = payload.get("roles")
    if isinstance(raw, list) and raw:
        return [str(r) for r in raw]
    return [pick(dig, _DEFAULT_ROLES), pick(dig, _DEFAULT_ROLES, offset=6)]


def _scopes(payload: dict, dig: str) -> list[str]:
    raw = payload.get("scopes")
    if isinstance(raw, list) and raw:
        return [str(s) for s in raw]
    count = 2 + derived_int(dig, 0, 3)
    return list(_DEFAULT_SCOPES[:count])


def _resolve_key_id(payload: dict, dig: str) -> str:
    """Coherence: an explicit ``key_id`` must have the shape create_api_key
    returns (api<10 hex>); a fabricated one is rejected. Absent -> derive one."""
    raw = payload.get("key_id")
    if raw is None:
        return ref(_KEY_PREFIX, dig)
    text = str(raw)
    suffix = text[len(_KEY_PREFIX) :]
    ok = text.startswith(_KEY_PREFIX) and len(suffix) == 10
    if ok:
        try:
            int(suffix, 16)
        except ValueError:
            ok = False
    if not ok:
        raise LabActionError(422, f"unknown api key {text!r}")
    return text


def _email_field(payload: dict, dig: str) -> str:
    """Validated email: reject a present-but-malformed address (422); derive one
    when absent."""
    if "email" in payload and str(payload["email"]).strip():
        email = str(payload["email"])
        if not valid_email(email):
            raise LabActionError(422, f"invalid email {email!r}")
        return email
    return _email("external", dig)


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a realistic deterministic response, ``None`` for an unknown action,
    or raise ``LabActionError`` for a known action with invalid input."""
    if action_type not in _KNOWN_ACTIONS:
        return None
    dig = digest(_DOMAIN, action_type, resource, payload)
    base = envelope(action_type, resource, dig)
    uid = _user_id(resource, dig)

    if action_type == "read_user_profile":
        return {
            **base,
            "status": "ok",
            "user": {
                "id": uid,
                "login": resource,
                "email": _email(resource, dig),
                "status": "ACTIVE",
                "groups": ["Everyone", pick(dig, ("Engineering", "Finance", "Sales", "IT"))],
            },
        }
    if action_type == "suspend_user":
        return {**base, "status": "SUSPENDED", "user_id": uid, "login": resource}
    if action_type == "delete_user":
        return {**base, "status": "DEPROVISIONED", "user_id": uid, "login": resource}
    if action_type == "reset_password":
        return {
            **base,
            "status": "RECOVERY",
            "user_id": uid,
            "recovery_token_id": ref("rec_", dig),
            "delivery": "EMAIL",
        }
    if action_type == "modify_user_roles":
        return {**base, "status": "updated", "user_id": uid, "roles": _roles(payload, dig)}
    if action_type == "add_user_to_admin_group":
        return {
            **base,
            "status": "added",
            "user_id": uid,
            "group": "Administrators",
            "membership": "ACTIVE",
        }
    if action_type == "create_api_key":
        return {
            **base,
            "status": "ACTIVE",
            "key_id": ref(_KEY_PREFIX, dig),
            "name": str(payload.get("name") or resource or "service-key"),
        }
    if action_type == "revoke_api_key":
        return {**base, "status": "REVOKED", "key_id": _resolve_key_id(payload, dig)}
    if action_type == "generate_long_lived_token":
        return {
            **base,
            "status": "ACTIVE",
            "token_id": ref("tok_", dig),
            "ttl_days": 365,
            "scope": "full_access",
        }
    if action_type == "modify_mfa_policy":
        return {
            **base,
            "status": "updated",
            "policy_id": ref("mfp_", dig),
            "required_factors": [_MFA_FACTORS[0], pick(dig, _MFA_FACTORS, offset=4)],
        }
    if action_type == "disable_sso":
        return {**base, "status": "disabled", "idp": resource or "company-saml"}
    if action_type == "add_oauth_app":
        return {
            **base,
            "status": "registered",
            "client_id": ref(_APP_PREFIX, dig),
            "app_name": str(payload.get("name") or resource or "oauth-app"),
            "redirect_uris": [str(payload.get("redirect_uri") or "https://app.example.test/cb")],
        }
    if action_type == "modify_oauth_scopes":
        return {
            **base,
            "status": "updated",
            "client_id": resource or ref(_APP_PREFIX, dig),
            "scopes": _scopes(payload, dig),
        }
    if action_type == "revoke_long_lived_token":
        return {**base, "status": "REVOKED", "token_id": ref("tok_", dig)}
    if action_type == "revoke_token":
        return {**base, "status": "REVOKED", "token_id": ref("tok_", dig)}
    if action_type == "assume_delegation":
        return {
            **base,
            "status": "delegated",
            "principal": resource or "agent:unknown",
            "delegation_id": ref("dlg_", dig),
        }
    # invite_external_user
    return {
        **base,
        "status": "PENDING",
        "invitation_id": ref("inv_", dig),
        "email": _email_field(payload, dig),
    }
