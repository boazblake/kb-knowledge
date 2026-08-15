"""Thin provider adapters used by production/slice composition.

No provider SDK is imported at module load. Missing optional dependencies fail
at construction, not silently downgrade to a fake implementation.
"""
from __future__ import annotations

import base64
import hashlib
import importlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from .protocol import PayloadEnvelope


class AdapterUnavailable(RuntimeError):
    pass


class EncryptionBoundaryError(RuntimeError):
    """Raw artifact encryption, integrity, or authorization failure."""


@dataclass(frozen=True)
class ArtifactContext:
    provider: str
    tenant: str
    connector: str
    source: str
    object: str
    revision: str
    purpose: str = "raw-artifact"

    def __post_init__(self):
        values = (self.provider, self.tenant, self.connector, self.source,
                  self.object, self.revision, self.purpose)
        if any(not isinstance(value, str) or not value or len(value) > 256 for value in values):
            raise ValueError("complete artifact context required")
        if self.purpose != "raw-artifact":
            raise ValueError("unsupported artifact purpose")
        if any("\x00" in value for value in values):
            raise ValueError("NUL is forbidden in artifact context")

    def as_mapping(self) -> dict[str, str]:
        return {"provider": self.provider, "tenant": self.tenant,
                "connector": self.connector, "source": self.source,
                "object": self.object, "revision": self.revision,
                "purpose": self.purpose}

    def key(self, prefix: str) -> str:
        # Keep object names predictable and traversal-free. Encode no user path.
        safe = re.compile(r"^[A-Za-z0-9._~-]+$")
        values = (self.provider, self.tenant, self.connector, self.source,
                  self.object, self.revision)
        if any(value in {".", ".."} or not safe.fullmatch(value) for value in values):
            raise ValueError("unsafe artifact key component")
        clean = prefix.strip("/")
        return "/".join(filter(None, (clean, "raw", *values)))


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


class S3RawObjectStore:
    test_only = False
    encrypted = True
    def __init__(self, bucket: str, *, client: Any = None, prefix: str = "raw/", kms: Any = None):
        if not bucket: raise ValueError("S3 bucket required")
        if kms is None: raise ValueError("KMS encryption provider required")
        if client is None:
            try: client = importlib.import_module("boto3").client("s3")
            except ImportError as exc: raise AdapterUnavailable("boto3 required for S3 raw storage") from exc
        self.bucket, self.client, self.prefix, self.kms = bucket, client, prefix, kms
    def put(self, key, payload, *, metadata=None, context=None):
        if not isinstance(context, ArtifactContext): raise EncryptionBoundaryError("artifact context required")
        expected_key = context.key(self.prefix)
        if key != expected_key: raise EncryptionBoundaryError("object key/context mismatch")
        envelope = self.kms.encrypt(payload, key_id=self.kms.current_key_id, context=context.as_mapping())
        meta = {str(k).lower(): str(v) for k, v in dict(metadata or {}).items()}
        meta.update({"content-sha256": hashlib.sha256(payload).hexdigest(),
                     "kms-key-id": envelope.key_id, "kms-algorithm": envelope.algorithm,
                     "kms-nonce": _b64(envelope.nonce), "kms-tag": _b64(envelope.tag),
                     "kms-context": _b64(envelope.context), "kms-wrapped-key": _b64(envelope.wrapped_key)})
        # Client-side envelope encryption keeps this compatible with S3 APIs
        # that do not implement AWS-specific SSE-KMS headers.
        self.client.put_object(Bucket=self.bucket, Key=key, Body=envelope.ciphertext,
                               Metadata=meta)
        return f"s3://{self.bucket}/{key}"
    def get(self, key, *, context=None):
        if not isinstance(context, ArtifactContext) or key != context.key(self.prefix):
            raise EncryptionBoundaryError("artifact context required or mismatched")
        try:
            result = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise EncryptionBoundaryError("encrypted artifact unavailable") from exc
        payload = result["Body"].read()
        metadata = {str(k).lower(): v for k, v in result.get("Metadata", {}).items()}
        required = ("content-sha256", "kms-key-id", "kms-algorithm", "kms-nonce",
                    "kms-tag", "kms-context", "kms-wrapped-key")
        if any(name not in metadata for name in required): raise EncryptionBoundaryError("incomplete encrypted object")
        envelope = PayloadEnvelope(metadata["kms-key-id"], metadata["kms-algorithm"], payload,
                                   _unb64(metadata["kms-nonce"]), _unb64(metadata["kms-tag"]),
                                   _unb64(metadata["kms-context"]), _unb64(metadata["kms-wrapped-key"]))
        plaintext = self.kms.decrypt(envelope, context=context.as_mapping())
        if hashlib.sha256(plaintext).hexdigest() != metadata["content-sha256"]:
            raise EncryptionBoundaryError("raw artifact hash mismatch")
        return plaintext
    def delete(self, key): self.client.delete_object(Bucket=self.bucket, Key=key)


class ManagedOIDCValidator:
    """Compatibility wrapper delegating to single secure OIDC validator."""
    test_only = False
    production_oidc = True
    def __init__(self, issuer: str, audience: str, jwks_url: str | None = None, *, validator: Any = None,
                 algorithms: tuple[str, ...] = ("RS256",), leeway: int = 30,
                 cache_lifespan: int = 300, timeout: float = 5.0):
        from .security import OIDCJWKSValidator
        if validator is not None:
            self._validator = validator
        else:
            if not jwks_url: raise ValueError("OIDC JWKS URL required")
            try:
                self._validator = OIDCJWKSValidator(issuer, audience, jwks_url, algorithms=algorithms,
                                                    leeway=leeway, cache_lifespan=cache_lifespan, timeout=timeout)
            except ImportError as exc: raise AdapterUnavailable("PyJWT[crypto] required") from exc
    def validate(self, token: str):
        return self._validator.validate(token)


class CloudKMSProvider:
    test_only = False
    def __init__(self, key_id: str, *, client: Any = None):
        if not key_id: raise ValueError("KMS key id required")
        self.current_key_id, self.client = key_id, client
        if client is None:
            try: self.client = importlib.import_module("boto3").client("kms")
            except ImportError as exc: raise AdapterUnavailable("boto3 required for KMS") from exc
    def encrypt(self, plaintext, *, key_id=None, context=None):
        if not context: raise EncryptionBoundaryError("encryption context required")
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            aad = json.dumps(dict(context), sort_keys=True, separators=(",", ":")).encode()
            result = self.client.generate_data_key(KeyId=key_id or self.current_key_id, KeySpec="AES_256",
                                                   EncryptionContext=dict(context))
            nonce = __import__("secrets").token_bytes(12)
            body = AESGCM(result["Plaintext"]).encrypt(nonce, plaintext, aad)
            return PayloadEnvelope(key_id or self.current_key_id, "AES-256-GCM", body[:-16], nonce,
                                   body[-16:], aad, result["CiphertextBlob"])
        except Exception as exc:
            raise EncryptionBoundaryError("KMS encryption failed") from exc
    def decrypt(self, envelope, *, context=None):
        if not context or not envelope.wrapped_key: raise EncryptionBoundaryError("incomplete envelope")
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            aad = json.dumps(dict(context), sort_keys=True, separators=(",", ":")).encode()
            if envelope.context != aad: raise EncryptionBoundaryError("context mismatch")
            result = self.client.decrypt(CiphertextBlob=envelope.wrapped_key,
                                         EncryptionContext=dict(context))
            return AESGCM(result["Plaintext"]).decrypt(envelope.nonce, envelope.ciphertext + envelope.tag, aad)
        except EncryptionBoundaryError: raise
        except Exception as exc: raise EncryptionBoundaryError("KMS decryption failed") from exc


def build_raw_artifact_store(bucket: str, key_id: str, *, prefix: str = "raw/",
                             s3_client: Any = None, kms_client: Any = None) -> S3RawObjectStore:
    """Use boto3 default credential chain: workload identity/secret manager boundary."""
    return S3RawObjectStore(bucket, prefix=prefix, client=s3_client,
                            kms=CloudKMSProvider(key_id, client=kms_client))


class OpenTelemetry:
    test_only = False
    def __init__(self, service_name: str, endpoint: str, *, tracer_provider=None, meter_provider=None):
        if not service_name or not endpoint: raise ValueError("telemetry service_name and endpoint required")
        try:
            otel_trace = importlib.import_module("opentelemetry.trace")
            otel_metrics = importlib.import_module("opentelemetry.metrics")
        except ImportError as exc: raise AdapterUnavailable("OpenTelemetry packages required") from exc
        self.tracer = otel_trace.get_tracer(service_name, tracer_provider=tracer_provider)
        self.meter = otel_metrics.get_meter(service_name, meter_provider=meter_provider)
    def span(self, name, **attributes):
        return self.tracer.start_as_current_span(name, attributes=attributes)
    def counter(self, name, value=1, **attributes):
        self.meter.create_counter(name).add(value, attributes)


class TemporalWorkflowBoundary:
    test_only = False
    def __init__(self, client: Any):
        if client is None: raise ValueError("Temporal client required")
        self.client = client
    def start_ingestion(self, workflow_id, payload):
        return self.client.start_workflow("ingestion", payload, id=workflow_id, task_queue="kb-ingestion")


class FixtureWorkflowBoundary:
    test_only = True
    def __init__(self): self.started = []
    def start_ingestion(self, workflow_id, payload):
        self.started.append((workflow_id, dict(payload))); return workflow_id
