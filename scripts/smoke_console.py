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
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

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
# Screenshots are kept WITH the docs (versioned, not lost in /tmp or the
# gitignored .run/): the smoke regenerates them and they are committed under
# docs/ so the red-team feature has a live, reproducible visual reference.
SCREENSHOT_DIR = Path("docs/screenshots/sim")


class SmokeFailure(AssertionError):
    """One browser assertion failed; the message carries the evidence."""


def _api(method: str, url: str, body: dict | None = None) -> tuple[int, dict | list]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method=method
    )
    try:
        # Smoke-only; URL is built from the trusted local API base
        # (http://127.0.0.1:8090) plus a fixed path, never external/user input.
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310  # nosec B310
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
    # The proxy observability buffers now PERSIST across runs (SQLite store,
    # .run/proxy_traces.db). The smoke's exchange/wire assertions assume a fresh
    # slate, so purge the DEBUG buffers explicitly (documented DELETE semantics;
    # the append-only audit log is untouched, I1).
    _api("DELETE", f"{api}/proxy/traces")
    _api("DELETE", f"{api}/proxy/wire")
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


def _shot(page: Page, name: str) -> None:
    # Full-page screenshot kept WITH the docs (SCREENSHOT_DIR), regenerated on
    # every smoke run so the red-team visual reference never goes stale.
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print(f"[sim] screenshot -> {path}")


def _verify_sim_redteam(page: Page, console: str) -> None:
    # /sim renders the frozen red-team scenarios across tabs: the landing tab is
    # the Scorecard (the CLI mirror), and the per-scenario "caught"/"missed"
    # badges live on the "Sujets MAF" and "Agents Git (Lane B)" tabs, fed live
    # from GET /sim/scenarios + /sim/git-scenarios. This is the feature's
    # browser-to-API proof: capture each tab and assert the known caught MAF
    # scenario rt-diagnostic-overreach shows its badge with the pill-ok class.
    page.goto(f"{console}/sim", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    _shot(page, "sim_scorecard")

    page.get_by_text("Sujets MAF", exact=True).click()
    badges = page.locator('[data-testid^="sim-scn-caught-"]')
    badges.first.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    count = badges.count()
    _expect(count >= 1, f"no red-team anomaly-caught badge rendered on MAF tab (got {count})")
    print(f"[sim] /sim MAF: {count} red-team scenario badge(s) rendered (live from /sim/scenarios)")
    caught = page.get_by_test_id("sim-scn-caught-rt-diagnostic-overreach")
    caught.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    classes = caught.get_attribute("class") or ""
    _expect(
        "sim-caught" in classes,
        f"rt-diagnostic-overreach badge is not sim-caught; class={classes!r}",
    )
    _expect(
        (caught.inner_text() or "").strip() == "attrapee",
        f"rt-diagnostic-overreach badge text is not 'attrapee' (got {caught.inner_text()!r})",
    )
    print("[sim] /sim MAF: rt-diagnostic-overreach shows 'attrapee' badge (anomaly caught)")
    _shot(page, "sim_maf")

    page.get_by_text("Agents Git (Lane B)", exact=True).click()
    git_badges = page.locator('[data-testid^="sim-scn-caught-"]')
    git_badges.first.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    git_count = git_badges.count()
    _expect(git_count >= 1, f"no git red-team badge rendered on Lane B tab (got {git_count})")
    print(f"[sim] /sim Lane B: {git_count} git badge(s) rendered (live from /sim/git-scenarios)")
    _shot(page, "sim_git")


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


def _drive_containment(page: Page, console: str, api: str) -> None:
    # Live wiring of the private-DNS containment toggle: the controlled checkbox
    # on the /servers Configuration tab drives PUT /config/containment. Flip it
    # via the UI, assert the API reflects the flip, then restore the initial
    # state (no lasting side effect). The flag persists to the gitignored runtime
    # sidecar, never the tracked corpus -- guarded by tests/test_config_corpus_clean.
    _, before = _api("GET", f"{api}/config/containment")
    initial = bool(before.get("containment")) if isinstance(before, dict) else False
    page.goto(f"{console}/servers", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    page.get_by_role("tab", name="Configuration", exact=True).click()
    box = page.locator("#containment-toggle")
    box.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    _expect(box.is_checked() == initial, "containment checkbox does not reflect the API on load")

    target = not initial
    box.click()  # controlled checkbox: flips only after the async PUT resolves

    def _api_is(state: bool) -> bool:
        _, body = _api("GET", f"{api}/config/containment")
        return isinstance(body, dict) and bool(body.get("containment")) is state

    page.wait_for_function(
        "(want) => document.getElementById('containment-toggle').checked === want",
        arg=target,
        timeout=UI_TIMEOUT_MS,
    )
    _expect(_api_is(target), f"PUT /config/containment did not persist {target}")
    # Restore the initial state so the smoke leaves no lasting change.
    box.click()
    page.wait_for_function(
        "(want) => document.getElementById('containment-toggle').checked === want",
        arg=initial,
        timeout=UI_TIMEOUT_MS,
    )
    _expect(_api_is(initial), "containment toggle did not restore the initial state")
    print(f"[2c] /servers: containment toggle {initial}->{target}->{initial} via PUT (live)")
    # Leave the page on the list tab so the following steps see the server row.
    page.get_by_role("tab", name="Serveurs", exact=True).click()
    _server_row(page).wait_for(state="visible", timeout=UI_TIMEOUT_MS)


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


def _drive_proxy_launch(page: Page, console: str, api: str) -> None:
    """Proxy console convivable loop: toggle debug ON from the UI, launch a
    key-less mock agent from the in-page launcher, and land on its live session.

    Proves the whole "launch and watch it in the proxy" path in a real browser:
    the debug toggle flips the backend recorder, the launcher runs a lane_b
    agent through the gateway-mediated lab (I5), and its side-effect traces show
    up grouped as that run's session (?source=sessions&run=). The governed
    server-less agent is used, so it needs no running server."""
    # Start from a known debug=off state so the UI toggle deterministically turns
    # recording ON and we can assert the UI -> API wiring.
    _api("POST", f"{api}/proxy/debug", {"enabled": False})
    page.goto(f"{console}/proxy", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    page.get_by_test_id("proxy-debug-toggle").click()
    debug_on = False
    for _ in range(20):
        _, body = _api("GET", f"{api}/proxy/debug")
        if isinstance(body, dict) and body.get("debug_enabled"):
            debug_on = True
            break
        page.wait_for_timeout(250)
    _expect(debug_on, "proxy debug did not turn on from the UI toggle")

    # Launch the server-less governed mock agent from the in-page launcher.
    panel = page.get_by_test_id("proxy-launch-panel")
    panel.get_by_label("agent").select_option(GOV_AGENT_ID)
    panel.get_by_test_id("proxy-launch-btn").click()

    # The page auto-switches to the sessions source preselected on the new run;
    # the run's side effects appear as a session row within the 2s poll.
    page.wait_for_url(re.compile(r"source=sessions"), timeout=UI_TIMEOUT_MS)
    page.get_by_label("sessions").get_by_role("button").first.wait_for(
        state="visible", timeout=UI_TIMEOUT_MS
    )
    _shot(page, "proxy-sessions-launch")
    print("[*] /proxy: debug toggle ON + launcher -> live session")

    # Expert-debug toolkit on the always-available app source (no overlay needed):
    # free-text filter narrows the live trace list, and Pause freezes the poll.
    page.goto(f"{console}/proxy?source=app", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    traces_list = page.get_by_role("list", name="proxy traces")
    traces_list.get_by_role("button").first.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    before = traces_list.get_by_role("button").count()
    page.get_by_test_id("app-filter-text").fill("open_pr")
    # The text filter is a server-side clause: it resets the delta feed and the
    # panel refetches the narrowed rows on its 1s poll. Rows are windowed by
    # VirtualList, but the rendered-button count still drops because the filter
    # shrinks the whole buffer, not just the visible slice.
    page.wait_for_function(
        "(n) => document.querySelectorAll('[aria-label=\"proxy traces\"] button').length < n",
        arg=before,
        timeout=UI_TIMEOUT_MS,
    )
    pause = page.get_by_test_id("proxy-pause")
    pause.click()
    _expect(
        pause.get_attribute("aria-pressed") == "true",
        "Pause button did not flip aria-pressed",
    )
    _shot(page, "proxy-toolkit-filter-pause")
    print("[*] /proxy: app free-text filter narrows + Pause freezes the poll")


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


def _verify_agent_ui(page: Page, console: str) -> None:
    # The creation WIZARD (Identite -> Cible -> ... -> Revue) composes an agent
    # and the Revue step's executing DRY-RUN runs its mock scenario in-memory
    # (no persistence) and shows the action log it would produce. This is the
    # browser-to-API proof of POST /runs/dry-run wired behind the wizard.
    page.goto(f"{console}/agents", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    # Identite step: name the agent.
    page.get_by_role("button", name=re.compile(r"1\. Identite")).click()
    page.get_by_label("Id", exact=True).fill("smoke-wizard-bot")
    page.get_by_label("Principal (identity)", exact=True).fill("bot@smoke")
    # Cible step: scope to the github catalog + a goal (dry-run needs both).
    page.get_by_role("button", name=re.compile(r"2\. Cible")).click()
    page.get_by_label("Target system (en face)", exact=True).select_option("github")
    page.get_by_label("Goal", exact=True).fill("read the smoke repo")
    # Tools step: pick one read action (composes the mock scenario).
    page.get_by_role("button", name=re.compile(r"4\. Tools")).click()
    page.locator("label", has_text="read_repo").get_by_role("checkbox").check()
    # Revue step: execute the dry-run and assert the action log renders.
    page.get_by_role("button", name=re.compile(r"7\. Revue")).click()
    page.get_by_role("button", name=re.compile(r"Tester \(dry-run")).click()
    result = page.get_by_test_id("agents-dryrun-result")
    result.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    _expect("read_repo" in result.inner_text(), "wizard dry-run shows the read_repo action")
    _shot(page, "agent-wizard-dryrun")


def _verify_help_modals(page: Page, console: str) -> None:
    # Every top-level page exposes a "? Aide" modal; /probe and /observability
    # were missing one. Assert each opens, shows its topic, and -- for /probe --
    # uses the renamed "sonde discovery" wording with no legacy "RailNode".
    for path, must_contain in (("/probe", "sonde discovery"), ("/observability", "trace")):
        page.goto(f"{console}{path}", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
        page.get_by_role("button", name=re.compile(r"Aide")).first.click()
        dialog = page.get_by_role("dialog")
        dialog.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
        text = dialog.inner_text()
        _expect(must_contain in text, f"{path} help modal mentions '{must_contain}'")
        _expect("RailNode" not in text, f"{path} help modal is free of legacy 'RailNode'")
        _shot(page, f"help-modal{path.replace('/', '-')}")
        page.get_by_test_id("help-modal-backdrop").click()


def _verify_control(page: Page, console: str) -> None:
    # The Control plane page: the always-visible 3-plane architecture diagram
    # plus the live governance digest (verdict counts) from GET /control/summary.
    page.goto(f"{console}/control", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    # The architecture diagram (Mermaid renders its raw source as a fallback).
    page.get_by_text(re.compile(r"Control plane -- decide")).first.wait_for(
        state="visible", timeout=UI_TIMEOUT_MS
    )
    # The live digest renders from the audit log aggregate.
    digest = page.get_by_test_id("control-summary")
    digest.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    _expect("deny" in digest.inner_text(), "control digest shows verdict cards")
    _shot(page, "control-plane")


def _verify_metrics(page: Page, console: str) -> None:
    # The Metrics page: per-agent / per-tool operational digest over captured
    # traces (GET /metrics/summary). The totals strip is always present.
    page.goto(f"{console}/metrics", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    page.get_by_test_id("metrics-totals").wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    _expect("appel" in page.get_by_test_id("metrics-totals").inner_text(), "metrics totals render")
    _shot(page, "metrics")


def _verify_graph(page: Page, console: str) -> None:
    # The interaction-graph page: pick an orchestration subject (auto-selected),
    # render the directed graph + per-node graph metrics (PageRank etc).
    page.goto(f"{console}/graph", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    page.get_by_test_id("graph-metrics").wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    _expect(
        "pagerank" in page.get_by_test_id("graph-metrics").inner_text().lower(),
        "graph metrics table renders",
    )
    _shot(page, "interaction-graph")


def _verify_registry(page: Page, console: str) -> None:
    # The generated agent registry: one row per corpus subject + metadata.
    page.goto(f"{console}/agent-registry", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    table = page.get_by_test_id("registry-table")
    table.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    _expect("gl-release-bot" in table.inner_text(), "registry lists the seeded subject")
    _shot(page, "agent-registry")


def _verify_receipts(page: Page, console: str, api: str) -> None:
    # The context-receipts page: content-free audit of side effects. After the
    # campaign run above, the proxy recorded traces -> receipts render.
    page.goto(f"{console}/receipts", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    # Either the receipts table or the explicit empty state -- both are valid;
    # assert the page rendered its own content (note text is always present).
    page.get_by_text("Audit sans contenu", exact=False).first.wait_for(
        state="visible", timeout=UI_TIMEOUT_MS
    )
    _shot(page, "context-receipts")

    # Off-platform attestation round-trip, driven through the real UI (R14 live
    # wiring, not /tmp): Export the envelope, then feed that exact file back into
    # the "Verify a third-party export" input and assert the verdict renders. The
    # smoke API has no signing key (fail-safe unsigned), so the signature is
    # reported invalid by design -- the CHAIN verdict is what proves the export
    # <-> verify-import wiring end to end.
    status, payload = _api("GET", f"{api}/proxy/receipts")
    _expect(status == 200, f"GET /proxy/receipts -> {status}")
    receipt_count = len(payload.get("receipts", [])) if isinstance(payload, dict) else 0
    if receipt_count == 0:
        # No side effect was traced this run -> export is disabled by design.
        # The empty-state path is already asserted above; nothing to round-trip.
        return

    export_btn = page.get_by_role("button", name=re.compile(r"Exporter \(signe"))
    export_btn.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    with page.expect_download(timeout=UI_TIMEOUT_MS) as download_info:
        export_btn.click()
    export_path = download_info.value.path()
    _expect(export_path is not None, "export button produced no download")

    page.get_by_test_id("receipts-import-input").set_input_files(str(export_path))
    verdict = page.get_by_test_id("receipts-import-verdict")
    verdict.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    text = verdict.inner_text()
    # The chain of the just-exported receipts is intact -> "Chaine verifiee".
    _expect(
        "Chaine verifiee" in text,
        f"imported-export chain verdict missing (got {text!r})",
    )
    _shot(page, "context-receipts-verify-import")


def _verify_discovery_exchange(page: Page, console: str, api: str) -> None:
    # The Discovery x Echange page: the discovery verdict overlaid on the real
    # exchange. Seed a wire-only flow to a NON-mediated target (no audit event
    # behind it) so the overlay must surface a ghost exchange next to the real
    # (hook) exchanges the campaign above produced.
    status, _ = _api(
        "POST",
        f"{api}/proxy/wire",
        {
            "method": "POST",
            "scheme": "http",
            "host": "evil.smoke.test",
            "port": 443,
            "path": "/leak",
            "status_code": 200,
            "request_body": "{}",
            "response_body": "{}",
        },
    )
    _expect(status in (200, 201), f"seed wire ghost flow -> {status}")
    page.goto(f"{console}/discovery-exchange", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    page.get_by_test_id("exchange-table").wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    # the run-level ghost-exchange signal renders (>=1 -- the seeded wire flow)
    ghost = page.get_by_test_id("dx-ghost-count")
    ghost.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    _expect(
        "echange(s) ghost" in ghost.inner_text(),
        f"ghost-exchange badge missing (got {ghost.inner_text()!r})",
    )
    # at least one exchange row is annotated as a ghost (the wire-only flow)
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('[data-testid=\"exchange-outcome\"]'))"
        ".some(n => n.textContent.trim() === 'ghost')",
        timeout=UI_TIMEOUT_MS,
    )
    # The real launched agents (the campaigns above) now surface: at least one
    # IDENTIFIED hook exchange and at least one DETECTE agent. Proves the full
    # chain from the UX -- launch an agent -> its exchange -> discovery sees it --
    # including the server-less governed path (GatewayForge tracing).
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('[data-testid=\"exchange-outcome\"]'))"
        ".some(n => n.textContent.trim() === 'identifie')",
        timeout=UI_TIMEOUT_MS,
    )
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('[data-testid=\"agent-outcome\"]'))"
        ".some(n => n.textContent.trim() === 'DETECTE')",
        timeout=UI_TIMEOUT_MS,
    )
    _shot(page, "discovery-exchange")
    # Launch a whole CAMPAIGN in process mode from the picker: every step spawns
    # as an OS process captured by PID (live broker) or runs in-process (replay
    # fallback). Either way the UX control must wire end-to-end and report back.
    camp = page.get_by_test_id("dx-camp")
    camp.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    camp.select_option(CAMPAIGN_ID)
    page.get_by_test_id("dx-launch-camp").click()
    msg = page.get_by_test_id("dx-camp-msg")
    msg.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    _expect(
        "campagne" in msg.inner_text().lower(),
        f"campaign launch gave no feedback (got {msg.inner_text()!r})",
    )
    _shot(page, "discovery-exchange-campaign")
    # Named-endpoint assertion (graceful): when the eBPF source is active (broker
    # live), the eBPF column renders per-agent wire endpoints as `wire-agent-<id>`
    # rows whose text carries the resolved `name (host:port)` form. In replay mode
    # (no broker, no live capture) those rows are absent -- tolerate that by
    # skipping rather than failing the smoke.
    wire_agent = page.query_selector('[data-testid^="wire-agent-"]')
    if wire_agent is not None:
        text = wire_agent.inner_text()
        _expect(
            "(" in text,
            f"wire-agent row present but not named (got {text!r})",
        )
    else:
        print("[dx] named wire skipped (replay broker)")
    _shot(page, "discovery-exchange-named-wire")


def _verify_runs_explorer(page: Page, console: str, api: str) -> None:
    """Runs Explorer: seed an eurodated run via the registry, then drive the UI.

    Proves the web-only researcher surface end to end -- the tree renders the
    seeded run, selecting it loads the artifact into Monaco, and the Meta tab
    surfaces the sha256 root_hash (the frozen-evidence proof, I1). This is the
    live runtime gate for the /runs page (the unit render tests cover the
    component; this asserts the browser-to-API wiring in a real Chromium)."""
    repo_root = str(Path(__file__).resolve().parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from recette.runs.registry import RunRegistry

    reg = RunRegistry(Path("docs/tracking/runs"))
    group = reg.new_group(
        category="smoke",
        group_id="smoke-runs",
        eurodate="2026-06-25T00-00-00",
        label="smoke runs-explorer",
    )
    run = reg.new_run(
        group=group,
        run_id="smoke-runs-explorer",
        kind="agent",
        eurodate="2026-06-25T00-00-01",
    )
    reg.write_artifact(run, "agents.jsonl", '{"agent_id":"smoke","ok":true}\n')
    reg.seal(run)

    page.goto(f"{console}/runs", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    page.get_by_test_id("runs-explorer").wait_for(timeout=UI_TIMEOUT_MS)
    node = page.get_by_test_id("run-node-smoke-runs-explorer")
    node.wait_for(timeout=UI_TIMEOUT_MS)
    node.get_by_role("button").first.click()
    page.get_by_test_id("runs-panel-content").wait_for(timeout=UI_TIMEOUT_MS)
    page.get_by_test_id("runs-tab-meta").click()
    root_hash = page.get_by_test_id("meta-root-hash")
    root_hash.wait_for(timeout=UI_TIMEOUT_MS)
    _expect(
        bool(root_hash.inner_text().strip()),
        "runs-explorer: Meta root_hash is empty (seal not surfaced in the UI)",
    )
    # Replay tab: the button spawns a child run (replay_of) -- assert the real
    # /results/{id}/replay response shape ({child_run_id,...}) renders, NOT a
    # RunDetail (the contract drift caught + fixed in PDCA cycle 2).
    page.get_by_test_id("runs-tab-replay").click()
    page.get_by_test_id("replay-btn").click()
    child = page.get_by_test_id("replay-result")
    child.wait_for(timeout=UI_TIMEOUT_MS)
    _expect(
        "replay" in child.inner_text().lower(),
        "runs-explorer: Replay produced no child-run result in the UI",
    )
    _shot(page, "runs-explorer")
    print("[runs] /runs tree + Monaco + Meta root_hash + Replay child-run OK")


def _verify_probe_inventory(page: Page, console: str) -> None:
    """The /probe agent-inventory panel renders the AgentInventory.

    Drives the real console -> GET /probe/inventory. When the Rust engine is
    built the endpoint serves a LIVE scan of the configured agent-source trees
    (badge "LIVE SCAN", real slugs like gh-shadow-agent); otherwise it falls back
    to the committed sample (badge "SAMPLE", which also carries the demo comm
    graph). Asserts the panel mounts, the live/sample badge is present, and the
    three passport BADGES (present / absent / invalid) render -- the discovery
    legibility signal -- then branches its deeper assertion on the mode."""
    page.goto(f"{console}/probe", wait_until="networkidle", timeout=UI_TIMEOUT_MS)
    panel = page.get_by_test_id("inv-panel")
    panel.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    live_badge = page.get_by_test_id("inv-live-badge")
    live_badge.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    mode = live_badge.inner_text().strip().upper()
    _expect(
        mode in ("LIVE SCAN", "SAMPLE"),
        f"probe inventory: unexpected live badge {mode!r}",
    )
    # All three passport states render in both modes.
    for kind in ("present", "absent", "invalid"):
        badge = page.get_by_test_id(f"inv-badge-{kind}")
        badge.first.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
    if mode == "LIVE SCAN":
        # Live scan of corpus/repos: the shadow + invalid subjects read by slug.
        body = panel.inner_text()
        _expect(
            "gh-shadow-agent" in body and "gh-invalid-passport" in body,
            "probe inventory: live scan did not surface the shadow/invalid slugs",
        )
        # Signed-attestation axis (Task 13): the live scan is invoked with
        # --trust/--now, so a signed passport.json resolves to a trusted/untrusted
        # badge. Assert at least one attestation badge rendered. Graceful: an
        # engine without the attestation axis would render none -- degrade with a
        # note rather than hard-fail (the built binary DOES carry the axis).
        attested = (
            page.get_by_test_id("inv-attest-trusted").count()
            + page.get_by_test_id("inv-attest-untrusted").count()
        )
        if attested:
            print(f"[probe] /probe inventory: {attested} signed-attestation badge(s) in LIVE SCAN")
        else:
            print(
                "[probe] /probe inventory: no attestation badge "
                "(engine lacks the signed axis) -- degraded, not failing"
            )
    else:
        # Sample fallback carries the demo comm graph with an undeclared edge.
        undeclared = page.get_by_test_id("inv-edges-undeclared")
        undeclared.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
        _expect(
            "undeclared" in undeclared.inner_text().lower(),
            "probe inventory: undeclared comm edge group not rendered",
        )
    _shot(page, "probe-inventory")
    print(f"[probe] /probe inventory panel: {mode} + present/absent/invalid badges OK")


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
            _drive_containment(page, console, api)
            _drive_test(page)
            _drive_campaign(page, console)
            _drive_dashboard_campaign(page, console)
            _verify_live_flux(page, console, api)
            _stop_server(page, console)
            _verify_recording_and_replay(page, console)
            # Independent of the server lifecycle: the red-team /sim view renders
            # the frozen scenarios' anomaly-caught badges live from the API.
            _verify_sim_redteam(page, console)
            # Independent of the server lifecycle: the IA tab drives the LLM
            # backend catalog + per-backend probe wiring.
            _drive_ai_backends(page, console)
            # The proxy convivable loop: UI debug toggle + in-page launcher ->
            # the launched agent's live session (server-less governed agent).
            _drive_proxy_launch(page, console, api)
            # New agent-creation UX: the wizard + executing dry-run, and the
            # previously-missing help modals on /probe and /observability.
            _verify_agent_ui(page, console)
            _verify_help_modals(page, console)
            # The /probe agent-inventory panel: static-scan passports + comm graph.
            _verify_probe_inventory(page, console)
            # The Control plane page: architecture diagram + live governance digest.
            _verify_control(page, console)
            _verify_metrics(page, console)
            _verify_graph(page, console)
            _verify_registry(page, console)
            _verify_receipts(page, console, api)
            _verify_discovery_exchange(page, console, api)
            # The Runs Explorer: the web-only researcher surface (eurodated
            # registry -> tree -> Monaco -> sha256 root_hash).
            _verify_runs_explorer(page, console, api)
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
