from __future__ import annotations

import hashlib
import fnmatch
import os
import re
from collections.abc import Iterable
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
    DEFAULT_IGNORED_DIRECTORIES = frozenset({
        ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "vendor",
        "build", "dist", "out", "target", "coverage", "__pycache__",
        ".cache", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox",
        ".next", ".turbo", ".terraform",
    })
    DEFAULT_IGNORED_FILE_PATTERNS = (
        ".env", ".env.*", ".DS_Store", "*.pem", "*.key", "*.p12", "*.pfx",
        "*.secret", "*.secrets", "credentials.*", "secrets.*",
    )

    def __init__(self, root: Path, max_files: int = 10000, max_bytes: int = 100 * 1024 * 1024,
                 provider: str = "local", tenant: str = "default", source_instance: str | None = None,
                 *, include_ignored: bool = False, ignore_directories: Iterable[str] = (),
                 ignore_file_patterns: Iterable[str] = ()):
        self.root = root.expanduser().resolve()
        if not self.root.is_dir(): raise ValueError("root must be a directory")
        self.max_files, self.max_bytes = max_files, max_bytes
        self.provider, self.tenant = provider, tenant
        self.source_instance = source_instance or str(self.root)
        self.include_ignored = include_ignored
        self.ignore_directories = frozenset(ignore_directories)
        self.ignore_file_patterns = tuple(ignore_file_patterns)

    def _directory_ignored(self, name: str) -> bool:
        return not self.include_ignored and name in self.DEFAULT_IGNORED_DIRECTORIES | self.ignore_directories

    def _file_ignore_reason(self, name: str) -> str | None:
        if self.include_ignored:
            return None
        patterns = self.DEFAULT_IGNORED_FILE_PATTERNS + self.ignore_file_patterns
        return next((f"sensitive metadata pattern: {pattern}" for pattern in patterns
                     if fnmatch.fnmatchcase(name, pattern)), None)

    def is_ignored_path(self, relative_path: str) -> bool:
        """Tell reconciliation that omitted paths are outside snapshot authority."""
        if self.include_ignored:
            return False
        parts = Path(relative_path).parts
        return any(self._directory_ignored(part) for part in parts[:-1]) or bool(self._file_ignore_reason(parts[-1]))
    def read(self):
        return iter(self.scan().records)
    def scan(self):
        records, exclusions, total = [], [], 0
        try:
            for current, directories, files in os.walk(self.root, topdown=True, followlinks=False):
                current_path = Path(current)
                kept_directories = []
                for name in sorted(directories):
                    path = current_path / name
                    rel = str(path.relative_to(self.root))
                    if path.is_symlink():
                        return ScanResult(tuple(records), False, "symlink encountered", tuple(exclusions))
                    if self._directory_ignored(name):
                        exclusions.append((rel, f"ignored directory: {name}"))
                    else:
                        kept_directories.append(name)
                directories[:] = kept_directories
                for name in sorted(files):
                    path = current_path / name
                    rel = str(path.relative_to(self.root))
                    if path.is_symlink():
                        return ScanResult(tuple(records), False, "symlink encountered", tuple(exclusions))
                    if (reason := self._file_ignore_reason(name)):
                        exclusions.append((rel, reason))
                        continue
                    resolved = path.resolve()
                    if self.root not in resolved.parents:
                        return ScanResult(tuple(records), False, "path escaped root", tuple(exclusions))
                    size = path.stat().st_size
                    if len(records) >= self.max_files or total + size > self.max_bytes:
                        return ScanResult(tuple(records), False, "scan limit exceeded", tuple(exclusions))
                    payload = path.read_bytes(); total += len(payload)
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
            return ScanResult(tuple(records), False, str(exc), tuple(exclusions))
        return ScanResult(tuple(records), True, exclusions=tuple(exclusions))


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
