"""Cloud lab entity: resources (derived from id)."""

from __future__ import annotations

from dataclasses import dataclass

from ._common import _edigest, _pick

__all__ = [
    "CLOUD_KINDS",
    "CLOUD_REGIONS",
    "CLOUD_STATES",
    "SEED_CLOUD_RESOURCES",
    "SEED_TERMINATED_RESOURCES",
    "CloudResource",
    "derive_cloud_resource",
]

CLOUD_STATES = ("running", "stopped")
CLOUD_KINDS = ("ec2", "rds", "s3", "eks", "lambda")
CLOUD_REGIONS = ("eu-west-1", "us-east-1", "ap-south-1")
SEED_CLOUD_RESOURCES = ("cloud/res/db-prod", "cloud/res/bucket-logs", "cloud/res/eks-main")
SEED_TERMINATED_RESOURCES = ("cloud/res/terminated-1",)


@dataclass(frozen=True)
class CloudResource:
    """A cloud resource, fully derived from its id."""

    resource_id: str
    kind: str
    state: str
    region: str

    @property
    def terminated(self) -> bool:
        """A terminated resource is gone; it cannot be modified or deleted."""
        return self.state == "terminated"

    def summary(self) -> dict:
        return {"resource_id": self.resource_id, "kind": self.kind, "state": self.state}


def derive_cloud_resource(resource_id: str) -> CloudResource:
    rid = resource_id or "cloud/res/unknown"
    dig = _edigest("cloud_resource", rid)
    state = "terminated" if rid in SEED_TERMINATED_RESOURCES else _pick(dig, CLOUD_STATES)
    return CloudResource(
        resource_id=rid,
        kind=_pick(dig, CLOUD_KINDS, offset=4),
        state=state,
        region=_pick(dig, CLOUD_REGIONS, offset=8),
    )
