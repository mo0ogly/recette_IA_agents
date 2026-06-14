"""Lab handler error protocol.

A domain handler returns a dict for a successful (simulated) side effect and
``None`` for an unknown action (mapped to HTTP 404 by the mock server). A third
outcome is needed for realistic doubles: a KNOWN action called with INVALID
input (a negative amount, a malformed IBAN, an unknown payee reference). The
handler signals it by raising ``LabActionError`` with the HTTP status the real
system would return; the mock server maps it to that status + an error
envelope.

The error is a pure function of the inputs (no clock, no random, no state), so
replay stays byte-identical (I4): the same invalid call always raises the same
status and message.
"""

from __future__ import annotations


class LabActionError(Exception):
    """A known lab action rejected its input, like the real system would.

    ``status_code`` is the HTTP status the mock server returns (4xx); the
    message is surfaced in the error envelope. Deterministic by construction.
    """

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
