"""The panel's server (ADR-0027): FastAPI, one static page, frames pushed to the browser.

Transport: Server-Sent Events (`GET /api/stream`, the browser's EventSource) for frames, and
`POST /api/ack` for acknowledging alerts. ADR-0010 named a websocket, but uvicorn serves a
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
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from pnt.dashboard.feed import Feed, frames, paced
from pnt.dashboard.health import HealthMonitor

WEB = Path(__file__).parent / "web"
# On a stream with no new frame for this long the server sends a `quiet` event: how long since the
# last frame, on the server's clock. It keeps the connection open, and on a live feed it is how the
# page tells a stopped stream from a steady one (s)
QUIET_EVERY_S = 1.0
# Host names that always mean this machine. `--host` adds its own; a wildcard bind allows any.
LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})
WILDCARD = frozenset({"0.0.0.0", "::"})


def _sse(event: str, data) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, allow_nan=False)}\n\n".encode()


def same_site(origin: str | None, host: str | None, bind_host: str) -> bool:
    """Whether a request that changes state may be from the panel's own page.

    Any web page can POST to localhost without a CORS preflight, but its browser names the page
    in `Origin`, which must then match `Host` (a client with no `Origin` is no browser, so no page
    is abusing it). `Host` must also be a name of this server: with DNS rebinding a hostile name
    resolves here, and `Origin` and `Host` agree. A wildcard bind cannot know its own names, so
    only the `Origin` check applies there."""
    try:
        name = urlsplit(f"//{host}").hostname
        origin_host = None if origin is None else urlsplit(origin).netloc
    except ValueError:
        return False
    if not host or (bind_host not in WILDCARD and name not in LOOPBACK | {bind_host.lower()}):
        return False
    return origin is None or origin_host.lower() == host.lower()


def _point(f: dict) -> list:
    """A frame in the compact form the history keeps: enough to redraw tracks and charts."""
    truth = f["truth"] or [None, None]
    clock_err = None
    if f["truth_clock_s"] is not None and f["clock_sigma_s"] is not None:
        clock_err = abs(f["clock_bias_s"] - f["truth_clock_s"])
    return [
        f["t_s"], f["pos"][0], f["pos"][1], truth[0], truth[1],
        f["hpl_m"], f["health"]["tpl_s"], f["status"], f["err_h_m"], clock_err,
        f["confidence"],
    ]  # fmt: skip


class Hub:
    """Frames from the producer thread, fanned out to every connected browser."""

    def __init__(self, info: dict):
        self.info = info
        self.history: list[list] = []
        self.emitters: list[dict] = []
        self.latest: dict | None = None
        self.latest_mono: float | None = None  # when `latest` arrived (time.monotonic)
        self.done = False
        self.error: str | None = None
        self.clients: set[asyncio.Queue] = set()

    def publish(self, event: str, data) -> None:
        """Called on the event loop's thread."""
        if event == "frame":
            self.emitters += data["new_emitters"]
            self.history.append(_point(data))
            self.latest = data
            self.latest_mono = time.monotonic()
        elif event == "end":
            self.done = True
        elif event == "error":
            self.error = data["message"]
        for q in self.clients:
            q.put_nowait((event, data))

    def quiet(self) -> dict:
        """Seconds since the last frame arrived (None before the first)."""
        if self.latest_mono is None:
            return {"s": None}
        return {"s": round(time.monotonic() - self.latest_mono, 1)}

    def snapshot(self) -> list[tuple[str, object]]:
        out = [("info", self.info), ("emitters", self.emitters), ("history", self.history)]
        if self.latest is not None:
            out.append(("frame", {**self.latest, "new_emitters": []}))
            out.append(("quiet", self.quiet()))  # a page that loads late sees the frame's age
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
    host: str = "127.0.0.1",
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
                        event, data = await asyncio.wait_for(q.get(), QUIET_EVERY_S)
                    except TimeoutError:
                        yield _sse("quiet", hub.quiet())
                        continue
                    yield _sse(event, data)
            finally:
                hub.clients.discard(q)

        headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        return StreamingResponse(events(), media_type="text/event-stream", headers=headers)

    @app.post("/api/ack")
    async def ack(request: Request, body: dict | None = None) -> dict:
        """Acknowledge one latched alert ({"id": n}) or all of them ({})."""
        if not same_site(request.headers.get("origin"), request.headers.get("host"), host):
            raise HTTPException(403, "cross-site request refused")
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
