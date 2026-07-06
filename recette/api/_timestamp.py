"""Shared I4 boundary clock capture.

The wall clock is read exactly once at an API boundary and passed downstream as
a captured INPUT; the decision/replay path never reads the host clock (I4). Both
POST /actions/execute and POST /runs (the admission gate) capture ``now`` here so
there is a single, tested capture primitive (DRY).
"""

from __future__ import annotations

import datetime as _dt


def capture_timestamp() -> str:
    """I4 capture point: ISO-8601 UTC with a ``Z`` suffix, captured at the boundary."""
    return _dt.datetime.now(_dt.UTC).isoformat().replace("+00:00", "Z")
