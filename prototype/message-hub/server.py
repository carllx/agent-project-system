"""
APS Message Hub - Minimal HTTP + SSE Server.

Features:
- REST endpoints for threads, messages, events
- SSE endpoint `/api/threads/<thread_id>/events/stream` for real-time notification
- Minimal Web UI `/threads/<thread_id>` for visual timeline
- Zero busy-polling requirement
"""

import json
import os
import queue
import threading
import time
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, List, Any

from storage import Storage


HTML_TIMELINE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>APS Message Hub - Thread Timeline</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; margin: 20px; background: #fafafa; color: #222; }
        h1 { font-size: 20px; margin-bottom: 4px; }
        .meta { color: #666; font-size: 13px; margin-bottom: 20px; }
        .section { background: white; border: 1px solid #ddd; border-radius: 6px; padding: 16px; margin-bottom: 20px; }
        h2 { font-size: 16px; margin-top: 0; border-bottom: 1px solid #eee; padding-bottom: 8px; }
        .item { padding: 10px; border-left: 3px solid #ccc; margin-bottom: 10px; background: #f9f9f9; }
        .item.request { border-left-color: #0366d6; }
        .item.response { border-left-color: #28a745; }
        .item.event { border-left-color: #6f42c1; }
        .tag { display: inline-block; padding: 2px 6px; font-size: 11px; font-weight: bold; border-radius: 3px; background: #e1e4e8; }
        .tag.request { background: #cce5ff; color: #004085; }
        .tag.response { background: #d4edda; color: #155724; }
        .tag.event { background: #e2e3e5; color: #383d41; }
        pre { background: #eee; padding: 8px; border-radius: 4px; overflow-x: auto; font-size: 12px; }
    </style>
</head>
<body>
    <h1>APS Message Hub Thread: <span id="thread-id">__THREAD_ID__</span></h1>
    <div class="meta">Server: APS Durable Message Hub PoC | Real-time SSE Connected</div>

    <div class="section">
        <h2>Messages Timeline</h2>
        <div id="messages-container">__MESSAGES_HTML__</div>
    </div>

    <div class="section">
        <h2>Durable Event Log (A2A / NATS style)</h2>
        <div id="events-container">__EVENTS_HTML__</div>
    </div>

    <script>
        const threadId = "__THREAD_ID__";
        const evtSource = new EventSource(`/api/threads/${threadId}/events/stream`);
        evtSource.onmessage = function(e) {
            console.log("SSE Event:", e.data);
            const data = JSON.parse(e.data);
            const container = document.getElementById("events-container");
            const div = document.createElement("div");
            div.className = "item event";
            div.innerHTML = `<span class="tag event">EVENT #${data.event_id}</span> <strong>${data.event_type}</strong> - ${new Date(data.created_at * 1000).toISOString()}<br><small>Msg: ${data.message_id || 'N/A'}</small><pre>${JSON.stringify(data.payload, null, 2)}</pre>`;
            container.appendChild(div);
        };
    </script>
</body>
</html>
"""


class HubServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765, db_path: str = "aps_hub.db"):
        self.host = host
        self.port = port
        self.storage = Storage(db_path)
        self.listeners: Dict[str, List[queue.Queue]] = {}
        self.listeners_lock = threading.Lock()
        self.httpd: Optional[HTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None

    def register_listener(self, thread_id: str) -> queue.Queue:
        with self.listeners_lock:
            q = queue.Queue()
            if thread_id not in self.listeners:
                self.listeners[thread_id] = []
            self.listeners[thread_id].append(q)
            return q

    def unregister_listener(self, thread_id: str, q: queue.Queue) -> None:
        with self.listeners_lock:
            if thread_id in self.listeners:
                if q in self.listeners[thread_id]:
                    self.listeners[thread_id].remove(q)

    def broadcast_event(self, thread_id: str, event: Dict[str, Any]) -> None:
        with self.listeners_lock:
            if thread_id in self.listeners:
                for q in self.listeners[thread_id]:
                    q.put(event)

    def start(self) -> None:
        hub = self

        class RequestHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Keep stderr clean

            def _send_json(self, status: int, data: Any):
                body = json.dumps(data).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def _send_html(self, status: int, html_str: str):
                body = html_str.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path

                # 1. Timeline UI: /threads/<thread_id>
                if path.startswith("/threads/"):
                    thread_id = path[len("/threads/"):]
                    messages = hub.storage.get_messages(thread_id)
                    events = hub.storage.get_events(thread_id)

                    msg_html = ""
                    for m in messages:
                        kind = "request" if m["message_type"] == "review.request" else "response"
                        msg_html += f"""
                        <div class="item {kind}">
                            <span class="tag {kind}">{m['message_type'].upper()}</span>
                            <strong>{m['message_id']}</strong> ({m['sender']} &rarr; {m['recipient']})
                            <br><small>Status: {m['status']} | Artifact: {m['artifact_id'] or 'None'} | Reply-To: {m['reply_to'] or 'None'}</small>
                            <pre>{m['content']}</pre>
                        </div>
                        """
                    if not msg_html:
                        msg_html = "<em>No messages in thread yet.</em>"

                    evt_html = ""
                    for e in events:
                        evt_html += f"""
                        <div class="item event">
                            <span class="tag event">EVENT #{e['event_id']}</span>
                            <strong>{e['event_type']}</strong> (Msg: {e['message_id'] or 'None'})
                            <pre>{json.dumps(e['payload'], indent=2)}</pre>
                        </div>
                        """
                    if not evt_html:
                        evt_html = "<em>No events in thread yet.</em>"

                    rendered = HTML_TIMELINE_TEMPLATE.replace("__THREAD_ID__", thread_id)\
                        .replace("__MESSAGES_HTML__", msg_html)\
                        .replace("__EVENTS_HTML__", evt_html)
                    self._send_html(200, rendered)
                    return

                # 2. SSE Events Stream: /api/threads/<thread_id>/events/stream
                if path.startswith("/api/threads/") and path.endswith("/events/stream"):
                    parts = path.split("/")
                    thread_id = parts[3]
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()

                    # Send initial comment/history if query specifies after_id
                    qs = parse_qs(parsed.query)
                    after_id = int(qs.get("after_id", [0])[0])
                    initial_events = hub.storage.get_events(thread_id, after_id=after_id)
                    for ev in initial_events:
                        self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode("utf-8"))
                        self.wfile.flush()

                    q = hub.register_listener(thread_id)
                    try:
                        while True:
                            try:
                                ev = q.get(timeout=2.0)
                                self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode("utf-8"))
                                self.wfile.flush()
                            except queue.Empty:
                                # Heartbeat ping
                                self.wfile.write(b": ping\n\n")
                                self.wfile.flush()
                    except (ConnectionError, BrokenPipeError):
                        pass
                    finally:
                        hub.unregister_listener(thread_id, q)
                    return

                # 3. GET /api/threads/<thread_id>/messages
                if path.startswith("/api/threads/") and path.endswith("/messages"):
                    thread_id = path.split("/")[3]
                    msgs = hub.storage.get_messages(thread_id)
                    self._send_json(200, {"thread_id": thread_id, "messages": msgs})
                    return

                # 4. GET /api/threads/<thread_id>/events
                if path.startswith("/api/threads/") and path.endswith("/events"):
                    thread_id = path.split("/")[3]
                    qs = parse_qs(parsed.query)
                    after_id = int(qs.get("after_id", [0])[0])
                    evts = hub.storage.get_events(thread_id, after_id=after_id)
                    self._send_json(200, {"thread_id": thread_id, "events": evts})
                    return

                # 5. GET /health
                if path == "/health":
                    self._send_json(200, {"status": "OK"})
                    return

                self._send_json(404, {"error": "Not Found"})

            def do_POST(self):
                parsed = urlparse(self.path)
                path = parsed.path

                # 1. POST /api/threads/<thread_id>/messages
                if path.startswith("/api/threads/") and path.endswith("/messages"):
                    thread_id = path.split("/")[3]
                    length = int(self.headers.get("Content-Length", 0))
                    raw_body = self.rfile.read(length)
                    try:
                        data = json.loads(raw_body.decode("utf-8"))
                    except Exception as e:
                        self._send_json(400, {"error": f"Invalid JSON: {e}"})
                        return

                    required_fields = ["message_id", "sender", "recipient", "message_type", "content"]
                    for field in required_fields:
                        if field not in data:
                            self._send_json(400, {"error": f"Missing required field: {field}"})
                            return

                    try:
                        msg, is_new, ev = hub.storage.create_message(
                            message_id=data["message_id"],
                            thread_id=thread_id,
                            sender=data["sender"],
                            recipient=data["recipient"],
                            message_type=data["message_type"],
                            content=data["content"],
                            reply_to=data.get("reply_to"),
                            artifact_id=data.get("artifact_id"),
                            metadata=data.get("metadata", {}),
                            status=data.get("status", "DELIVERED_TO_HUB")
                        )
                        if is_new and ev:
                            hub.broadcast_event(thread_id, ev)
                        self._send_json(201 if is_new else 200, {
                            "status": "ACK",
                            "is_new": is_new,
                            "message": msg
                        })
                    except ValueError as e:
                        self._send_json(400, {"error": str(e)})
                    except Exception as e:
                        self._send_json(500, {"error": str(e)})
                    return

                # 2. POST /api/threads/<thread_id>/events (Manual event push/status update)
                if path.startswith("/api/threads/") and path.endswith("/events"):
                    thread_id = path.split("/")[3]
                    length = int(self.headers.get("Content-Length", 0))
                    raw_body = self.rfile.read(length)
                    try:
                        data = json.loads(raw_body.decode("utf-8"))
                    except Exception as e:
                        self._send_json(400, {"error": f"Invalid JSON: {e}"})
                        return

                    if "event_type" not in data:
                        self._send_json(400, {"error": "Missing event_type"})
                        return

                    ev = hub.storage.record_event(
                        thread_id=thread_id,
                        event_type=data["event_type"],
                        message_id=data.get("message_id"),
                        payload=data.get("payload", {})
                    )
                    hub.broadcast_event(thread_id, ev)
                    self._send_json(201, {"status": "ACK", "event": ev})
                    return

                self._send_json(404, {"error": "Not Found"})

        self.httpd = ThreadingHTTPServer((self.host, self.port), RequestHandler)
        self._server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._server_thread.start()

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=2.0)
            self._server_thread = None


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    db = sys.argv[2] if len(sys.argv) > 2 else "aps_hub.db"
    server = HubServer(port=port, db_path=db)
    server.start()
    print(f"APS Message Hub running on http://127.0.0.1:{port}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping server...")
        server.stop()
