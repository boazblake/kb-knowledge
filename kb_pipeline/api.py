from __future__ import annotations

import json, logging
import secrets
from typing import Any
from http.cookies import SimpleCookie
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .answer import AnswerError


class LoopbackSyntheticIdentity:
    """Short-lived local demo identity; external auth remains a port."""
    def __init__(self, identity="reader", tenant="default", ttl_seconds=300):
        self.identity, self.tenant = identity, tenant
        self.token = secrets.token_urlsafe(24)
        self.expires_at = datetime.now(timezone.utc).timestamp() + ttl_seconds

    def valid(self, token):
        return secrets.compare_digest(self.token, token) and datetime.now(timezone.utc).timestamp() < self.expires_at

    def principal(self):
        from .security import Principal
        return Principal(self.identity, self.tenant, frozenset({"admin"} if self.identity == "admin" else set()), frozenset({"*"}))


def _handler(service, tokens, session_token, max_query_chars=512, max_results=100, frontend_root=None, max_request_bytes=16 * 1024):
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

        def _authorize_scope(self, principal, query):
            """Bind optional request scope before retrieval/ranking/answering."""
            if not hasattr(principal, "can_read"):
                return True
            values = parse_qs(query, keep_blank_values=True)
            tenant = values.get("tenant", [principal.tenant])[0]
            source = values.get("source", [""])[0]
            if not principal.can_read(tenant, source):
                self._error(403, "forbidden", "tenant or source scope denied")
                return False
            return True

        def _admin_only(self, principal):
            if hasattr(principal, "is_admin") and not principal.is_admin(principal.tenant):
                self._error(403, "forbidden", "admin principal required")
                return False
            return True

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
            if not self._authorize_scope(identity, path.query):
                return
            if path.path == "/v1/status":
                if getattr(self.server, "production", False) and not self._admin_only(identity): return
                status = service.store.status(); status["health"] = service.health() if hasattr(service, "health") else {}
                return self._send(200, status)
            if path.path == "/v1/report":
                try:
                    if getattr(self.server, "production", False) and not self._admin_only(identity): return
                    report = service.report(identity) if getattr(self.server, "production", False) and hasattr(service, "report") else (service.report() if hasattr(service, "report") else _report(service))
                    return self._send(200, report)
                except Exception:
                    return self._error(503, "unavailable", "service unavailable")
            if path.path == "/v1/search":
                query = parse_qs(path.query, keep_blank_values=True).get("q", [""])[0].strip()
                if not query:
                    return self._error(400, "invalid_query", "q required")
                if len(query) > max_query_chars:
                    return self._error(400, "invalid_query", "q exceeds limit")
                try:
                    if hasattr(identity, "subject"):
                        hits = service.search(query, identity)
                    else:
                        hits = service.search(query, identity["identity"], identity["is_admin"])
                    return self._send(200, {"items": [_safe_search_hit(service, h) for h in hits[:max_results]], "complete": True})
                except Exception:
                    return self._error(503, "unavailable", "service unavailable")
            return self._error(404, "not_found", "route not found")

        def do_POST(self):
            path = urlsplit(self.path)
            identity = self._identity()
            if identity is None:
                return self._error(401, "unauthenticated", "authentication required")
            if not self._authorize_scope(identity, path.query):
                return
            if path.path != "/v1/answer":
                return self._error(404, "not_found", "route not found")
            try:
                length = int(self.headers.get("Content-Length", "-1"))
                if length < 0 or length > max_request_bytes:
                    return self._error(413, "request_too_large", "request exceeds limit")
                body = json.loads(self.rfile.read(length))
                query = body["query"] if isinstance(body, dict) else None
                if not isinstance(query, str) or not query.strip() or len(query.strip()) > max_query_chars:
                    return self._error(400, "invalid_query", "bounded query required")
                if hasattr(identity, "subject"):
                    result = service.answer(query.strip(), identity)
                else:
                    result = service.answer(query.strip(), identity["identity"], identity["is_admin"])
                return self._send(200, result)
            except (json.JSONDecodeError, KeyError, TypeError):
                return self._error(400, "invalid_request", "bounded JSON query required")
            except AnswerError:
                return self._error(503, "unavailable", "answer service unavailable")
            except Exception:
                return self._error(503, "unavailable", "answer service unavailable")

        def log_message(self, format, *args):
            logging.getLogger("kb_pipeline.http").info("http_request", extra={"route": self.path.split("?", 1)[0], "status": args[1] if len(args) > 1 else None})

    return Handler


def _safe_search_hit(service, hit):
    """Public DTO. Explicit allow-list prevents URI/artifact leakage."""
    return {"document_id": hit.document_id, "title": hit.title, "snippet": hit.snippet,
            **service.search_metadata(hit)}


def _report(service):
    """Compatibility aggregate for service implementations without report()."""
    status = service.store.status()
    health = service.health() if hasattr(service, "health") else {}
    readiness = service.readiness() if hasattr(service, "readiness") else {"status": "ready", "checks": {}}
    return {
        "counts": {key: status.get(key, 0) for key in ("documents", "tombstones", "raw_records")},
        "ledger": {"sequence": health.get("ledger_sequence", 0), "outbox_pending": health.get("outbox_pending", 0),
                   "outbox_failed": health.get("outbox_failed", 0), "dead_letters": health.get("dead_letters", 0),
                   "gaps": health.get("gaps", 0), "checkpoints": health.get("checkpoints", {})},
        "projection": {"lag": health.get("projection_lag", {}), "max_lag": health.get("max_projection_lag", 0), "watermarks": health.get("watermarks", {})},
        "readiness": {"status": readiness.get("status", "not_ready"), "checks": readiness.get("checks", {})},
    }


def create_server(service, host="127.0.0.1", port=8080, token=None, *, max_query_chars=512, max_results=100, frontend_root=None, max_request_bytes=16 * 1024, identity_provider=None, production=False):
    if production and (identity_provider is None or getattr(identity_provider, "test_only", False)):
        raise ValueError("production API requires non-test OIDC validator")
    token = token or secrets.token_urlsafe(32)
    # Token map exists only for loopback demo/slice. Production never accepts it.
    tokens = {} if production else {token: {"identity": "reader", "tenant": "default", "is_admin": False}}
    handler = _handler(service, tokens, token, max_query_chars, max_results, frontend_root, max_request_bytes)
    if production:
        validator: Any = identity_provider
        def production_identity(self):
            value = self.headers.get("Authorization", "")
            if not value.startswith("Bearer "):
                return None
            try:
                return validator.validate(value[7:])
            except Exception:
                return None
        handler._identity = production_identity
    server = ThreadingHTTPServer((host, port), handler)
    setattr(server, "runtime_tokens", tokens)
    setattr(server, "production", production)
    return server, token
