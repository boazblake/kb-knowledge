from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from urllib.error import HTTPError, URLError


MAX_BATCH = 32
MAX_TEXT_CHARS = 100_000
MAX_DIMENSIONS = 4096
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class EmbeddingError(Exception):
    pass


class EmbeddingUnavailable(EmbeddingError):
    pass


class EmbeddingValidationError(EmbeddingError):
    pass


def embedding_input(title: str, text: str) -> str:
    return f"{title}\n{text}"


def input_hash(title: str, text: str) -> str:
    return hashlib.sha256(embedding_input(title, text).encode("utf-8")).hexdigest()


def pack_vector(values) -> bytes:
    values = tuple(float(value) for value in values)
    if not values or len(values) > MAX_DIMENSIONS or any(not math.isfinite(value) for value in values):
        raise EmbeddingValidationError("invalid embedding vector")
    return struct.pack(f"<{len(values)}f", *values)


def unpack_vector(blob: bytes, dimensions: int) -> tuple[float, ...]:
    if dimensions < 1 or dimensions > MAX_DIMENSIONS or len(blob) != dimensions * 4:
        raise EmbeddingValidationError("embedding blob dimension mismatch")
    return struct.unpack(f"<{dimensions}f", blob)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise EmbeddingUnavailable("embedding redirect rejected")


def _open_local(request, timeout):
    return build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=timeout)


@dataclass(frozen=True)
class NoopEmbedder:
    model: str = "none"

    def embed(self, texts: tuple[str, ...]) -> tuple[None, ...]:
        return tuple(None for _ in texts)


@dataclass(frozen=True)
class OllamaEmbedder:
    model: str
    endpoint: str = "http://127.0.0.1:11434/api/embed"
    timeout_seconds: float = 10.0

    def __post_init__(self):
        parsed = urlsplit(self.endpoint)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
            raise ValueError("embedding endpoint must be literal loopback HTTP")
        if not self.model.strip() or len(self.model) > 128 or self.timeout_seconds <= 0 or self.timeout_seconds > 120:
            raise ValueError("invalid embedding model or timeout")

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts or len(texts) > MAX_BATCH or any(not isinstance(text, str) or len(text) > MAX_TEXT_CHARS for text in texts):
            raise EmbeddingValidationError("embedding batch or text exceeds limit")
        payload = json.dumps({"model": self.model, "input": list(texts)}).encode()
        try:
            with _open_local(Request(self.endpoint, data=payload, headers={"Content-Type": "application/json"}), self.timeout_seconds) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except (OSError, HTTPError, URLError) as exc:
            raise EmbeddingUnavailable("embedding provider unavailable") from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise EmbeddingValidationError("embedding response exceeds limit")
        try:
            data = json.loads(raw)
            vectors = data["embeddings"]
            if not isinstance(vectors, list) or len(vectors) != len(texts): raise ValueError("embedding count mismatch")
            result = tuple(tuple(float(value) for value in vector) for vector in vectors)
            packed = tuple(pack_vector(vector) for vector in result)
            dimensions = {len(vector) for vector in result}
            if len(dimensions) != 1: raise ValueError("embedding dimensions mismatch")
            return tuple(unpack_vector(blob, len(result[0])) for blob in packed)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, EmbeddingValidationError) as exc:
            if isinstance(exc, EmbeddingValidationError): raise
            raise EmbeddingValidationError("malformed embedding response") from exc
