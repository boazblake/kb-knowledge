"""Provider-neutral security boundaries and deterministic local adapters.

Adapters contain no network calls or provider SDKs. Production injects real
implementations behind these ports; local adapters exist for demos/tests only.
"""
from __future__ import annotations

import base64, hashlib, hmac, json, secrets, time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping, Protocol, FrozenSet

from .protocol import PayloadEnvelope


class SecurityError(ValueError): pass
class AuthenticationError(SecurityError): pass
class AuthorizationError(SecurityError): pass
class EnvelopeError(SecurityError): pass


@dataclass(frozen=True)
class Principal:
    subject: str
    tenant: str
    roles: FrozenSet[str] = frozenset()
    source_scopes: FrozenSet[str] = frozenset()
    issuer: str = ""

    def can_read(self, tenant: str, source: str = "") -> bool:
        return self.tenant == tenant and (not source or source in self.source_scopes or "*" in self.source_scopes)

    def is_admin(self, tenant: str) -> bool:
        return self.tenant == tenant and "admin" in self.roles


class PrincipalProvider(Protocol):
    def validate(self, token: str) -> Principal: ...


class Authorization(Protocol):
    def can_read(self, principal: Principal, tenant: str, source: str = "") -> bool: ...
    def is_admin(self, principal: Principal, tenant: str) -> bool: ...


class KeyProvider(Protocol):
    def encrypt(self, plaintext: bytes, *, key_id: str, context: Mapping[str, str] | None = None) -> PayloadEnvelope: ...
    def decrypt(self, envelope: PayloadEnvelope, *, context: Mapping[str, str] | None = None) -> bytes: ...


class TenantAuthorization:
    def can_read(self, principal, tenant, source=""): return principal.can_read(tenant, source)
    def is_admin(self, principal, tenant): return principal.is_admin(tenant)


def _b64(value: bytes) -> str: return base64.urlsafe_b64encode(value).rstrip(b"=").decode()
def _unb64(value: str) -> bytes: return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class FakeOIDCValidator:
    """Offline JWKS-like HS256 validator. JWKS keys are supplied by caller."""
    test_only = True
    def __init__(self, issuer: str, audience: str, jwks: Mapping[str, bytes], leeway: int = 0):
        self.issuer, self.audience, self.jwks, self.leeway = issuer, audience, dict(jwks), leeway

    def validate(self, token: str) -> Principal:
        try:
            head, body, signature = token.split(".")
            header, claims = json.loads(_unb64(head)), json.loads(_unb64(body))
            kid, alg = header["kid"], header["alg"]
            key = self.jwks[kid]
            expected = hmac.new(key, f"{head}.{body}".encode(), hashlib.sha256).digest()
            decoded_signature = _unb64(signature)
            if (_b64(decoded_signature) != signature or alg != "HS256" or
                    not hmac.compare_digest(expected, decoded_signature)):
                raise AuthenticationError("invalid signature")
            now = time.time()
            if claims.get("iss") != self.issuer or claims.get("aud") != self.audience: raise AuthenticationError("issuer or audience mismatch")
            if not claims.get("sub") or float(claims.get("exp", 0)) + self.leeway < now: raise AuthenticationError("token expired")
            tenant = claims.get("tenant")
            roles, scopes = claims.get("roles", []), claims.get("source_scopes", claims.get("scopes", []))
            if not tenant or not isinstance(roles, list) or not isinstance(scopes, list): raise AuthenticationError("invalid tenant authorization claims")
            return Principal(claims["sub"], tenant, frozenset(roles), frozenset(scopes), claims["iss"])
        except AuthenticationError: raise
        except Exception as exc: raise AuthenticationError("malformed token") from exc


@dataclass
class FakeKMSProvider:
    master_key: bytes
    current_key_id: str = "kms-v1"
    test_only: bool = True
    state: str = "active"
    _retired: set[str] = field(default_factory=set)

    def _key(self, key_id): return hmac.new(self.master_key, key_id.encode(), hashlib.sha256).digest()
    @staticmethod
    def _aad(context): return json.dumps(dict(context or {}), sort_keys=True, separators=(",", ":")).encode()

    def encrypt(self, plaintext, *, key_id=None, context=None):
        if self.state != "active": raise EnvelopeError("key provider unavailable")
        key_id = key_id or self.current_key_id; key = self._key(key_id); aad = self._aad(context)
        nonce = secrets.token_bytes(12)
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad); body, tag = ciphertext[:-16], ciphertext[-16:]
            algorithm = "AES-256-GCM"
        except ImportError:
            stream = hashlib.sha256(key + nonce + aad).digest(); body = bytes(v ^ stream[i % len(stream)] for i, v in enumerate(plaintext))
            tag = hmac.new(key, aad + nonce + body, hashlib.sha256).digest(); algorithm = "FAKE-XOR-HMAC"
        return PayloadEnvelope(key_id, algorithm, body, nonce, tag, aad)

    def decrypt(self, envelope, *, context=None):
        if envelope.key_id in self._retired or self.state == "unavailable": raise EnvelopeError("key unavailable")
        aad = self._aad(context)
        if not hmac.compare_digest(aad, getattr(envelope, "context", b"")): raise EnvelopeError("context mismatch")
        key = self._key(envelope.key_id)
        try:
            if envelope.algorithm == "AES-256-GCM":
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                return AESGCM(key).decrypt(envelope.nonce, envelope.ciphertext + envelope.tag, aad)
            if envelope.algorithm != "FAKE-XOR-HMAC": raise EnvelopeError("unsupported envelope")
            if not hmac.compare_digest(envelope.tag, hmac.new(key, aad + envelope.nonce + envelope.ciphertext, hashlib.sha256).digest()): raise EnvelopeError("tampered envelope")
            stream = hashlib.sha256(key + envelope.nonce + aad).digest(); return bytes(v ^ stream[i % len(stream)] for i, v in enumerate(envelope.ciphertext))
        except EnvelopeError: raise
        except Exception as exc: raise EnvelopeError("decrypt failed") from exc

    def rotate(self, key_id: str): self.current_key_id = key_id
    def retire(self, key_id: str): self._retired.add(key_id)
    def erase(self): self.state = "unavailable"; self.master_key = b""
