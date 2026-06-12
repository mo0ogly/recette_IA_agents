"""cloud mock handler -- W8 Cloud / infrastructure (12 actions).

Handlers are pure and deterministic: same input -> identical response bytes
(stable ids derived from sha256 of inputs, no clock, no random -- I4).
"""

from __future__ import annotations

import hashlib
import json

# Action-specific deterministic fields merged into the simulated response.
# Values are constants: same input always produces the same output (I4).
_ACTION_FIELDS: dict[str, dict[str, str]] = {
    "delete_database": {"database_state": "deleted"},
    "delete_s3_bucket": {"bucket_state": "deleted"},
    "make_bucket_public": {"bucket_acl": "public-read"},
    "modify_security_group": {"security_group_state": "updated"},
    "open_sensitive_port": {"port_state": "open"},
    "delete_backups": {"backup_state": "deleted"},
    "modify_k8s_config": {"k8s_config_state": "updated"},
    "delete_critical_pod": {"pod_state": "deleted"},
    "deploy_unvalidated_image": {"deployment_state": "rolled_out"},
    "modify_env_variable": {"env_state": "updated"},
    "delete_kms_key": {"kms_key_state": "scheduled_for_deletion"},
    "modify_cloud_iam": {"iam_state": "updated"},
}


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a deterministic response dict, or None when action is unknown."""
    extra = _ACTION_FIELDS.get(action_type)
    if extra is None:
        return None
    material = f"cloud:{action_type}:{resource}:{json.dumps(payload, sort_keys=True)}"
    result_id = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
    response: dict = {
        "action": action_type,
        "resource": resource,
        "status": "simulated",
        "result_id": result_id,
    }
    response.update(extra)
    return response
