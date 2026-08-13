from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import LocalFilesConnector, PlainTextCanonicalizer
from .domain import ACL
from .service import KnowledgeService
from .storage import LexicalIndex, MemoryAuditStore, SQLiteStore


class DemoACLResolver:
    def __init__(self, acl: ACL):
        self.acl = acl

    def resolve(self, record):
        return record.source and self.acl


@dataclass(frozen=True)
class RuntimeConfig:
    database: Path
    source_root: Path
    host: str = "127.0.0.1"
    port: int = 8080
    mode: str = "demo"
    max_query_chars: int = 512
    max_results: int = 100
    frontend_root: Path | None = None
    payload_provider: Any | None = None
    max_request_bytes: int = 1024 * 1024
    max_replay_batch: int = 100

    def validate(self) -> "RuntimeConfig":
        if self.mode not in {"demo", "production"}:
            raise ValueError("mode must be demo or production")
        if not (1 <= self.port <= 65535):
            raise ValueError("port must be between 1 and 65535")
        if self.max_query_chars < 1 or self.max_query_chars > 4096:
            raise ValueError("max_query_chars out of range")
        if self.max_results < 1 or self.max_results > 1000:
            raise ValueError("max_results out of range")
        if self.max_request_bytes < 1 or self.max_request_bytes > 50 * 1024 * 1024: raise ValueError("max_request_bytes out of range")
        if self.max_replay_batch < 1 or self.max_replay_batch > 10000: raise ValueError("max_replay_batch out of range")
        if not self.source_root.is_dir():
            raise ValueError("source_root must be a directory")
        if self.payload_provider is not None and getattr(self.payload_provider, "test_only", False) and self.mode != "demo":
            raise ValueError("test-only crypto provider is only permitted in demo mode")
        return self


@dataclass
class Composition:
    config: RuntimeConfig
    store: SQLiteStore
    connector: LocalFilesConnector
    service: KnowledgeService


def compose(config: RuntimeConfig) -> Composition:
    config.validate()
    store = SQLiteStore(config.database)
    connector = LocalFilesConnector(config.source_root)
    service = KnowledgeService(
        store, LexicalIndex(), DemoACLResolver(ACL(frozenset({"reader"}), frozenset({"admin"}))),
        PlainTextCanonicalizer(), store,
    )
    return Composition(config, store, connector, service)
