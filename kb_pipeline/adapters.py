from __future__ import annotations

import hashlib
import re
from pathlib import Path
from .domain import ScanResult
from .domain import Input, RawRecord, SourceVersion, CanonicalDocument, ACL

JPEG_MAGIC = b"\xff\xd8\xff"


def is_jpeg(payload: bytes) -> bool:
    """Bounded JPEG identification; do not inspect or decode image body."""
    return payload[:len(JPEG_MAGIC)] == JPEG_MAGIC


def is_valid_jpeg(payload: bytes) -> bool:
    """Bounded structural check before image classification or indexing."""
    if not is_jpeg(payload) or len(payload) < 6 or payload.rfind(b"\xff\xd9") < 0:
        return False
    pos, found_frame = 2, False
    while pos + 4 <= len(payload) and pos < 65536:
        if payload[pos] != 0xFF:
            pos += 1; continue
        while pos < len(payload) and payload[pos] == 0xFF: pos += 1
        if pos >= len(payload): break
        marker = payload[pos]; pos += 1
        if marker in {0xD8, 0xD9}: continue
        if pos + 2 > len(payload): break
        length = int.from_bytes(payload[pos:pos + 2], "big")
        if length < 2 or pos + length > len(payload): break
        if marker in set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0)):
            if length < 7: return False
            height = int.from_bytes(payload[pos + 3:pos + 5], "big")
            width = int.from_bytes(payload[pos + 5:pos + 7], "big")
            found_frame = bool(width and height and width <= 10000 and height <= 10000)
            break
        pos += length
    return found_frame


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
                if is_jpeg(payload) and not is_valid_jpeg(payload):
                    continue
                if not is_jpeg(payload):
                    try:
                        text_probe = payload.decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                    if "\x00" in text_probe:
                        continue
                metadata = ({"mime_type": "image/jpeg", "byte_length": str(len(payload)),
                             "content_hash": hashlib.sha256(payload).hexdigest()}
                            if is_jpeg(payload) else {})
                records.append(Input(self.name, rel, payload, path.as_uri(),
                                     metadata=metadata,
                                     provider=self.provider, tenant=self.tenant,
                                     source_instance=self.source_instance))
        except OSError as exc:
            return ScanResult(tuple(records), False, str(exc))
        return ScanResult(tuple(records), True)


class ContentAwareCanonicalizer:
    def __init__(self, max_bytes: int = 10 * 1024 * 1024, max_chars: int = 5 * 1024 * 1024):
        self.max_bytes, self.max_chars = max_bytes, max_chars
    def canonicalize(self, record: RawRecord, acl: ACL) -> CanonicalDocument:
        if len(record.payload) > self.max_bytes: raise ValueError("payload exceeds limit")
        if is_jpeg(record.payload):
            if not is_valid_jpeg(record.payload): raise ValueError("malformed JPEG payload")
            filename = record.source.source_uri.rsplit("/", 1)[-1] or "unnamed image"
            text = f"JPEG image: {filename}; visual extraction pending."
        else:
            try:
                text = record.payload.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("unsupported binary payload") from exc
            if "\x00" in text:
                raise ValueError("unsupported binary payload")
        if len(text) > self.max_chars: raise ValueError("text exceeds limit")
        return CanonicalDocument(record.source.source_id, record.source, record.source.source_uri.rsplit("/", 1)[-1], text, acl, record.metadata)


class PlainTextCanonicalizer(ContentAwareCanonicalizer):
    """Compatibility name; canonicalization now rejects unsupported binary safely."""
    pass


def source_version(item: Input) -> SourceVersion:
    digest = hashlib.sha256(item.payload).hexdigest()
    return SourceVersion(item.external_id, digest, item.source_uri, item.observed_at, digest)


def tokenize(value: str) -> set[str]:
    return set(re.findall(r"[\w-]+", value.casefold()))
