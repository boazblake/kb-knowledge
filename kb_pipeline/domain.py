from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping, Sequence


def now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Input:
    connector: str
    external_id: str
    payload: bytes
    source_uri: str
    observed_at: datetime = field(default_factory=now)
    metadata: Mapping[str, str] = field(default_factory=dict)
    permissions: ACL | None = None
    provider: str = "local"
    tenant: str = "default"
    source_instance: str = ""


@dataclass(frozen=True)
class SourceVersion:
    source_id: str
    version: str
    source_uri: str
    observed_at: datetime
    content_hash: str
    supersedes: str | None = None


@dataclass(frozen=True)
class RawRecord:
    source: SourceVersion
    payload: bytes
    metadata: Mapping[str, str]
    schema_version: str = "raw.v1"
    envelope_id: str | None = None


@dataclass(frozen=True)
class ACL:
    # None means unresolved. Unresolved ACL is never visible.
    readers: frozenset[str] | None
    admins: frozenset[str] = frozenset()

    def permits(self, identity: str, is_admin: bool = False) -> bool:
        return is_admin and identity in self.admins or self.readers is not None and identity in self.readers


@dataclass(frozen=True)
class CanonicalDocument:
    document_id: str
    source: SourceVersion
    title: str
    text: str
    acl: ACL
    metadata: Mapping[str, str] = field(default_factory=dict)
    tombstoned: bool = False
    deleted_at: datetime | None = None


@dataclass(frozen=True)
class SearchHit:
    document_id: str
    title: str
    snippet: str
    source_uri: str
    source_version: str


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    action: str
    actor: str
    target: str
    at: datetime = field(default_factory=now)


@dataclass(frozen=True)
class ScanResult:
    records: tuple[Input, ...]
    complete: bool
    reason: str | None = None
    exclusions: tuple[tuple[str, str], ...] = ()
