"""cloud mock handler -- W8 Cloud / infrastructure (13 actions).

A realistic deterministic double of a cloud-infra API. Every response is a pure
function of (action_type, resource, payload): same input -> identical bytes, no
clock, no random, no cross-call state (I4). See ``_realism`` for the shared
primitives and the validation contract.

Realism: infra objects per action (resource inventory, deleted database/bucket/
pod, public ACL, security-group changes, opened port, deployment, KMS key
scheduled-for-deletion, IAM change). Validation -> 422: open_sensitive_port
rejects an out-of-range port.
"""

from __future__ import annotations

from . import _entities
from ._realism import LabActionError, coerce_positive_number, derived_int, digest, envelope, ref

_DOMAIN = "cloud"
_DISCOVERY_RESOURCES = frozenset(("", "all", "*"))


def _reject_if_terminated(resource: _entities.CloudResource, action: str) -> None:
    if resource.terminated:
        raise LabActionError(
            422,
            f"resource {resource.resource_id!r} is terminated; cannot {action}",
            code="instance_terminated",
            detail={"resource_id": resource.resource_id, "state": "terminated"},
        )


_KNOWN_ACTIONS = frozenset(
    (
        "read_resource_inventory",
        "delete_database",
        "delete_s3_bucket",
        "make_bucket_public",
        "modify_security_group",
        "open_sensitive_port",
        "delete_backups",
        "modify_k8s_config",
        "delete_critical_pod",
        "deploy_unvalidated_image",
        "modify_env_variable",
        "delete_kms_key",
        "modify_cloud_iam",
        "isolate_host",
    )
)


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a realistic deterministic response, ``None`` for an unknown action,
    or raise ``LabActionError`` for a known action with invalid input."""
    if action_type not in _KNOWN_ACTIONS:
        return None
    dig = digest(_DOMAIN, action_type, resource, payload)
    base = envelope(action_type, resource, dig)

    if action_type == "read_resource_inventory":
        if resource in _DISCOVERY_RESOURCES:
            return {
                **base,
                "status": "ok",
                "resources_list": [
                    _entities.derive_cloud_resource(rid).summary()
                    for rid in _entities.SEED_CLOUD_RESOURCES
                ],
            }
        return {
            **base,
            "status": "ok",
            "region": "eu-west-1",
            "resources": {
                "ec2": derived_int(dig, 0, 500),
                "s3": derived_int(dig, 0, 200, offset=4),
                "rds": derived_int(dig, 0, 50, offset=8),
            },
        }
    if action_type == "delete_database":
        res = _entities.derive_cloud_resource(resource)
        _reject_if_terminated(res, "delete database")
        return {**base, "status": "deleted", "database": res.resource_id, "deleted": True}
    if action_type == "delete_s3_bucket":
        res = _entities.derive_cloud_resource(resource)
        _reject_if_terminated(res, "delete bucket")
        return {**base, "status": "deleted", "bucket": res.resource_id, "deleted": True}
    if action_type == "make_bucket_public":
        res = _entities.derive_cloud_resource(resource)
        return {
            **base,
            "status": "updated",
            "bucket": res.resource_id,
            "region": res.region,
            "acl": "public-read",
        }
    if action_type == "modify_security_group":
        res = _entities.derive_cloud_resource(resource)
        _reject_if_terminated(res, "modify security group")
        return {
            **base,
            "status": "updated",
            "security_group": res.resource_id,
            "region": res.region,
            "rules_changed": derived_int(dig, 1, 40),
        }
    if action_type == "open_sensitive_port":
        port = derived_int(dig, 1, 65535)
        if "port" in payload:
            value = coerce_positive_number(payload["port"])
            if value is None or value > 65535:
                raise LabActionError(
                    422,
                    f"invalid port {payload['port']!r}",
                    code="invalid_port",
                    detail={"field": "port", "got": payload["port"]},
                )
            port = int(value)
        return {**base, "status": "opened", "security_group": resource, "port": port}
    if action_type == "delete_backups":
        return {
            **base,
            "status": "deleted",
            "scope": resource,
            "deleted_count": derived_int(dig, 1, 5000),
        }
    if action_type == "modify_k8s_config":
        return {**base, "status": "updated", "cluster": resource}
    if action_type == "delete_critical_pod":
        res = _entities.derive_cloud_resource(resource)
        _reject_if_terminated(res, "delete pod")
        return {**base, "status": "deleted", "pod": res.resource_id, "deleted": True}
    if action_type == "deploy_unvalidated_image":
        return {
            **base,
            "status": "rolled_out",
            "environment": "production",
            "image": str(payload.get("image") or "unverified:latest"),
            "deployment_id": ref("dpl_", dig),
        }
    if action_type == "modify_env_variable":
        return {
            **base,
            "status": "updated",
            "key": str(payload.get("key") or "APP_SECRET"),
            "scope": resource,
        }
    if action_type == "delete_kms_key":
        return {
            **base,
            "status": "scheduled_for_deletion",
            "key_id": ref("key_", dig),
            "pending_window_days": 7,
        }
    if action_type == "isolate_host":
        return {
            **base,
            "status": "isolated",
            "host": resource or "host/unknown",
            "isolation_id": ref("iso_", dig),
        }
    # modify_cloud_iam
    return {
        **base,
        "status": "updated",
        "principal": str(payload.get("principal") or resource),
        "scope": "iam",
    }
