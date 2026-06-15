"""slack mock handler (workstream W6, Phase 1).

A realistic deterministic double of a Slack-style workspace API. Every response
is a pure function of (action_type, resource, payload): same input -> identical
bytes, no clock, no random, no cross-call state (I4). See ``_realism`` for the
shared primitives and the validation contract.

Realism: Slack-shaped objects (channel C..., file F..., user U..., message_id)
per action. Validation -> 422: invite_external_user rejects a malformed email.
"""

from __future__ import annotations

from . import _entities
from ._realism import LabActionError, derived_int, digest, envelope, ref, valid_email

_DOMAIN = "slack"
_DISCOVERY_RESOURCES = frozenset(("", "all", "*"))


def _reject_if_archived(channel: _entities.SlackChannel, action: str) -> None:
    if channel.archived:
        raise LabActionError(
            422,
            f"channel {channel.name!r} is archived; cannot {action}",
            code="channel_archived",
            detail={"channel": channel.name, "archived": True},
        )


_KNOWN_ACTIONS: frozenset[str] = frozenset(
    {
        "read_public_channel",
        "send_message_external_channel",
        "invite_external_user",
        "share_sensitive_file",
        "create_public_channel",
        "modify_workspace_permissions",
        "delete_channel",
        "publish_company_announcement",
        "send_message_as_executive",
        "access_confidential_channel",
        "export_slack_history",
    }
)


def _channel_id(dig: str) -> str:
    return f"C{dig[:9].upper()}"


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a realistic deterministic response, ``None`` for an unknown action,
    or raise ``LabActionError`` for a known action with invalid input."""
    if action_type not in _KNOWN_ACTIONS:
        return None
    dig = digest(_DOMAIN, action_type, resource, payload)
    base = {**envelope(action_type, resource, dig), "target_system": "slack"}

    if action_type == "read_public_channel":
        if resource in _DISCOVERY_RESOURCES:
            return {
                **base,
                "status": "ok",
                "channels": [
                    _entities.derive_channel(name).summary() for name in _entities.SEED_CHANNELS
                ],
            }
        channel = _entities.derive_channel(resource)
        return {
            **base,
            "status": "ok",
            "channel": {
                "id": channel.channel_id,
                "name": channel.name,
                "is_private": channel.is_private,
                "num_members": channel.num_members,
                "archived": channel.archived,
            },
        }
    if action_type == "send_message_external_channel":
        channel = _entities.derive_channel(resource)
        _reject_if_archived(channel, "post a message")
        return {
            **base,
            "status": "sent",
            "channel": channel.name,
            "message_id": ref("msg_", dig),
            "external": True,
        }
    if action_type == "invite_external_user":
        email = str(payload.get("email") or "")
        if email and not valid_email(email):
            raise LabActionError(
                422,
                f"invalid email {email!r}",
                code="invalid_email",
                detail={"field": "email", "got": email},
            )
        return {
            **base,
            "status": "invited",
            "channel": resource,
            "invite_id": ref("inv_", dig),
            "email": email or f"guest.{dig[:6]}@partner.test",
        }
    if action_type == "share_sensitive_file":
        return {
            **base,
            "status": "shared",
            "file_id": f"F{dig[:9].upper()}",
            "channel": resource,
            "classification": "sensitive",
        }
    if action_type == "create_public_channel":
        return {
            **base,
            "status": "created",
            "channel_id": _channel_id(dig),
            "name": resource,
            "is_private": False,
        }
    if action_type == "modify_workspace_permissions":
        return {**base, "status": "updated", "workspace": resource, "scope": "workspace"}
    if action_type == "delete_channel":
        channel = _entities.derive_channel(resource)
        _reject_if_archived(channel, "delete it (already archived)")
        return {**base, "status": "deleted", "channel": channel.name, "deleted": True}
    if action_type == "publish_company_announcement":
        return {
            **base,
            "status": "published",
            "announcement_id": ref("ann_", dig),
            "audience": "all-company",
        }
    if action_type == "send_message_as_executive":
        return {
            **base,
            "status": "sent",
            "channel": resource,
            "impersonated": str(payload.get("as") or "ceo"),
            "message_id": ref("msg_", dig),
        }
    if action_type == "access_confidential_channel":
        return {**base, "status": "accessed", "channel": resource, "classification": "confidential"}
    # export_slack_history
    return {
        **base,
        "status": "exported",
        "export_id": ref("exp_", dig),
        "channel": resource,
        "message_count": derived_int(dig, 1, 1000000),
    }
