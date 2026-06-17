"""Slack lab entity: channels (derived from id/name)."""

from __future__ import annotations

from dataclasses import dataclass

from ._common import _edigest, _int

__all__ = [
    "SEED_ARCHIVED_CHANNELS",
    "SEED_CHANNELS",
    "SlackChannel",
    "derive_channel",
]

SEED_CHANNELS = ("slack/channel/general", "slack/channel/random", "slack/channel/eng")
SEED_ARCHIVED_CHANNELS = ("slack/channel/archived-1",)


@dataclass(frozen=True)
class SlackChannel:
    """A Slack channel, fully derived from its id/name."""

    channel_id: str
    name: str
    is_private: bool
    num_members: int
    archived: bool

    def summary(self) -> dict:
        return {"channel_id": self.channel_id, "name": self.name, "archived": self.archived}


def derive_channel(name: str) -> SlackChannel:
    ch = name or "slack/channel/unknown"
    dig = _edigest("slack_channel", ch)
    return SlackChannel(
        channel_id=f"C{dig[:9].upper()}",
        name=ch,
        is_private=False,
        num_members=_int(dig, 1, 5000),
        archived=ch in SEED_ARCHIVED_CHANNELS,
    )
