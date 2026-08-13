from __future__ import annotations

import hashlib
import re
from pathlib import Path
from .domain import ScanResult
from .domain import Input, RawRecord, SourceVersion, CanonicalDocument, ACL


class LocalFilesConnector:
    name = "local-files"
    def __init__(self, root: Path, max_files: int = 10000, max_bytes: int = 100 * 1024 * 1024,
                 provider: str = "local", tenant: str = "default", source_instance: str | None = None):
        self.root = root.expanduser().resolve()
        if not self.root.is_dir(): raise ValueError("root must be a directory")
        self.max_files, self.max_bytes = max_files, max_bytes
        self.provider, self.tenant = provider, tenant
        self.source_instance = source_instance or str(self.root)
    def read(self):
        return iter(self.scan().records)
    def scan(self):
        records, total = [], 0
        try:
            paths = sorted(self.root.rglob("*"))
            for path in paths:
                if path.is_symlink():
                    return ScanResult(tuple(records), False, "symlink encountered")
                if not path.is_file(): continue
                resolved = path.resolve()
                if self.root not in resolved.parents: return ScanResult(tuple(records), False, "path escaped root")
                size = path.stat().st_size
                if len(records) >= self.max_files or total + size > self.max_bytes:
                    return ScanResult(tuple(records), False, "scan limit exceeded")
                payload = path.read_bytes(); total += len(payload)
                rel = str(path.relative_to(self.root))
                records.append(Input(self.name, rel, payload, path.as_uri(),
                                     provider=self.provider, tenant=self.tenant,
                                     source_instance=self.source_instance))
        except OSError as exc:
            return ScanResult(tuple(records), False, str(exc))
        return ScanResult(tuple(records), True)


class PlainTextCanonicalizer:
    def __init__(self, max_bytes: int = 10 * 1024 * 1024, max_chars: int = 5 * 1024 * 1024):
        self.max_bytes, self.max_chars = max_bytes, max_chars
    def canonicalize(self, record: RawRecord, acl: ACL) -> CanonicalDocument:
        if len(record.payload) > self.max_bytes: raise ValueError("payload exceeds limit")
        text = record.payload.decode("utf-8", errors="replace")
        if len(text) > self.max_chars: raise ValueError("text exceeds limit")
        return CanonicalDocument(record.source.source_id, record.source, record.source.source_uri.rsplit("/", 1)[-1], text, acl, record.metadata)


def source_version(item: Input) -> SourceVersion:
    digest = hashlib.sha256(item.payload).hexdigest()
    return SourceVersion(item.external_id, digest, item.source_uri, item.observed_at, digest)


def tokenize(value: str) -> set[str]:
    return set(re.findall(r"[\w-]+", value.casefold()))
