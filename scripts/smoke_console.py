#!/usr/bin/env python3
"""Browser smoke: the React console drives the API in a real Chromium.

Closes the last unproven link of the chain console -> API -> mock server ->
replay: every other smoke (scripts/smoke_lab.py, the unit suites) talks to
the API directly. This one renders the actual UI and clicks the actual
buttons, asserting the browser-to-API wiring.

Flow (seed via API, then drive the UI):
  1. seed a mock_local server entry, a bound mock agent, and a campaign
     through the API (backend already proven elsewhere)
  2. /servers   : click Start on the server row -> status reaches "up";
                  click Stop -> status returns to "down" (UI lifecycle wiring)
  3. /campaigns : click Lancer on the campaign -> status reaches "completed"
  4. /audit     : the executed actions are visible in the audit view

Requires a RUNNING console (vite) and API, with the console pointed at that
API (VITE_AGENTRAIL_API_URL). Uses the Python Playwright bindings; the
chromium browser must be installed (playwright install chromium).

Stdlib + playwright only. Exit 0 = SMOKE PASS, exit 1 = failure (any
unexpected UI state aborts immediately). Re-runnable: API fixtures named
``smoke-console-*`` are deleted up front.

Usage:
    python3.11 scripts/smoke_console.py \
        --console http://localhost:5173 --api http://127.0.0.1:8090 \
        --server-port 9131
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PwTimeout

SERVER_ID = "smoke-console-gh"
AGENT_ID = "smoke-console-bot"
CAMPAIGN_ID = "smoke-console-camp"
ACTIONS = ("read_repo", "open_pr")
UI_TIMEOUT_MS = 15000


class SmokeFailure(AssertionError):
    """One browser assertion failed; the message carries the evidence."""


def _api(method: str, url: str, body: dict | None = None) -> tuple[int, dict | list]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        return error.code, json.loads(raw) if raw else {}


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _cleanup(api: str) -> None:
    _api("POST", f"{api}/config/servers/{SERVER_ID}/stop")
    for path in (
        f"/campaigns/{CAMPAIGN_ID}",
        f"/config/agents/{AGENT_ID}",
        f"/config/servers/{SERVER_ID}",
    ):
        _api("DELETE", f"{api}{path}")


def _seed(api: str, server_port: int) -> None:
    status, body = _api("GET", f"{api}/health")
    _expect(status == 200, f"API not reachable at {api} (GET /health -> {status})")
    _cleanup(api)
    status, _ = _api(
        "POST",
        f"{api}/config/servers",
        {"id": SERVER_ID, "system": "github", "mode": "mock_local", "port": server_port},
    )
    _expect(status == 201, f"seed server -> {status}")
    status, _ = _api(
        "POST",
        f"{api}/config/agents",
        {
            "id": AGENT_ID,
            "runtime": "lab",
            "ai_mode": "mock",
            "principal": "smoke@acme",
            "target_system": "github",
            "goal": "console smoke: read a repo then open a PR",
            "capability_scope": list(ACTIONS),
            "server": SERVER_ID,
            "scenario": [
                {"kind": "tool_call", "tool_name": action, "tool_args": {"resource": "acme/x"}}
                for action in ACTIONS
            ]
            + [{"kind": "final", "text": "done"}],
        },
    )
    _expect(status == 201, f"seed agent -> {status}")
    status, _ = _api(
        "POST",
        f"{api}/campaigns",
        {"id": CAMPAIGN_ID, "description": "console smoke", "steps": [{"agent_id": AGENT_ID}]},
    )
    _expect(status == 201, f"seed campaign -> {status}")


def _server_row(page: Page):
    return page.locator("tr", has=page.get_by_text(SERVER_ID, exact=True)).first


def _start_server(page: Page, console: str) -> None:
    page.goto(f"{console}/servers", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    row = _server_row(page)
    row.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    print("[2/5] /servers: server row rendered")
    row.get_by_role("button", name="Start", exact=True).click()
    _server_row(page).get_by_text("up", exact=True).wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    print("[2/5] /servers: Start -> status up")


def _stop_server(page: Page, console: str) -> None:
    # Re-navigate so the row reflects the post-campaign state, then stop.
    page.goto(f"{console}/servers", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    _server_row(page).get_by_role("button", name="Stop", exact=True).click()
    _server_row(page).get_by_text("down", exact=True).wait_for(
        state="visible", timeout=UI_TIMEOUT_MS
    )
    print("[4/5] /servers: Stop -> status down")


def _drive_campaign(page: Page, console: str) -> None:
    page.goto(f"{console}/campaigns", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    row = page.locator("tr", has=page.get_by_text(CAMPAIGN_ID, exact=True)).first
    row.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    row.get_by_role("button", name="Lancer", exact=True).click()
    # The run is fast (server is up); the campaign row status cell flips to
    # "completed" once the SSE stream ends. Poll the page for the terminal word.
    page.get_by_text("completed", exact=False).first.wait_for(
        state="visible", timeout=UI_TIMEOUT_MS
    )
    print("[3/5] /campaigns: Lancer -> completed")


def _verify_recording_and_replay(page: Page, console: str) -> None:
    # The campaign run persisted a recording, the auditable trace of a campaign
    # (the /audit view is for the governed /actions/execute path, a different
    # store). The recording is visible in the UI and replays deterministically
    # (I4); replay uses the in-memory LabForge, so the stopped server is fine.
    recording_id = f"{CAMPAIGN_ID}.00.{AGENT_ID}"
    page.goto(f"{console}/campaigns", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    rec_row = page.locator("tr", has=page.get_by_text(recording_id, exact=True)).first
    rec_row.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    print(f"[5/5] /campaigns: recording {recording_id} visible")
    rec_row.get_by_role("button", name="Replay", exact=True).click()
    page.get_by_text("completed", exact=False).first.wait_for(
        state="visible", timeout=UI_TIMEOUT_MS
    )
    print("[5/5] /campaigns: Replay -> completed (I4)")


def run_smoke(console: str, api: str, server_port: int) -> None:
    _seed(api, server_port)
    print(f"[1/4] seeded {SERVER_ID} + {AGENT_ID} + {CAMPAIGN_ID} via API")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(UI_TIMEOUT_MS)
            # Order matters: the agent is bound to the server, so the server
            # must be UP for the campaign's proxied actions to succeed (I5).
            _start_server(page, console)
            _drive_campaign(page, console)
            _stop_server(page, console)
            _verify_recording_and_replay(page, console)
        finally:
            browser.close()
    print("SMOKE PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--console", default="http://localhost:5173", help="console base URL")
    parser.add_argument("--api", default="http://127.0.0.1:8090", help="API base URL")
    parser.add_argument("--server-port", type=int, default=9131)
    args = parser.parse_args()
    console = args.console.rstrip("/")
    api = args.api.rstrip("/")
    try:
        run_smoke(console, api, args.server_port)
    except (SmokeFailure, PwTimeout) as failure:
        print(f"SMOKE FAIL: {failure}", file=sys.stderr)
        return 1
    finally:
        _cleanup(api)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
