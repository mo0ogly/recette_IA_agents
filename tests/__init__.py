"""Test-suite package initializer.

Pins the proxy debug store to ``:memory:`` for the WHOLE suite: dozens of API
tests call ``create_app()`` bare, and the production default
(``.run/proxy_traces.db``) must never be created by a test run (no repo-state
pollution). Set unconditionally so an operator env value cannot leak a file
write into the suite either. A test that needs a file-backed store passes an
explicit path (``create_app(proxy_db_path=...)`` / ``SqliteProxyStore(path)``).
"""

import os

os.environ["INSPECT_IA_AGENTS_PROXY_DB"] = ":memory:"
