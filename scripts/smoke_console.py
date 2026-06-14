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
  4. /live + /flux : a server-less governed campaign's actions stream into the
                  realtime view (/live) and the audit tail (/flux)
  5. /ai-backends: the provider dropdown is fed by the dynamic catalog and the
                   per-backend "Test" probe reaches a terminal status (ok|error)

Requires a RUNNING console (vite) and API, with the console pointed at that
API (VITE_INSPECT_IA_AGENTS_API_URL). Uses the Python Playwright bindings; the
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
AI_BACKEND_ID = "smoke-console-ai"
# A SERVER-LESS governed agent: with no server binding it runs the lab path,
# which is routed through the Gateway (GatewayForge), so its actions are
# policy-evaluated, audited, and streamed to /live and /flux. The server-bound
# agent above stays on the direct ProxyForge (its ephemeral server is not the
# canonical lab the gateway mediates), so it is the wrong subject for that proof.
GOV_AGENT_ID = "smoke-console-gov-bot"
GOV_CAMPAIGN_ID = "smoke-console-gov-camp"
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
        f"/campaigns/{GOV_CAMPAIGN_ID}",
        f"/config/agents/{AGENT_ID}",
        f"/config/agents/{GOV_AGENT_ID}",
        f"/config/servers/{SERVER_ID}",
        f"/config/ai-backends/{AI_BACKEND_ID}",
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
    # Server-less governed agent + its campaign: no `server`, so it runs the
    # gateway-mediated lab path and its actions land in /audit, /flux and /live.
    status, _ = _api(
        "POST",
        f"{api}/config/agents",
        {
            "id": GOV_AGENT_ID,
            "runtime": "lab",
            "ai_mode": "mock",
            "principal": "smoke-gov@acme",
            "target_system": "github",
            "goal": "console smoke: governed lab run visible in /live and /flux",
            "capability_scope": list(ACTIONS),
            "scenario": [
                {"kind": "tool_call", "tool_name": action, "tool_args": {"resource": "acme/x"}}
                for action in ACTIONS
            ]
            + [{"kind": "final", "text": "done"}],
        },
    )
    _expect(status == 201, f"seed governed agent -> {status}")
    status, _ = _api(
        "POST",
        f"{api}/campaigns",
        {
            "id": GOV_CAMPAIGN_ID,
            "description": "console smoke (governed)",
            "steps": [{"agent_id": GOV_AGENT_ID}],
        },
    )
    _expect(status == 201, f"seed governed campaign -> {status}")
    # An AI backend for the IA tab. No key is stored (R8): the probe will
    # either answer (env key present) or fail deterministically (no key) --
    # both are a terminal result, which is what the UI wiring must surface.
    status, _ = _api(
        "POST",
        f"{api}/config/ai-backends",
        {"id": AI_BACKEND_ID, "provider": "groq", "model": "llama-3.3-70b-versatile"},
    )
    _expect(status == 201, f"seed ai_backend -> {status}")


def _drive_ai_backends(page: Page, console: str) -> None:
    # The IA (backends) tab: assert the provider dropdown is fed by the dynamic
    # catalog (GET /config/ai-providers) and that the per-row "Test" button does
    # a real round-trip whose outcome is surfaced in the UI. The probe result is
    # not asserted ok/green: with no stored key it may fail deterministically;
    # what matters is the wiring -- a terminal status (ok OR error), never stuck.
    page.goto(f"{console}/ai-backends", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    options = page.locator("#backend-provider option")
    options.first.wait_for(state="attached", timeout=UI_TIMEOUT_MS)
    count = options.count()
    _expect(count > 5, f"provider dropdown not fed by the catalog (got {count} options)")
    print(f"[ai] /ai-backends: provider dropdown lists {count} providers (dynamic catalog)")
    row = page.locator("tr", has=page.get_by_text(AI_BACKEND_ID, exact=True)).first
    row.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    row.get_by_role("button", name="Test", exact=True).click()
    # Wait until the status dot leaves the untested/testing state for a terminal
    # one. The dot carries data-status in {untested, ok, error}.
    terminal = row.locator(
        '[data-testid="backend-test-status"][data-status="ok"], '
        '[data-testid="backend-test-status"][data-status="error"]'
    )
    terminal.first.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    status = row.get_by_test_id("backend-test-status").get_attribute("data-status")
    _expect(status in ("ok", "error"), f"probe did not reach a terminal status (got {status!r})")
    # The probe outcome is also appended to the "Provider calls" log console.
    page.get_by_text(f"backend {AI_BACKEND_ID}", exact=False).first.wait_for(
        state="visible", timeout=UI_TIMEOUT_MS
    )
    print(f"[ai] /ai-backends: Test -> terminal status {status!r}, logged in Provider calls")


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


def _drive_test(page: Page) -> None:
    # The "Test" verb: fire one action at the running server from the UI and
    # assert it answers like a real server (ok + HTTP 200 in the result panel).
    _server_row(page).get_by_role("button", name="Test", exact=True).click()
    panel = page.get_by_test_id(f"server-test-{SERVER_ID}")
    panel.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    # The dropdown is fed by the live catalog for the system; run the default
    # (first) catalogued action -- the lab handler answers it deterministically.
    combo = panel.get_by_role("combobox")
    combo.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    chosen = combo.input_value()
    _expect(chosen != "", "test panel action dropdown stayed empty (catalog not loaded)")
    panel.get_by_role("button", name="Run test", exact=True).click()
    result = page.get_by_test_id(f"server-test-result-{SERVER_ID}")
    result.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    result.get_by_text("HTTP 200", exact=False).wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    _expect("ok" in (result.inner_text() or ""), "test result panel did not report ok")
    print(f"[2b] /servers: Test {chosen} -> ok HTTP 200 (server answers live)")


def _drive_campaign(page: Page, console: str) -> None:
    page.goto(f"{console}/campaigns", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    # The page is split into tabs; the persisted campaigns live under the
    # "Campagnes" tab (default tab is "Modeles par domaine").
    page.get_by_role("tab", name="Campagnes", exact=True).click()
    row = page.locator("tr", has=page.get_by_text(CAMPAIGN_ID, exact=True)).first
    row.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    row.get_by_role("button", name="Lancer", exact=True).click()
    # The run is fast (server is up); the campaign row status cell flips to
    # "completed" once the SSE stream ends. Poll the page for the terminal word.
    page.get_by_text("completed", exact=False).first.wait_for(
        state="visible", timeout=UI_TIMEOUT_MS
    )
    print("[3/5] /campaigns: Lancer -> completed")


def _drive_dashboard_campaign(page: Page, console: str) -> None:
    # The dashboard "Campagnes" section: launch the SAME campaign from the
    # control board (not the /campaigns page). This drives runCampaign through
    # the GatewayForge path and asserts the row's status voyant reaches
    # "termine" (completed). Server is still up, so the proxied actions succeed.
    page.goto(f"{console}/dashboard", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    table = page.get_by_role("table", name="campagnes")
    table.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    row = table.locator("tr", has=page.get_by_text(CAMPAIGN_ID, exact=True)).first
    row.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    print("[db] /dashboard: campaign row rendered in Campagnes section")
    row.get_by_role("button", name=f"Lancer la campagne {CAMPAIGN_ID}").click()
    # Status voyant flips to "termine" once the run completes (polled every 2s).
    row.get_by_text("termine", exact=True).wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    print("[db] /dashboard: Lancer -> voyant termine (campaign run completed)")


def _verify_live_flux(page: Page, console: str, api: str) -> None:
    # /live (SSE) and /flux (audit tail) both tail FORWARD from the cursor at
    # page load, so open the page FIRST, then fire the governed campaign, then
    # assert its actions appear. The server-less GOV agent runs the gateway-
    # mediated path, so its actions are audited and streamed here.
    #
    # /flux: assert inside the LogConsole (.logc) -- the agent id also appears in
    # the filter dropdown, so scope to the log to avoid matching that hidden
    # <option>. The action text is rendered as "github/<action>".
    page.goto(f"{console}/flux", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    logc = page.locator(".logc")
    logc.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    status, _ = _api("POST", f"{api}/campaigns/{GOV_CAMPAIGN_ID}/run")
    _expect(status == 201, f"run governed campaign for /flux -> {status}")
    logc.get_by_text("github/open_pr", exact=False).first.wait_for(
        state="visible", timeout=UI_TIMEOUT_MS
    )
    print("[live] /flux: governed campaign action 'github/open_pr' visible in the log")

    # /live: an open SSE connection never reaches networkidle; wait for the DOM
    # only, then fire a fresh run and assert a governed row streams in.
    page.goto(f"{console}/live", wait_until="domcontentloaded", timeout=UI_TIMEOUT_MS)
    page.get_by_text("Connecte", exact=False).first.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    status, _ = _api("POST", f"{api}/campaigns/{GOV_CAMPAIGN_ID}/run")
    _expect(status == 201, f"run governed campaign for /live -> {status}")
    page.get_by_test_id("live-row").first.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    cell = page.get_by_role("cell", name=GOV_AGENT_ID, exact=True)
    cell.first.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    print("[live] /live: governed campaign row streamed in (agent cell visible)")


def _verify_recording_and_replay(page: Page, console: str) -> None:
    # The campaign run persisted a recording, the deterministic trace of a
    # campaign (replayable, I4). A governed campaign ALSO lands in the audit
    # store and the /live + /flux views (see _verify_live_flux); this step
    # checks the recording artefact, which replay re-issues deterministically.
    # Replay uses the in-memory LabForge, so the stopped server is fine.
    recording_id = f"{CAMPAIGN_ID}.00.{AGENT_ID}"
    page.goto(f"{console}/campaigns", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    # Recordings live under the "Enregistrements" tab.
    page.get_by_role("tab", name="Enregistrements", exact=True).click()
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
            _drive_test(page)
            _drive_campaign(page, console)
            _drive_dashboard_campaign(page, console)
            _verify_live_flux(page, console, api)
            _stop_server(page, console)
            _verify_recording_and_replay(page, console)
            # Independent of the server lifecycle: the IA tab drives the LLM
            # backend catalog + per-backend probe wiring.
            _drive_ai_backends(page, console)
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
