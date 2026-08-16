from __future__ import annotations

import argparse, hashlib, json, os, shutil, sqlite3, tempfile, sys
import math
from datetime import datetime, timezone
from pathlib import Path
from .storage import SQLiteStore, database_quiesce_lock
from .composition import RuntimeConfig, compose
from .api import create_server
from .answer import OllamaAnswerer, OpenAIAnswerer
from .vision import LocalOllamaVisionObserver
from .embedding import OllamaEmbedder, input_hash
from .production_adapters import ManagedOIDCValidator
from urllib.parse import urlsplit


EVIDENCE_SCHEMA = "kb-pipeline.gate4-evidence.v1"
EVIDENCE_SUITE_VERSION = "0.1.0"
EVIDENCE_MANIFEST = Path(__file__).parents[1] / "tests" / "test_manifest.json"
EVIDENCE_CATEGORIES = (
    "purge", "replay", "readiness", "limits", "log_redaction",
)
_PLACEHOLDERS = {"", "unknown", "not_run", "reported_by_test_runner", "placeholder", "tbd"}


def _test_manifest():
    try:
        manifest = json.loads(EVIDENCE_MANIFEST.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("test evidence manifest is unavailable") from exc
    if manifest.get("schema") != "kb-pipeline.test-manifest.v1" or not isinstance(manifest.get("tests"), list):
        raise ValueError("invalid test evidence manifest")
    if not manifest["tests"] or any(not isinstance(test, str) or not test for test in manifest["tests"]):
        raise ValueError("test evidence manifest must contain test IDs")
    if len(set(manifest["tests"])) != len(manifest["tests"]):
        raise ValueError("test evidence manifest contains duplicate test IDs")
    return manifest


def _required_value(value, field):
    if value is None or (isinstance(value, str) and value.strip().lower() in _PLACEHOLDERS):
        raise ValueError(f"evidence field {field} is missing or placeholder")
    return value


def validate_evidence(data):
    """Validate QA-owned evidence; never manufacture an outcome."""
    if not isinstance(data, dict) or data.get("schema") != EVIDENCE_SCHEMA:
        raise ValueError(f"evidence schema must be {EVIDENCE_SCHEMA}")
    allowed = {"schema", "gate", "validation_owner", "provenance", "test_count", "suite_version",
               "environment", "scenario_results", "backup_bundle_checksums", "sqlite_integrity",
               "restore_validation", "interruption_outcomes", "category_results", "exclusions"}
    unknown = set(data) - allowed if isinstance(data, dict) else set()
    if unknown:
        raise ValueError(f"unknown evidence fields: {', '.join(sorted(unknown))}")
    required = ("gate", "validation_owner", "provenance", "test_count", "suite_version",
                "environment", "scenario_results", "backup_bundle_checksums",
                "sqlite_integrity", "restore_validation", "interruption_outcomes",
                "category_results", "exclusions")
    for field in required:
        _required_value(data.get(field), field)
    if data["gate"] != 4 or data["validation_owner"] != "QA":
        raise ValueError("evidence must identify Gate 4 and QA owner")
    manifest = _test_manifest()
    provenance = data["provenance"]
    if not isinstance(provenance, dict) or provenance.get("source") not in {"result_json", "executed"}:
        raise ValueError("provenance.source must be result_json or executed")
    if provenance.get("manifest") != "tests/test_manifest.json":
        raise ValueError("provenance.manifest must identify checked-in test manifest")
    manifest_hash = hashlib.sha256(EVIDENCE_MANIFEST.read_bytes()).hexdigest()
    if provenance.get("manifest_sha256") != manifest_hash:
        raise ValueError("provenance.manifest_sha256 does not match checked-in test manifest")
    if data["test_count"] != len(manifest["tests"]):
        raise ValueError("test_count does not match checked-in test manifest")
    if data["suite_version"] != EVIDENCE_SUITE_VERSION:
        raise ValueError("suite_version does not match package version")
    if not isinstance(data["environment"], dict) or not data["environment"]:
        raise ValueError("environment must contain observed values")
    _required_value(provenance.get("captured_at"), "provenance.captured_at")
    scenarios = data["scenario_results"]
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("scenario_results must contain actual scenario outcomes")
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise ValueError("scenario result must be object")
        _required_value(scenario.get("id"), "scenario_results.id")
        if scenario.get("status") not in {"pass", "fail"}:
            raise ValueError("scenario status must be pass or fail")
    checksums = data["backup_bundle_checksums"]
    if not isinstance(checksums, list) or not checksums:
        raise ValueError("backup_bundle_checksums must contain observed checksums")
    for item in checksums:
        if not isinstance(item, dict) or not item.get("path") or not isinstance(item.get("sha256"), str) or len(item["sha256"]) != 64:
            raise ValueError("invalid backup checksum entry")
    if data["sqlite_integrity"] not in {"pass", "fail"} or data["restore_validation"] not in {"pass", "fail"}:
        raise ValueError("SQLite integrity and restore validation require pass/fail")
    if not isinstance(data["interruption_outcomes"], list) or not data["interruption_outcomes"]:
        raise ValueError("interruption_outcomes must contain actual outcomes")
    for outcome in data["interruption_outcomes"]:
        if not isinstance(outcome, dict) or not outcome.get("id") or outcome.get("status") not in {"pass", "fail"}:
            raise ValueError("invalid interruption outcome")
    categories = data["category_results"]
    if not isinstance(categories, dict) or set(categories) != set(EVIDENCE_CATEGORIES):
        raise ValueError("category_results must cover purge, replay, readiness, limits, log_redaction")
    if any(categories[key] not in {"pass", "fail"} for key in EVIDENCE_CATEGORIES):
        raise ValueError("category results require pass/fail")
    if not isinstance(data["exclusions"], list) or any(not isinstance(item, str) or not item.strip() for item in data["exclusions"]):
        raise ValueError("exclusions must explicitly list scope exclusions")
    return data


def _fail(hook, hooks):
    if hooks and hook in hooks:
        raise RuntimeError(f"failure injection: {hook}")


def _fsync(path: Path):
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _fsync_tree(root: Path):
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        _fsync(path)
    fd = os.open(root, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def _checksums(root: Path):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and p.name != "manifest.json"}


def _validate_bundle(bundle: Path):
    manifest = bundle / "manifest.json"
    if not manifest.is_file(): raise ValueError("invalid backup: manifest.json missing")
    data = json.loads(manifest.read_text())
    if data.get("schema") != "kb-pipeline.backup.v1": raise ValueError("unsupported backup schema")
    if _checksums(bundle) != data.get("checksums", {}): raise ValueError("backup checksum validation failed")
    store = SQLiteStore(bundle / "database.sqlite", bundle / "raw")
    if not store.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok":
        raise ValueError("backup SQLite integrity validation failed")
    for row in store.db.execute("SELECT artifact FROM raw_records"):
        if not (bundle / "raw" / Path(row["artifact"]).name).is_file():
            raise ValueError(f"missing raw artifact: {row['artifact']}")
    return data


def _backup(database: Path, target: Path, failure_hooks=()):
    target = target.expanduser(); target.parent.mkdir(parents=True, exist_ok=True)
    lock = database_quiesce_lock(database)
    with lock, tempfile.TemporaryDirectory(dir=target.parent, prefix=f".{target.name}.staging-") as name:
        staging = Path(name); (staging / "raw").mkdir()
        # Online backup reads one SQLite snapshot while shared writers are quiesced.
        source = sqlite3.connect(database); destination = sqlite3.connect(staging / "database.sqlite")
        try: source.backup(destination); destination.commit()
        finally: destination.close(); source.close()
        _fail("db_copy", failure_hooks)
        raw = Path(str(database) + ".raw")
        _fail("artifact_copy", failure_hooks)
        if raw.exists():
            for item in sorted(raw.iterdir()):
                if item.is_file(): shutil.copy2(item, staging / "raw" / item.name)
        bundled = SQLiteStore(staging / "database.sqlite", staging / "raw")
        for row in bundled.db.execute("SELECT source_id,version,artifact FROM raw_records").fetchall():
            bundled.db.execute("UPDATE raw_records SET artifact=? WHERE source_id=? AND version=?", (str(bundled.artifact_root / Path(row[2]).name), row[0], row[1]))
        bundled.db.commit(); bundled.validate_artifact_links()
        checksums = _checksums(staging); _fail("manifest_checksum", failure_hooks)
        manifest = {"schema": "kb-pipeline.backup.v1", "created_at": datetime.now(timezone.utc).isoformat(), "checksums": checksums}
        (staging / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2)); _fsync_tree(staging)
        _fail("publish", failure_hooks)
        published = target.with_name(f".{target.name}.publish")
        if published.exists(): shutil.rmtree(published)
        staging.rename(published); _fsync_tree(published)
        old = target.with_name(f".{target.name}.previous")
        if old.exists(): shutil.rmtree(old)
        if target.exists(): target.rename(old)
        try:
            published.rename(target)
        except Exception:
            if target.exists(): shutil.rmtree(target)
            if old.exists(): old.rename(target)
            raise


def _restore(database: Path, bundle: Path, failure_hooks=()):
    _validate_bundle(bundle); database.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=database.parent, prefix=f".{database.name}.restore-") as name:
        tmp = Path(name); staged_db = tmp / database.name; staged_raw = Path(str(staged_db) + ".raw")
        shutil.copy2(bundle / "database.sqlite", staged_db); _fail("restore_db_copy", failure_hooks)
        if (bundle / "raw").exists(): shutil.copytree(bundle / "raw", staged_raw)
        _fail("restore_artifact_copy", failure_hooks)
        restored = SQLiteStore(staged_db, staged_raw)
        for row in restored.db.execute("SELECT source_id,version,artifact FROM raw_records").fetchall():
            restored.db.execute("UPDATE raw_records SET artifact=? WHERE source_id=? AND version=?", (str(staged_raw / Path(row["artifact"]).name), row["source_id"], row["version"]))
        restored.db.commit(); restored.validate_artifact_links(); restored.db.close()
        _fail("restore_promotion", failure_hooks)
        old_db = database.with_name(f".{database.name}.previous")
        old_raw = Path(str(old_db) + ".raw")
        if old_db.exists(): old_db.unlink()
        if old_raw.exists(): shutil.rmtree(old_raw)
        if database.exists(): database.rename(old_db)
        live_raw = Path(str(database) + ".raw")
        if live_raw.exists(): live_raw.rename(old_raw)
        try:
            staged_db.rename(database)
            if staged_raw.exists(): staged_raw.rename(live_raw)
            promoted = sqlite3.connect(database)
            for row in promoted.execute("SELECT source_id,version,artifact FROM raw_records").fetchall():
                promoted.execute("UPDATE raw_records SET artifact=? WHERE source_id=? AND version=?", (str(live_raw / Path(row[2]).name), row[0], row[1]))
            promoted.commit(); promoted.close()
        except Exception:
            if database.exists(): database.unlink()
            if live_raw.exists(): shutil.rmtree(live_raw)
            if old_db.exists(): old_db.rename(database)
            if old_raw.exists(): old_raw.rename(live_raw)
            raise


def _answerer_from_args(command, model=None, endpoint=None, timeout=None,
                        openai_model=None, openai_timeout=None, openai_retries=None):
    """Build answer provider only from explicit serve flags; never discover config."""
    if command != "serve" and any(value is not None for value in (model, endpoint, timeout, openai_model, openai_timeout, openai_retries)):
        raise ValueError("Ollama flags are supported only with serve")
    if any(value is not None for value in (openai_model, openai_timeout, openai_retries)):
        if any(value is not None for value in (model, endpoint, timeout)):
            raise ValueError("OpenAI and Ollama answerers cannot both be configured")
        if openai_model is None:
            raise ValueError("--openai-model is required to activate OpenAI")
        openai_timeout = 30.0 if openai_timeout is None else openai_timeout
        openai_retries = 2 if openai_retries is None else openai_retries
        if not math.isfinite(openai_timeout) or openai_timeout <= 0 or openai_timeout > 120:
            raise ValueError("--openai-timeout must be greater than 0 and at most 120 seconds")
        if openai_retries < 0 or openai_retries > 5:
            raise ValueError("--openai-retries must be between 0 and 5")
        return OpenAIAnswerer(openai_model, openai_timeout, openai_retries)
    if model is None:
        if endpoint is not None or timeout is not None:
            raise ValueError("--ollama-model is required to activate Ollama")
        return None
    if not model.strip() or len(model) > 128 or any(ord(char) < 32 for char in model):
        raise ValueError("--ollama-model must be 1-128 printable characters")
    if timeout is None:
        timeout = 10.0
    if not math.isfinite(timeout) or timeout <= 0 or timeout > 120:
        raise ValueError("--ollama-timeout must be greater than 0 and at most 120 seconds")
    if endpoint is None:
        endpoint = "http://127.0.0.1:11434/api/generate"
    parsed = urlsplit(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("--ollama-endpoint must be loopback HTTP")
    return OllamaAnswerer(endpoint=endpoint, model=model, timeout_seconds=timeout)


def _serve_startup_output(address, mode, token, cloud_answerer=False):
    """Return safe, copyable startup guidance for local/reference servers."""
    lines = [f"serving on {address}"]
    if mode in {"demo", "mock"}:
        lines.extend((
            f"local-only Bearer token (valid until server stops): {token}",
            f"API use: Authorization: Bearer {token}",
            "Browser use: open local UI; it receives an HttpOnly kb_session cookie.",
        ))
    else:
        lines.append("production auth: use configured OIDC Bearer token; no local token issued")
    if cloud_answerer:
        lines.append("WARNING: OpenAI mode sends bounded query/evidence to cloud; do not use sensitive data")
    return "\n".join(lines)


def _vision_from_args(command, model=None, endpoint=None, timeout=None):
    if command not in {"index", "vision-reextract"} and any(value is not None for value in (model, endpoint, timeout)):
        raise ValueError("vision flags are supported only with index or vision-reextract")
    if model is None:
        if endpoint is not None or timeout is not None:
            raise ValueError("--vision-model is required to activate vision")
        return None
    if not model.strip() or len(model) > 128 or any(ord(char) < 32 for char in model):
        raise ValueError("--vision-model must be 1-128 printable characters")
    timeout = 10.0 if timeout is None else timeout
    if not math.isfinite(timeout) or timeout <= 0 or timeout > 120:
        raise ValueError("--vision-timeout must be greater than 0 and at most 120 seconds")
    endpoint = endpoint or "http://127.0.0.1:11434/api/chat"
    return LocalOllamaVisionObserver(endpoint=endpoint, model=model, timeout_seconds=timeout)


def _semantic_from_args(command, model=None, endpoint=None, timeout=None):
    if command not in {"serve", "semantic-reindex"} and any(value is not None for value in (model, endpoint, timeout)):
        raise ValueError("semantic flags are supported only with serve or semantic-reindex")
    if model is None:
        if command == "semantic-reindex": raise ValueError("--semantic-model is required for semantic-reindex")
        if endpoint is not None or timeout is not None: raise ValueError("--semantic-model is required to activate semantic retrieval")
        return None
    timeout = 10.0 if timeout is None else timeout
    if not math.isfinite(timeout) or timeout <= 0 or timeout > 120:
        raise ValueError("--semantic-timeout must be greater than 0 and at most 120 seconds")
    endpoint = endpoint or "http://127.0.0.1:11434/api/embed"
    return OllamaEmbedder(model=model, endpoint=endpoint, timeout_seconds=timeout)


def _semantic_reindex(database, embedder, full=False, batch_size=16):
    store = SQLiteStore(database)
    docs = tuple(doc for doc in store.all() if not doc.tombstoned)
    existing = {row["document_id"]: row for row in store.embedding_rows(embedder.model)}
    pending = [doc for doc in docs if full or not (existing.get(doc.document_id) and existing[doc.document_id]["version"] == doc.source.version and existing[doc.document_id]["input_hash"] == input_hash(doc.title, doc.text))]
    count = 0
    for offset in range(0, len(pending), batch_size):
        group = pending[offset:offset + batch_size]
        vectors = embedder.embed(tuple(f"{doc.title}\n{doc.text}" for doc in group))
        if len(vectors) != len(group): raise ValueError("embedding provider returned wrong batch size")
        for doc, vector in zip(group, vectors):
            if store.save_embedding(doc, embedder.model, vector, input_hash(doc.title, doc.text)): count += 1
    return {"model": embedder.model, "documents": len(docs), "embedded": count, "full": full}


def main():
    p = argparse.ArgumentParser(); p.add_argument("command", choices=["serve", "index", "rebuild", "index-rebuild", "semantic-reindex", "vision-reextract", "backup", "restore", "pilot-evidence"]); p.add_argument("database", type=Path); p.add_argument("target", type=Path, nargs="?"); p.add_argument("--source-root", type=Path, default=Path.cwd()); p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=8080); p.add_argument("--mode", choices=["demo", "mock", "production"], default="demo"); p.add_argument("--result-json", type=Path, help="validated QA result JSON (required for pilot-evidence)"); p.add_argument("--ollama-model", help="explicitly activate loopback Ollama answerer"); p.add_argument("--ollama-endpoint"); p.add_argument("--ollama-timeout", type=float); p.add_argument("--openai-model", help="explicitly activate OpenAI Responses answerer; requires OPENAI_API_KEY"); p.add_argument("--openai-timeout", type=float); p.add_argument("--openai-retries", type=int); p.add_argument("--vision-model"); p.add_argument("--vision-endpoint"); p.add_argument("--vision-timeout", type=float); p.add_argument("--semantic-model"); p.add_argument("--semantic-endpoint"); p.add_argument("--semantic-timeout", type=float); p.add_argument("--semantic-full", "--full", dest="semantic_full", action="store_true")
    a = p.parse_args()
    try:
        answerer = _answerer_from_args(a.command, a.ollama_model, a.ollama_endpoint, a.ollama_timeout, a.openai_model, a.openai_timeout, a.openai_retries)
        vision_observer = _vision_from_args(a.command, a.vision_model, a.vision_endpoint, a.vision_timeout)
        semantic_embedder = _semantic_from_args(a.command, a.semantic_model, a.semantic_endpoint, a.semantic_timeout)
    except ValueError as exc:
        p.error(str(exc))
    if a.command == "semantic-reindex":
        try: print(json.dumps(_semantic_reindex(a.database, semantic_embedder, a.semantic_full), sort_keys=True, indent=2))
        except Exception as exc: p.error(f"semantic reindex failed: {exc}")
        return
    if a.command == "vision-reextract":
        if vision_observer is None: p.error("--vision-model is required for vision-reextract")
        app = compose(RuntimeConfig(a.database, a.source_root, vision_observer=vision_observer))
        print(json.dumps(app.service.reextract_images(vision_observer, a.semantic_full), sort_keys=True, indent=2))
        return
    if a.command in {"serve", "index", "rebuild"}:
        identity_provider = None
        if a.mode == "production":
            issuer, audience, jwks_url = (os.environ.get(name) for name in ("OIDC_ISSUER", "OIDC_AUDIENCE", "OIDC_JWKS_URL"))
            if not all((issuer, audience, jwks_url)):
                p.error("production requires OIDC_ISSUER, OIDC_AUDIENCE, and OIDC_JWKS_URL")
            assert issuer is not None and audience is not None and jwks_url is not None
            identity_provider = ManagedOIDCValidator(issuer, audience, jwks_url)
        config = RuntimeConfig(a.database, a.source_root, a.host, a.port, a.mode, frontend_root=Path(__file__).parents[1] / "frontend", answerer=answerer, vision_observer=vision_observer, semantic_embedder=semantic_embedder, identity_provider=identity_provider, oidc_issuer=os.environ.get("OIDC_ISSUER"), oidc_audience=os.environ.get("OIDC_AUDIENCE"), oidc_jwks_url=os.environ.get("OIDC_JWKS_URL")); app = compose(config); print(config.status["banner"], flush=True) if config.mode == "mock" else None
        if a.command == "serve":
            server, token = create_server(app.service, a.host, a.port, frontend_root=config.frontend_root, max_query_chars=config.max_query_chars, max_results=config.max_results, identity_provider=config.identity_provider, production=config.mode == "production")
            print(_serve_startup_output(f"{server.server_address[0]}:{server.server_address[1]}", config.mode, token, isinstance(answerer, OpenAIAnswerer)), flush=True)
            server.serve_forever()
        else:
            if a.command == "index": app.service.reconcile(app.connector, "startup")
            app.store.rebuild_index()
    elif a.command == "index-rebuild": SQLiteStore(a.database).rebuild_index()
    elif a.command == "backup": _backup(a.database, a.target) if a.target else p.error("target required")
    elif a.command == "restore": _restore(a.database, a.target) if a.target else p.error("target required")
    else:
        if not a.result_json:
            p.error("pilot-evidence refuses fabricated defaults; --result-json is required")
        try:
            evidence = validate_evidence(json.loads(a.result_json.read_text()))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            p.error(f"invalid QA evidence: {exc}")
        print(json.dumps(evidence, sort_keys=True, indent=2))

if __name__ == "__main__": main()
