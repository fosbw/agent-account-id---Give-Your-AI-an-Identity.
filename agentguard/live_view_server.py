from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlparse

from .accounts import AccountError
from .live_view import LiveViewHub


_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent Live View</title>
<style>
:root{color-scheme:dark;font-family:Inter,system-ui,sans-serif}body{margin:0;background:#0b1020;color:#e8ecf5}main{max-width:1100px;margin:0 auto;padding:24px}header{display:flex;gap:12px;align-items:center;justify-content:space-between}h1{font-size:24px;margin:0}.controls{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}input,button{border:1px solid #33415f;border-radius:8px;background:#121a2d;color:#e8ecf5;padding:10px}button{cursor:pointer}.grid{display:grid;grid-template-columns:2fr 1fr;gap:16px}.panel{background:#111a2f;border:1px solid #263653;border-radius:12px;padding:16px}.screen{min-height:420px;background:#070b15;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#8290aa}.event{border-bottom:1px solid #263653;padding:10px 0}.badge{display:inline-block;padding:4px 8px;border-radius:999px;background:#1c2e50;margin-right:6px}.muted{color:#8e9bb2;font-size:13px}@media(max-width:800px){.grid{grid-template-columns:1fr}}
</style></head>
<body><main>
<header><h1>Agent Live View</h1><span id="state" class="badge">idle</span></header>
<div class="controls"><input id="session" placeholder="session id" autocomplete="off"><button onclick="loadEvents()">Connect</button><button onclick="control('pause')">Pause</button><button onclick="control('resume')">Resume</button><button onclick="control('kill')">Kill</button></div>
<div class="grid"><section class="panel"><div class="screen" id="screen">Waiting for a session</div></section><section class="panel"><h2>Safe Activity</h2><div id="events" class="muted">No events yet</div></section></div>
<script>
let cursor=0;
function sid(){return encodeURIComponent(document.getElementById('session').value.trim())}
async function loadEvents(){cursor=0;document.getElementById('events').innerHTML='';await poll()}
async function poll(){const id=sid();if(!id)return;const r=await fetch('/api/events?session_id='+id+'&after='+cursor);if(r.ok){const data=await r.json();for(const e of data.events){cursor=Math.max(cursor,e.sequence);render(e)}}setTimeout(poll,800)}
function render(e){document.getElementById('state').textContent=e.state;document.getElementById('screen').textContent=e.frame_ref?'Live frame: '+e.frame_ref:(e.overlay||e.page||e.state);const row=document.createElement('div');row.className='event';row.innerHTML='<span class="badge">'+e.kind+'</span><b>'+e.state+'</b><div class="muted">'+(e.page||'')+' '+(e.overlay||'')+'</div>';document.getElementById('events').prepend(row)}
async function control(action){const id=document.getElementById('session').value.trim();if(!id)return;const r=await fetch('/api/control',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({session_id:id,action})});if(!r.ok)alert(await r.text())}
</script></main></body></html>"""


class LiveViewServer:
    """Local-only HTTP transport for LiveViewHub metadata and controls.

    It serves safe event metadata and opaque frame references. It does not serve
    screenshot bytes, credentials, browser cookies, or provider verification data.
    Bind to 127.0.0.1 by default; expose it only behind an authenticated transport
    that the deployment explicitly provides.
    """

    def __init__(self, hub: LiveViewHub, host: str = "127.0.0.1", port: int = 0):
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("LiveViewServer is local-only")
        self.hub = hub
        self.host = host
        self.port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    def start(self) -> str:
        hub = self.hub

        class Handler(BaseHTTPRequestHandler):
            def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    self._send(HTTPStatus.OK, _HTML.encode(), "text/html; charset=utf-8")
                    return
                if parsed.path == "/health":
                    self._send(HTTPStatus.OK, b'{"ok":true}')
                    return
                if parsed.path == "/api/events":
                    query = parse_qs(parsed.query)
                    session_id = query.get("session_id", [""])[0]
                    try:
                        after = int(query.get("after", ["0"])[0])
                        events = [event.to_dict() for event in hub.events(session_id, after)]
                    except (AccountError, ValueError) as exc:
                        self._send(HTTPStatus.BAD_REQUEST, json.dumps({"error": str(exc)}).encode())
                        return
                    self._send(HTTPStatus.OK, json.dumps({"events": events}).encode())
                    return
                self._send(HTTPStatus.NOT_FOUND, b'{"error":"not found"}')

            def do_POST(self) -> None:  # noqa: N802
                if urlparse(self.path).path != "/api/control":
                    self._send(HTTPStatus.NOT_FOUND, b'{"error":"not found"}')
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    event = hub.control(payload["session_id"], payload["action"])
                except (AccountError, KeyError, ValueError, json.JSONDecodeError) as exc:
                    self._send(HTTPStatus.BAD_REQUEST, json.dumps({"error": str(exc)}).encode())
                    return
                self._send(HTTPStatus.OK, json.dumps(event.to_dict()).encode())

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.port = self._server.server_address[1]
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return f"http://{self.host}:{self.port}/"

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        self._thread = None
