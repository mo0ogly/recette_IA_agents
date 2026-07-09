"""SSE live-capture stream for the wire buffer (GET /proxy/wire/stream).

The stream is a data-light wake-up channel: `cursor` events carry only the
buffer's last_seq; the delta endpoint stays the single data path. The endpoint
generator is unbounded (it ends on client disconnect), so it is driven DIRECTLY
here -- a fake Request whose ``is_disconnected`` flips to True after the first
tick -- rather than through a streaming client that could hang. Deterministic,
no sleep-based flakiness.
"""

import asyncio
import unittest

try:
    from fastapi import FastAPI

    from recette.api.routers import proxy as proxy_router

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False


class _FakeRecorder:
    """Minimal recorder: a mutable last_seq the test controls."""

    def __init__(self) -> None:
        self._seq = 0

    def set_seq(self, value: int) -> None:
        self._seq = value

    def last_seq(self) -> int:
        return self._seq


class _FakeRequest:
    """A Request whose disconnect flips True after ``ticks`` polls."""

    def __init__(self, recorder: _FakeRecorder, ticks: int) -> None:
        self._ticks = ticks
        self.app = FastAPI()
        self.app.state.wire_flow_recorder = recorder

    async def is_disconnected(self) -> bool:
        self._ticks -= 1
        return self._ticks < 0


async def _collect(request: object, limit: int = 10) -> list[str]:
    response = await proxy_router.stream_wire_flows(request)  # type: ignore[arg-type]
    out: list[str] = []
    async for chunk in response.body_iterator:
        out.append(chunk if isinstance(chunk, str) else chunk.decode())
        if len(out) >= limit:
            break
    return out


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class WireStreamTest(unittest.TestCase):
    def test_greets_with_the_current_cursor(self) -> None:
        recorder = _FakeRecorder()
        recorder.set_seq(7)
        # ticks=0 -> the greeting is yielded, then the loop sees disconnect.
        chunks = asyncio.run(_collect(_FakeRequest(recorder, ticks=0)))
        joined = "".join(chunks)
        self.assertIn("event: cursor", joined)
        self.assertIn('"last_seq": 7', joined)

    def test_emits_a_new_cursor_when_the_buffer_grows(self) -> None:
        recorder = _FakeRecorder()
        recorder.set_seq(1)
        request = _FakeRequest(recorder, ticks=2)

        async def run() -> list[str]:
            response = await proxy_router.stream_wire_flows(request)  # type: ignore[arg-type]
            it = response.body_iterator.__aiter__()
            first = await it.__anext__()  # greeting cursor = 1
            recorder.set_seq(5)  # a flow lands between polls
            second = await it.__anext__()  # cursor = 5
            return [
                first if isinstance(first, str) else first.decode(),
                second if isinstance(second, str) else second.decode(),
            ]

        first, second = asyncio.run(run())
        self.assertIn('"last_seq": 1', first)
        self.assertIn('"last_seq": 5', second)


if __name__ == "__main__":
    unittest.main()
