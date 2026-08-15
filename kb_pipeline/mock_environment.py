"""MOCK/REFERENCE environment adapters for synthetic end-to-end tests.

These classes are deliberately local fixtures. They are not provider
implementations, production substitutes, or production qualification evidence.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from .production_adapters import ArtifactContext, S3RawObjectStore
from .protocol import PayloadEnvelope
from .security import Principal, AuthenticationError, FakeKMSProvider, OIDCJWKSValidator
from .nango_adapter import NangoAdapter, NangoPoll, NangoRecord, FakeNangoTransport


MOCK_REFERENCE_BANNER = "MOCK/REFERENCE ONLY — synthetic data only; cannot qualify production"


class MockOIDCIssuer:
    """MOCK/REFERENCE local RSA OIDC/JWKS issuer with rotation/failure controls."""
    test_only = True
    production_oidc = False

    def __init__(self, issuer: str = "http://127.0.0.1/mock-issuer", audience: str = "mock-api"):
        try:
            import importlib
            from cryptography.hazmat.primitives.asymmetric import rsa
            jwt = importlib.import_module("jwt")
            RSAAlgorithm = importlib.import_module("jwt.algorithms").RSAAlgorithm
        except ImportError as exc:
            raise RuntimeError("MOCK/REFERENCE OIDC requires PyJWT[crypto]") from exc
        self.issuer, self.audience = issuer, audience
        self._jwt, self._rsa, self._rsa_algorithm = jwt, rsa, RSAAlgorithm
        self._private: dict[str, Any] = {}
        self._keys: dict[str, dict[str, Any]] = {}
        self.fail_jwks = False
        self.fail_issue = False
        self.rotate("mock-rsa-1")
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def jwks(self):
        return {"keys": list(self._keys.values())}

    def rotate(self, kid: str) -> None:
        key = self._rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = self._rsa_algorithm.to_jwk(key.public_key(), as_dict=True)
        public.update({"kid": kid, "use": "sig", "alg": "RS256"})
        self._private[kid], self._keys[kid] = key, public

    def issue(self, *, subject="mock-user", tenant="mock-tenant", roles=("reader",), source_scopes=("mock-connector",), kid=None, **claims):
        if self.fail_issue:
            raise AuthenticationError("MOCK/REFERENCE issuer failure")
        kid = kid or next(reversed(self._private))
        now = datetime.now(timezone.utc)
        payload = {"iss": self.issuer, "aud": self.audience, "sub": subject,
                   "tenant": tenant, "roles": list(roles), "source_scopes": list(source_scopes),
                   "iat": now, "nbf": now, "exp": now + timedelta(minutes=5)}
        payload.update(claims)
        return self._jwt.encode(payload, self._private[kid], algorithm="RS256", headers={"kid": kid})

    def start(self) -> str:
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if owner.fail_jwks:
                    self.send_error(503, "MOCK/REFERENCE JWKS failure")
                    return
                body = json.dumps(owner.jwks).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            def log_message(self, format, *args): pass
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True); self._thread.start()
        self.jwks_url = f"http://127.0.0.1:{self._server.server_address[1]}/jwks"
        return self.jwks_url

    def close(self) -> None:
        if self._server:
            self._server.shutdown(); self._server.server_close()
        if self._thread: self._thread.join(timeout=2)


class MockOIDCValidator:
    """MOCK/REFERENCE wrapper around validator logic pointed at local issuer."""
    test_only = True
    production_oidc = False
    def __init__(self, issuer, audience, jwks_url):
        self._validator = OIDCJWKSValidator(issuer, audience, jwks_url)
    def validate(self, token): return self._validator.validate(token)


class MockKMSProvider(FakeKMSProvider):
    """MOCK/REFERENCE KeyProvider using local AEAD, rotation, and failures."""
    test_only = True

    def fail(self) -> None:
        self.state = "unavailable"


class _MockS3Client:
    """Tiny client shim consumed by existing S3RawObjectStore; MOCK/REFERENCE."""
    def __init__(self): self.objects: dict[tuple[str, str], tuple[bytes, dict[str, str]]] = {}
    def put_object(self, *, Bucket, Key, Body, Metadata): self.objects[(Bucket, Key)] = (Body, dict(Metadata))
    def get_object(self, *, Bucket, Key):
        body, metadata = self.objects[(Bucket, Key)]
        return {"Body": type("Body", (), {"read": lambda self: body})(), "Metadata": metadata}
    def delete_object(self, *, Bucket, Key): self.objects.pop((Bucket, Key), None)


class MockS3RawObjectStore(S3RawObjectStore):
    """MOCK/REFERENCE in-memory S3-compatible store reusing production adapter."""
    test_only = True
    def __init__(self, bucket="mock-bucket", *, kms=None, prefix="raw/"):
        self.mock_client = _MockS3Client()
        super().__init__(bucket, client=self.mock_client, prefix=prefix, kms=kms or MockKMSProvider(b"mock-kms-master-key-32-bytes------"))
    def put(self, key, payload, *, metadata=None, context=None):
        if context is None:
            parts = key.strip("/").split("/")
            if len(parts) < 8: raise ValueError("MOCK/REFERENCE artifact context required")
            context = ArtifactContext(*parts[-6:])
        return super().put(key, payload, metadata=metadata, context=context)
    def get(self, key, *, context=None):
        return super().get(key, context=context)


class MockTemporalBoundary:
    """MOCK/REFERENCE in-process workflow boundary; no Temporal substitute."""
    test_only = True
    def __init__(self, handler=None, failures: int = 0):
        self.handler, self.failures, self.started = handler, failures, []
    def start_ingestion(self, workflow_id: str, payload: Mapping[str, Any]):
        if any(item[0] == workflow_id for item in self.started):
            raise ValueError("MOCK/REFERENCE duplicate workflow")
        if self.failures:
            self.failures -= 1; raise ConnectionError("MOCK/REFERENCE workflow failure")
        self.started.append((workflow_id, dict(payload)))
        return self.handler(workflow_id, payload) if self.handler else workflow_id
    async def start_ingestion_async(self, event):
        return self.start_ingestion(event.idempotency_key, event.payload)


class MockTelemetrySink:
    """MOCK/REFERENCE OTLP/OTel collector sink retaining safe spans/counters."""
    test_only = True
    def __init__(self): self.spans, self.counters = [], {}
    def span(self, name, **attributes):
        sink = self
        class Span:
            def __enter__(self): sink.spans.append({"name": name, "attributes": dict(attributes)}); return self
            def __exit__(self, exc_type, *_):
                if exc_type: sink.spans[-1]["error.type"] = exc_type.__name__
                return False
        return Span()
    def counter(self, name, value=1, **attributes):
        self.counters[name] = self.counters.get(name, 0) + value


class ApprovedMockConnectorFixture:
    """MOCK/REFERENCE approved synthetic connector fixture; no credentials/network."""
    test_only = True
    synthetic_fixture = True
    def __init__(self, tenant="mock-tenant", records=(), oidc_token=None):
        poll = NangoPoll("1", tuple(records), True, "mock-run")
        self.adapter = NangoAdapter("mock-provider", "mock-connection", tenant,
                                    FakeNangoTransport((poll,)), connector="mock-connector")
        self.oidc_token = oidc_token
    def poll(self):
        batch = self.adapter.poll()
        if not self.oidc_token:
            return batch
        envelopes = tuple((type(raw)(raw.source, raw.payload, {**raw.metadata, "oidc_token": self.oidc_token}, raw.schema_version, raw.envelope_id), change)
                          for raw, change in batch.envelopes)
        return type(batch)(batch.cursor, envelopes, batch.complete, batch.run_id, batch.retry,
                           batch.capability, batch.capability_status, batch.cursor_semantics)
    def __getattr__(self, name): return getattr(self.adapter, name)


def mock_status() -> dict[str, str]:
    return {"mode": "mock", "classification": "MOCK/REFERENCE", "qualification": "forbidden", "banner": MOCK_REFERENCE_BANNER}
