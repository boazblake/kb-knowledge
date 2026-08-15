from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import ContentAwareCanonicalizer, LocalFilesConnector
from .domain import ACL
from .service import KnowledgeService
from .answer import DeterministicAnswerer
from .storage import LexicalIndex, MemoryAuditStore, SQLiteStore
from .postgres_authority import PostgresAuthorityRepository, PostgresIngestionService


class DemoACLResolver:
    def __init__(self, acl: ACL):
        self.acl = acl

    def resolve(self, record):
        return record.source and self.acl


@dataclass(frozen=True)
class RuntimeConfig:
    database: Path | str
    source_root: Path | None
    host: str = "127.0.0.1"
    port: int = 8080
    mode: str = "demo"
    max_query_chars: int = 512
    max_results: int = 100
    frontend_root: Path | None = None
    payload_provider: Any | None = None
    identity_provider: Any | None = None
    key_provider: Any | None = None
    max_request_bytes: int = 1024 * 1024
    max_replay_batch: int = 100
    max_projection_lag: int = 0
    answerer: Any | None = None
    vision_observer: Any | None = None
    semantic_embedder: Any | None = None
    raw_storage: Any | None = None
    workflow: Any | None = None
    telemetry: Any | None = None
    connector: Any | None = None
    authority_repository: Any | None = None
    telemetry_endpoint: str | None = None
    telemetry_service_name: str | None = None

    def validate(self) -> "RuntimeConfig":
        if self.mode not in {"demo", "slice", "production"}:
            raise ValueError("mode must be demo, slice, or production")
        # Port 0 lets OS allocate free ephemeral port for isolated test/launcher runs.
        if not (0 <= self.port <= 65535):
            raise ValueError("port must be between 0 and 65535")
        if self.max_query_chars < 1 or self.max_query_chars > 4096:
            raise ValueError("max_query_chars out of range")
        if self.max_results < 1 or self.max_results > 1000:
            raise ValueError("max_results out of range")
        if self.max_request_bytes < 1 or self.max_request_bytes > 50 * 1024 * 1024: raise ValueError("max_request_bytes out of range")
        if self.max_replay_batch < 1 or self.max_replay_batch > 10000: raise ValueError("max_replay_batch out of range")
        if self.max_projection_lag < 0 or self.max_projection_lag > 1000000: raise ValueError("max_projection_lag out of range")
        if self.mode != "production" and (self.source_root is None or not self.source_root.is_dir()):
            raise ValueError("source_root must be a directory")
        if self.mode == "production":
            database = str(self.database).lower()
            if database == ":memory:" or database.endswith((".sqlite", ".sqlite3", ".db")) or not database.startswith(("postgres://", "postgresql://")):
                raise ValueError("production requires PostgreSQL authority; SQLite is forbidden")
        if self.payload_provider is not None and getattr(self.payload_provider, "test_only", False) and self.mode not in {"demo", "slice"}:
            raise ValueError("test-only crypto provider is only permitted in demo or slice mode")
        if self.mode == "production" and (self.identity_provider is None or self.key_provider is None):
            raise ValueError("production requires injected OIDC and KMS ports")
        for provider in (self.identity_provider, self.key_provider, self.payload_provider,
                         self.raw_storage, self.workflow, self.connector, self.telemetry):
            if self.mode == "production" and getattr(provider, "test_only", False):
                raise ValueError("test/demo security adapter forbidden in production")
        if self.mode == "production" and self.payload_provider is None:
            raise ValueError("production requires wired payload encryption provider")
        if self.mode == "production":
            if self.raw_storage is None or self.workflow is None or self.telemetry is None:
                raise ValueError("production requires S3-compatible raw storage, workflow, and telemetry")
            if self.telemetry_endpoint is None or self.telemetry_service_name is None:
                raise ValueError("production requires telemetry endpoint and service name")
            if self.connector is None or getattr(self.connector, "test_only", False):
                raise ValueError("production requires non-fixture connector transport")
            if self.authority_repository is not None and not isinstance(self.authority_repository, PostgresAuthorityRepository):
                raise ValueError("production requires PostgresAuthorityRepository")
            required = {
                "identity_provider": ("validate",),
                "key_provider": ("encrypt", "decrypt"),
                "payload_provider": ("encrypt", "decrypt", "current_key_id"),
                "raw_storage": ("put", "get", "delete"),
                "workflow": ("start_ingestion",),
                "telemetry": ("span", "counter"),
                "connector": ("poll", "read"),
            }
            for name, methods in required.items():
                provider = getattr(self, name)
                if not all(hasattr(provider, method) for method in methods):
                    raise ValueError(f"production dependency {name} has incompatible adapter type")
        return self


@dataclass
class Composition:
    config: RuntimeConfig
    store: Any
    connector: Any
    service: Any


def compose(config: RuntimeConfig) -> Composition:
    config.validate()
    if config.mode == "production":
        repository = config.authority_repository or PostgresAuthorityRepository(str(config.database))
        # Construction is intentionally eager: missing psycopg or DB setup fails
        # before accepting traffic, never by silently falling back to SQLite.
        repository.open()
        return Composition(config, repository, config.connector,
                           PostgresIngestionService(repository, config.connector, ContentAwareCanonicalizer()))
    store = SQLiteStore(config.database, payload_provider=config.payload_provider)
    assert config.source_root is not None
    connector = LocalFilesConnector(config.source_root)
    service = KnowledgeService(
        store, LexicalIndex(), DemoACLResolver(ACL(frozenset({"reader"}), frozenset({"admin"}))),
        ContentAwareCanonicalizer(), store,
        max_projection_lag=config.max_projection_lag,
        answerer=config.answerer or DeterministicAnswerer(),
        vision_observer=config.vision_observer,
        semantic_embedder=config.semantic_embedder,
    )
    return Composition(config, store, connector, service)
