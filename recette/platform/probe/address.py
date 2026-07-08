"""Broker address parsing shared by the broker and the API relay.

The canonical broker endpoint is a Unix socket path (``.run/probe.sock``).
On platforms where CPython does not expose ``socket.AF_UNIX`` (Windows), the
launcher falls back to a loopback TCP endpoint written as ``tcp:HOST:PORT``
(e.g. ``tcp:127.0.0.1:8093``). This module gives both sides ONE parser so the
two forms never drift.

Fail-safe: an unparseable ``tcp:`` value raises ``ValueError`` -- callers turn
that into their own fail-closed error, never a guessed endpoint.
"""

from __future__ import annotations

import socket

_TCP_PREFIX = "tcp:"


def parse_probe_address(value: str) -> tuple[str, object]:
    """Return ``("tcp", (host, port))`` for ``tcp:HOST:PORT``, else ``("unix", path)``.

    Raises ``ValueError`` when a ``tcp:`` form is malformed (missing port,
    non-numeric port).
    """
    if value.startswith(_TCP_PREFIX):
        rest = value[len(_TCP_PREFIX) :]
        host, sep, port_text = rest.rpartition(":")
        if not sep or not host or not port_text.isdigit():
            raise ValueError(f"malformed tcp probe address {value!r} (expected tcp:HOST:PORT)")
        return ("tcp", (host, int(port_text)))
    return ("unix", value)


def create_stream_socket(family_kind: str) -> socket.socket:
    """A stream socket for the parsed family; fail-closed when AF_UNIX is missing.

    Raises ``OSError`` (not ``AttributeError``) when a unix address is requested
    on a platform without ``socket.AF_UNIX``, so callers handle one error type.
    """
    if family_kind == "tcp":
        return socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if not hasattr(socket, "AF_UNIX"):
        raise OSError(
            "AF_UNIX is not supported on this platform; "
            "use a tcp:HOST:PORT probe address instead"
        )
    return socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
