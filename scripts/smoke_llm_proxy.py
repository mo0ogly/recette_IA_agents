#!/usr/bin/env python3
"""Live smoke for the OPTIONAL LiteLLM gateway overlay.

Proves the gateway runs and serves the OpenAI-compatible surface an inspect_ia_agents
``openai_compat`` backend would target:

    [LiteLLM container :4000]  <-- GET /v1/models (master key)  --> model_list

Re-runnable and self-skipping: needs Docker. Without it, SKIPS with a reason --
the deterministic regression lives in the unittest suite (the recette never
calls a real model: StubLlm/ReplayLlm), this is the live wiring proof (R14).
``/v1/models`` only echoes the configured model_list, so the smoke needs no
provider key and makes no upstream model call.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROXY_PORT = 4000
PROXY_URL = f"http://127.0.0.1:{PROXY_PORT}"
MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "sk-recette-local")


def _skip(reason: str) -> None:
    print(f"SKIP smoke_llm_proxy: {reason}")
    sys.exit(0)


def _fail(reason: str) -> None:
    print(f"FAIL smoke_llm_proxy: {reason}")
    sys.exit(1)


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex((host, port)) == 0


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "--profile", "llm", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _get_models() -> dict:
    req = urllib.request.Request(
        f"{PROXY_URL}/v1/models", headers={"Authorization": f"Bearer {MASTER_KEY}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310  # nosec B310
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"_status": exc.code}
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        # App still booting: the port is open but the HTTP server is not ready
        # (connection reset / refused mid-request). Keep polling.
        return {}


def main() -> None:
    if shutil.which("docker") is None:
        _skip("docker not installed")

    print("smoke_llm_proxy: bringing the LiteLLM gateway up (may pull the image)...")
    up = _compose("up", "-d", "llm-proxy")
    if up.returncode != 0:
        _skip(f"could not start llm-proxy (docker): {up.stderr.strip()[:200]}")

    try:
        for _ in range(120):
            if _port_open("127.0.0.1", PROXY_PORT):
                break
            time.sleep(1)
        else:
            _fail("llm-proxy did not bind :4000 in time")

        # Give the app a moment to finish booting after the port opens.
        for _ in range(30):
            body = _get_models()
            ids = [m.get("id") for m in body.get("data", [])]
            if ids:
                print(f"smoke_llm_proxy: PASS -- gateway serves models: {ids}")
                return
            time.sleep(1)
        _fail("gateway did not list any model on /v1/models")
    finally:
        print("smoke_llm_proxy: tearing the gateway down")
        _compose("rm", "-sf", "llm-proxy")


if __name__ == "__main__":
    main()
