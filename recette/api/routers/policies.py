"""A1: policy version endpoints over the append-only PolicyStore (I1).

Documents are immutable once published: re-posting an existing version is a
409, switching the active version only moves the pointer.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ...platform.policy.model import PolicyVersion
from ...platform.policy.store import PolicyStore, UnknownPolicyVersionError

router = APIRouter(prefix="/policies", tags=["policies"])


def _store(request: Request) -> PolicyStore:
    store: PolicyStore = request.app.state.policy_store
    return store


@router.get("")
def list_policies(request: Request) -> dict:
    store = _store(request)
    return {"versions": store.list_versions(), "active": store.active_version_id()}


@router.get("/active")
def get_active_policy(request: Request) -> dict:
    store = _store(request)
    version = store.active_version_id()
    if version is None:
        raise HTTPException(status_code=404, detail="no active policy version")
    return store.get(version).to_dict()


@router.put("/active")
def set_active_policy(request: Request, body: dict[str, Any]) -> dict:
    version = body.get("version")
    if not isinstance(version, str) or not version:
        raise HTTPException(status_code=400, detail="body must contain a non-empty 'version'")
    try:
        _store(request).set_active(version)
    except UnknownPolicyVersionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"active": version}


@router.get("/{version}")
def get_policy(request: Request, version: str) -> dict:
    try:
        return _store(request).get(version).to_dict()
    except UnknownPolicyVersionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", status_code=201)
def publish_policy(request: Request, body: dict[str, Any]) -> dict:
    try:
        policy = PolicyVersion.from_dict(body)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"malformed policy document: {exc}") from exc
    try:
        return _store(request).publish(policy).to_dict()
    except ValueError as exc:
        # PolicyStore raises ValueError mentioning "immutable" on version collision.
        if "immutable" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
