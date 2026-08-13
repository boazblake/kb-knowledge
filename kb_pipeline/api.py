from __future__ import annotations

import json, logging
import secrets
from http.cookies import SimpleCookie
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


class LoopbackSyntheticIdentity:
    """Short-lived local demo identity; external auth remains a port."""
    def __init__(self, identity="reader", tenant="default", ttl_seconds=300):
        self.identity, self.tenant = identity, tenant
        self.token = secrets.token_urlsafe(24)
        self.expires_at = datetime.now(timezone.utc).timestamp() + ttl_seconds

    def valid(self, token):
        return secrets.compare_digest(self.token, token) and datetime.now(timezone.utc).timestamp() < self.expires_at


def _handler(service, tokens, session_token, max_query_chars=512, max_results=100, frontend_root=None):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, body, content_type="application/json", headers=None):
            payload = body if isinstance(body, bytes) else json.dumps(body, default=str, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            for name, value in headers or ():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(payload)

        def _error(self, status, code, message):
            return self._send(status, {"code": code, "message": message, "details": {}, "trace_id": secrets.token_hex(8)})

        def _identity(self):
            value = self.headers.get("Authorization", "")
            if value.startswith("Bearer "):
                return tokens.get(value[7:])
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            session = cookie.get("kb_session")
            return tokens.get(session.value) if session else None

        def do_GET(self):
            path = urlsplit(self.path)
            if path.path == "/v1/health":
                return self._send(200, {"status": "ok"})
            if path.path == "/v1/ready":
                status = service.readiness() if hasattr(service, "readiness") else {"status": "ready"}
                return self._send(200 if status.get("status") == "ready" else 503, status)
            if frontend_root is not None and path.path in {"/", "/index.html", "/app.js", "/styles.css"}:
                name = "index.html" if path.path in {"/", "/index.html"} else path.path[1:]
                file = Path(frontend_root) / name
                if not file.is_file():
                    return self._error(404, "not_found", "route not found")
                types = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
                return self._send(
                    200,
                    file.read_bytes(),
                    types.get(file.suffix, "application/octet-stream"),
                    [("Set-Cookie", f"kb_session={session_token}; HttpOnly; SameSite=Strict; Path=/")],
                )
            identity = self._identity()
            if identity is None:
                return self._error(401, "unauthenticated", "authentication required")
            if path.path == "/v1/status":
                status = service.store.status(); status["health"] = service.health() if hasattr(service, "health") else {}
                return self._send(200, status)
            if path.path == "/v1/search":
                query = parse_qs(path.query, keep_blank_values=True).get("q", [""])[0].strip()
                if not query:
                    return self._error(400, "invalid_query", "q required")
                if len(query) > max_query_chars:
                    return self._error(400, "invalid_query", "q exceeds limit")
                try:
                    hits = service.search(query, identity["identity"], identity["is_admin"])
                    return self._send(200, {"items": [_safe_search_hit(service, h) for h in hits[:max_results]], "complete": True})
                except Exception:
                    return self._error(503, "unavailable", "service unavailable")
            return self._error(404, "not_found", "route not found")

        def log_message(self, format, *args):
            logging.getLogger("kb_pipeline.http").info("http_request", extra={"route": self.path.split("?", 1)[0], "status": args[1] if len(args) > 1 else None})

    return Handler


def _safe_search_hit(service, hit):
    """Public DTO. Explicit allow-list prevents URI/artifact leakage."""
    return {"document_id": hit.document_id, "title": hit.title, "snippet": hit.snippet,
            **service.search_metadata(hit)}


def create_server(service, host="127.0.0.1", port=8080, token=None, *, max_query_chars=512, max_results=100, frontend_root=None):
    token = token or secrets.token_urlsafe(32)
    tokens = {token: {"identity": "reader", "tenant": "default", "is_admin": False}}
    server = ThreadingHTTPServer((host, port), _handler(service, tokens, token, max_query_chars, max_results, frontend_root))
    setattr(server, "runtime_tokens", tokens)
    return server, token
