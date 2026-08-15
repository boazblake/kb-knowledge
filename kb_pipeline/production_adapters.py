"""Thin provider adapters used by production/slice composition.

No provider SDK is imported at module load. Missing optional dependencies fail
at construction, not silently downgrade to a fake implementation.
"""
from __future__ import annotations

import importlib
from typing import Any, Mapping


class AdapterUnavailable(RuntimeError):
    pass


class S3RawObjectStore:
    test_only = False
    def __init__(self, bucket: str, *, client: Any = None, prefix: str = "raw/", kms: Any = None, tenant: str = ""):
        if not bucket: raise ValueError("S3 bucket required")
        if client is None:
            try: client = importlib.import_module("boto3").client("s3")
            except ImportError as exc: raise AdapterUnavailable("boto3 required for S3 raw storage") from exc
        self.bucket, self.client, self.prefix, self.kms, self.tenant = bucket, client, prefix, kms, tenant
    def _key(self, key: str) -> str: return f"{self.prefix}{key}"
    def put(self, key, payload, *, metadata=None):
        metadata = dict(metadata or {})
        if self.kms is not None:
            context = {"object_key": key, "tenant": self.tenant, "purpose": "raw-artifact"}
            envelope = self.kms.encrypt(payload, key_id=self.kms.current_key_id, context=context)
            payload = envelope.ciphertext
            metadata.update({"kms-key-id": envelope.key_id, "kms-algorithm": envelope.algorithm,
                             "kms-nonce": envelope.nonce.hex(), "kms-tag": envelope.tag.hex(),
                             "kms-context": envelope.context.hex()})
        self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=payload, Metadata=metadata)
        return f"s3://{self.bucket}/{self._key(key)}"
    def get(self, key):
        result = self.client.get_object(Bucket=self.bucket, Key=self._key(key))
        payload = result["Body"].read()
        metadata = {str(k).lower(): v for k, v in result.get("Metadata", {}).items()}
        if self.kms is None or "kms-key-id" not in metadata:
            return payload
        from .protocol import PayloadEnvelope
        envelope = PayloadEnvelope(metadata["kms-key-id"], metadata["kms-algorithm"], payload,
                                   bytes.fromhex(metadata["kms-nonce"]), bytes.fromhex(metadata["kms-tag"]),
                                   bytes.fromhex(metadata.get("kms-context", "")))
        return self.kms.decrypt(envelope, context={"object_key": key, "tenant": self.tenant, "purpose": "raw-artifact"})
    def delete(self, key): self.client.delete_object(Bucket=self.bucket, Key=self._key(key))


class ManagedOIDCValidator:
    test_only = False
    def __init__(self, issuer: str, audience: str, *, validator: Any = None):
        if not issuer or not audience: raise ValueError("OIDC issuer and audience required")
        self.issuer, self.audience, self.validator = issuer, audience, validator
        if validator is None:
            try: importlib.import_module("jwt")
            except ImportError as exc: raise AdapterUnavailable("PyJWT or injected OIDC validator required") from exc
    def validate(self, token: str):
        if self.validator is not None: return self.validator(token)
        try:
            jwt = importlib.import_module("jwt")
            client = jwt.PyJWKClient(self.issuer + "/.well-known/jwks.json")
            key = client.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256", "ES256"], audience=self.audience, issuer=self.issuer)
            from .security import Principal
            tenant = claims.get("tenant")
            roles = claims.get("roles", [])
            scopes = claims.get("source_scopes", claims.get("scopes", []))
            if not claims.get("sub") or not tenant or not isinstance(roles, list) or not isinstance(scopes, list):
                raise ValueError("invalid tenant claims")
            return Principal(claims["sub"], tenant, frozenset(roles), frozenset(scopes), claims["iss"])
        except Exception as exc:
            raise AdapterUnavailable("OIDC JWKS validation failed") from exc


class CloudKMSProvider:
    test_only = False
    def __init__(self, key_id: str, *, client: Any = None):
        if not key_id: raise ValueError("KMS key id required")
        self.current_key_id, self.client = key_id, client
        if client is None:
            try: self.client = importlib.import_module("boto3").client("kms")
            except ImportError as exc: raise AdapterUnavailable("boto3 required for KMS") from exc
    def encrypt(self, plaintext, *, key_id=None, context=None):
        from .protocol import PayloadEnvelope
        result = self.client.encrypt(KeyId=key_id or self.current_key_id, Plaintext=plaintext,
                                     EncryptionContext=dict(context or {}))
        return PayloadEnvelope(key_id or self.current_key_id, "AWS-KMS", result["CiphertextBlob"], b"", b"", b"")
    def decrypt(self, envelope, *, context=None):
        return self.client.decrypt(CiphertextBlob=envelope.ciphertext, EncryptionContext=dict(context or {}))["Plaintext"]


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
