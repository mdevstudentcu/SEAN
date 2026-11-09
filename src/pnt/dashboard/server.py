"""The panel's server (ADR-0010): FastAPI, one static page, frames pushed to the browser.

Transport: Server-Sent Events (`GET /api/stream`, the browser's EventSource) for frames, and
`POST /api/ack` for acknowledging alerts. ADR-0010 names a websocket, but uvicorn serves a
websocket only with the `websockets` or `wsproto` package, and neither is in uv.lock; SSE needs
nothing beyond fastapi and uvicorn. The frames are the same either way (`pnt.dashboard.feed`).

One producer thread runs the feed once and every browser shares it: a browser that connects
late (or reloads) gets the history so far, then the live frames. Alerts are latched on the
server, so an acknowledgement shows on every screen.
"""

from __future__ import annotations

import asyncio
import json
import math
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from pnt.dashboard.feed import Feed, frames, paced
from pnt.dashboard.health import HealthMonitor

WEB = Path(__file__).parent / "web"
# Keep-alive comment on a quiet stream, so proxies and the browser keep it open (s)
KEEPALIVE_S = 15.0


def _sse(event: str, data) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, allow_nan=False)}\n\n".encode()


def _point(f: dict) -> list:
    """A frame in the compact form the history keeps: enough to redraw tracks and charts."""
    truth = f["truth"] or [None, None]
    clock_err = None
    if f["truth_clock_s"] is not None and f["clock_sigma_s"] is not None:
        clock_err = abs(f["clock_bias_s"] - f["truth_clock_s"])
    return [
        f["t_s"], f["pos"][0], f["pos"][1], truth[0], truth[1],
        f["hpl_m"], f["health"]["tpl_s"], f["status"], f["err_h_m"], clock_err,
    ]  # fmt: skip


class Hub:
    """Frames from the producer thread, fanned out to every connected browser."""

    def __init__(self, info: dict):
        self.info = info
        self.history: list[list] = []
        self.emitters: list[dict] = []
        self.latest: dict | None = None
        self.done = False
        self.error: str | None = None
        self.clients: set[asyncio.Queue] = set()

    def publish(self, event: str, data) -> None:
        """Called on the event loop's thread."""
        if event == "frame":
            self.emitters += data["new_emitters"]
            self.history.append(_point(data))
            self.latest = data
        elif event == "end":
            self.done = True
        elif event == "error":
            self.error = data["message"]
        for q in self.clients:
            q.put_nowait((event, data))

    def snapshot(self) -> list[tuple[str, object]]:
        out = [("info", self.info), ("emitters", self.emitters), ("history", self.history)]
        if self.latest is not None:
            out.append(("frame", {**self.latest, "new_emitters": []}))
        if self.error is not None:
            out.append(("error", {"message": self.error}))
        if self.done:
            out.append(("end", {}))
        return out


def create_app(
    feed: Feed,
    speed: float = 1.0,
    alert_limit_m: float = 50.0,
    time_alert_limit_s: float = 1.5e-6,
    max_rate_hz: float = 10.0,
) -> FastAPI:
    shown_speed = speed if math.isfinite(speed) else None  # JSON has no infinity
    hub = Hub({**feed.info(alert_limit_m, time_alert_limit_s), "speed": shown_speed})
    monitor = HealthMonitor(alert_limit_m, time_alert_limit_s)
    lock = threading.Lock()
    stop = threading.Event()

    def produce(loop: asyncio.AbstractEventLoop) -> None:
        try:
            for f in paced(frames(feed, monitor, lock), speed, max_rate_hz, pace=feed.pace):
                if stop.is_set():
                    return
                loop.call_soon_threadsafe(hub.publish, "frame", f)
            loop.call_soon_threadsafe(hub.publish, "end", {})
        except Exception as exc:  # shown on the panel instead of dying silently in a thread
            loop.call_soon_threadsafe(hub.publish, "error", {"message": repr(exc)})
            raise

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        thread = threading.Thread(
            target=produce, args=(asyncio.get_running_loop(),), daemon=True, name="pnt-feed"
        )
        thread.start()
        yield
        stop.set()

    app = FastAPI(title="pnt dashboard", lifespan=lifespan)
    app.state.hub = hub
    app.state.monitor = monitor
    app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEB / "index.html")

    @app.get("/api/info")
    async def info() -> dict:
        return hub.info

    @app.get("/api/stream")
    async def stream(request: Request) -> StreamingResponse:
        q: asyncio.Queue = asyncio.Queue()

        async def events() -> AsyncIterator[bytes]:
            for event, data in hub.snapshot():
                yield _sse(event, data)
            hub.clients.add(q)
            try:
                while not await request.is_disconnected():
                    try:
                        event, data = await asyncio.wait_for(q.get(), KEEPALIVE_S)
                    except TimeoutError:
                        yield b": keep-alive\n\n"
                        continue
                    yield _sse(event, data)
            finally:
                hub.clients.discard(q)

        headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        return StreamingResponse(events(), media_type="text/event-stream", headers=headers)

    @app.post("/api/ack")
    async def ack(body: dict | None = None) -> dict:
        """Acknowledge one latched alert ({"id": n}) or all of them ({})."""
        alert_id = (body or {}).get("id")
        with lock:
            monitor.acknowledge(None if alert_id is None else int(alert_id))
            shown = [a.__dict__.copy() for a in monitor.shown()]
        hub.publish("alerts", shown)
        if hub.latest is not None:
            hub.latest["health"]["alerts"] = shown
        return {"alerts": shown}

    return app


def serve(app: FastAPI, host: str = "127.0.0.1", port: int = 8050) -> None:
    import uvicorn

    print(f"dashboard on http://{host}:{port}  (Ctrl-C to stop)")
    uvicorn.run(app, host=host, port=port, log_level="warning", timeout_graceful_shutdown=1)
