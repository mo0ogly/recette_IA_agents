"""Discovery-recette campaigns + replayable recordings.

A campaign is a persisted, ordered set of Lane B agent launches the discovery
team runs on demand. Running one streams live frames over the existing run
WebSocket (GET /runs/{id}/ws) and persists one recording per step; a recording
can later be replayed deterministically (I4).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from ..campaign_store import UnknownCampaignError, UnknownRecordingError
from ..campaign_templates import get_template, instantiate, list_templates
from ..runners import make_campaign_runner, make_replay_runner

router = APIRouter(tags=["campaigns"])


def _campaigns(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.campaign_store


def _recordings(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.recording_store


@router.get("/campaigns")
def list_campaigns(request: Request) -> dict:
    return {"campaigns": _campaigns(request).list()}


@router.get("/campaign-templates")
def campaign_templates() -> dict:
    """Predefined campaign templates, named by agent profile + usage."""
    return {"templates": list_templates()}


@router.post("/campaign-templates/{template_id}/instantiate", status_code=201)
def instantiate_template(request: Request, template_id: str) -> dict:
    template = get_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="no such template")
    try:
        return instantiate(template, request.app.state.config_store, _campaigns(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/campaigns", status_code=201)
def create_campaign(request: Request, campaign: dict[str, Any]) -> dict:
    try:
        return _campaigns(request).add(campaign)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/campaigns/{campaign_id}")
def get_campaign(request: Request, campaign_id: str) -> dict:
    campaign = _campaigns(request).get(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="no such campaign")
    return campaign


@router.delete("/campaigns/{campaign_id}", status_code=204)
def delete_campaign(request: Request, campaign_id: str) -> Response:
    try:
        _campaigns(request).delete(campaign_id)
    except UnknownCampaignError as exc:
        raise HTTPException(status_code=404, detail="no such campaign") from exc
    return Response(status_code=204)


@router.post("/campaigns/{campaign_id}/run", status_code=201)
def run_campaign(request: Request, campaign_id: str) -> dict:
    campaign = _campaigns(request).get(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="no such campaign")
    mgr = request.app.state.run_manager
    runner = make_campaign_runner(
        campaign, request.app.state.config_store, _recordings(request)
    )
    run = mgr.create("campaign", {"campaign_id": campaign_id})
    mgr.start(run, runner)
    return {"run_id": run.id, "status": run.status}


@router.get("/recordings")
def list_recordings(request: Request) -> dict:
    return {"recordings": _recordings(request).list()}


@router.get("/recordings/{recording_id}")
def get_recording(request: Request, recording_id: str) -> dict:
    try:
        return _recordings(request).get(recording_id).to_dict()
    except (UnknownRecordingError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="no such recording") from exc


@router.post("/recordings/{recording_id}/replay", status_code=201)
def replay_recording(request: Request, recording_id: str) -> dict:
    try:
        recording = _recordings(request).get(recording_id)
    except (UnknownRecordingError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="no such recording") from exc
    mgr = request.app.state.run_manager
    run = mgr.create("replay", {"recording_id": recording_id})
    mgr.start(run, make_replay_runner(recording, recording_id))
    return {"run_id": run.id, "status": run.status}
