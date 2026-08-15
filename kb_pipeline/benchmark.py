"""Supported-runtime synthetic load and SLO measurement harness.

This module emits local/simulated evidence only. It uses project service APIs and
stdlib process counters; it does not export telemetry or qualify production.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

from .composition import RuntimeConfig, compose
from .domain import Input

SCHEMA = "kb-pipeline.slo-evidence.v1"
HARNESS_VERSION = "0.1.0"
WINDOW_DAYS = 30

@dataclass(frozen=True)
class SLODefaults:
    availability: float = 0.999
    search_p95_ms: float = 100.0
    ingest_records_per_second: float = 100.0
    freshness_max_seconds: float = 300.0
    purge_max_seconds: float = 3600.0

@dataclass(frozen=True)
class Summary:
    count: int
    errors: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    throughput_per_second: float
    error_rate: float

def percentile(values: Iterable[float], percentile_value: float) -> float:
    values = sorted(float(v) for v in values)
    if not values:
        return 0.0
    rank = (len(values) - 1) * percentile_value / 100
    low, high = int(rank), min(int(rank) + 1, len(values) - 1)
    return round(values[low] + (values[high] - values[low]) * (rank - low), 6)

def summarize(latencies_ms: Iterable[float], errors: int, elapsed_seconds: float) -> Summary:
    values = tuple(latencies_ms)
    count = len(values) + errors
    return Summary(count, errors, percentile(values, 50), percentile(values, 95),
                   percentile(values, 99), count / elapsed_seconds if elapsed_seconds > 0 else 0.0,
                   errors / count if count else 1.0)

def error_budget(slo: float, observed_bad_fraction: float) -> dict:
    budget = 1.0 - slo
    burn = observed_bad_fraction / budget if budget else float("inf")
    burn_rate = round(burn, 6)
    return {"slo": slo, "budget_fraction": round(budget, 12),
            "budget_minutes_30d": round(budget * WINDOW_DAYS * 24 * 60, 6),
            "observed_bad_fraction": observed_bad_fraction, "burn_rate": burn_rate,
            "burn_alerts": {"fast_1h": burn_rate >= 5.0, "slow_6h": burn_rate >= 2.0},
            "within_budget": observed_bad_fraction <= budget}

def compare_slos(search: Summary, ingest: Summary, *, freshness_seconds: float,
                 purge_seconds: float, defaults: SLODefaults = SLODefaults(),
                 dependency_checks: dict | None = None) -> dict:
    availability = 1.0 - max(search.error_rate, ingest.error_rate)
    checks = {
        "availability": availability >= defaults.availability,
        "search_p95": search.p95_ms <= defaults.search_p95_ms,
        "ingest_throughput": ingest.throughput_per_second >= defaults.ingest_records_per_second,
        "freshness": freshness_seconds <= defaults.freshness_max_seconds,
        "purge_sla": purge_seconds <= defaults.purge_max_seconds,
    }
    if dependency_checks:
        checks["authority_dependencies"] = all(dependency_checks.values())
    return {
        "approved_defaults": asdict(defaults),
        "measurement_window_model": {"days": WINDOW_DAYS, "type": "rolling",
                                      "note": "single run is not 30-day evidence"},
        "checks": checks,
        "observed": {"availability": availability, "search": asdict(search),
                     "ingest": asdict(ingest), "freshness_seconds": freshness_seconds,
                     "purge_seconds": purge_seconds},
        "error_budgets": {
            "availability": error_budget(defaults.availability, 1.0 - availability),
            "search_errors": error_budget(defaults.availability, search.error_rate),
            "ingest_errors": error_budget(defaults.availability, ingest.error_rate),
        },
    }

def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"

def _sample_process() -> dict:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result = {"cpu_user_seconds": usage.ru_utime, "cpu_system_seconds": usage.ru_stime,
              "max_rss": usage.ru_maxrss, "rss_unit": "bytes" if sys.platform == "darwin" else "KiB",
              "io": "unavailable"}
    try:
        import psutil  # optional ready-made process telemetry, never required
        proc = psutil.Process(os.getpid())
        counters = proc.io_counters()
        result["io"] = {"read_bytes": counters.read_bytes, "write_bytes": counters.write_bytes}
        result["rss_bytes"] = proc.memory_info().rss
    except (ImportError, AttributeError, OSError):
        pass
    return result

def _corpus(root: Path, records: int) -> None:
    root.mkdir()
    for number in range(records):
        (root / f"doc-{number:06d}.txt").write_text(
            f"Synthetic knowledge document {number}. reliability search corpus term-{number % 11}.\n",
            encoding="utf-8")

def _inputs(records: int) -> list[Input]:
    now = datetime.now(timezone.utc)
    return [Input("local-files", f"doc-{n:06d}",
                   f"Synthetic knowledge document {n}. reliability search corpus term-{n % 11}.\n".encode(),
                   f"file:///synthetic/doc-{n:06d}.txt", now, {"synthetic": "true"})
            for n in range(records)]

def _run_calls(fn: Callable[[int], object], count: int, concurrency: int) -> tuple[Summary, list[str]]:
    latencies, errors = [], []
    started = time.perf_counter()
    lock = threading.Lock()
    def call(index: int) -> None:
        at = time.perf_counter()
        try:
            fn(index)
            value = (time.perf_counter() - at) * 1000
            with lock: latencies.append(value)
        except Exception as exc:
            with lock: errors.append(type(exc).__name__)
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(call, range(count)))
    return summarize(latencies, len(errors), time.perf_counter() - started), errors

def run_harness(records: int = 200, searches: int = 200, concurrency: int = 1,
                warmup: int = 0, authority_fresh: bool = False, freshness_seconds: float = 0.0) -> dict:
    if min(records, searches, concurrency, warmup) < 0 or concurrency < 1:
        raise ValueError("records, searches, warmup must be non-negative; concurrency must be positive")
    started_at = datetime.now(timezone.utc)
    process_before = _sample_process()
    with tempfile.TemporaryDirectory(prefix="kb-slo-") as directory:
        root, db = Path(directory) / "corpus", Path(directory) / "state.sqlite"
        _corpus(root, records)
        app = compose(RuntimeConfig(db, root, port=0, max_projection_lag=0))
        corpus = _inputs(records)
        for item in corpus[:warmup]:
            app.service.ingest(item, "slo-warmup")
        measured_corpus = corpus[warmup:]
        ingest, ingest_errors = _run_calls(lambda i: app.service.ingest(measured_corpus[i], "slo-ingest"),
                                           len(measured_corpus), concurrency)
        queries = ["reliability", "knowledge", "term-3", "search"]
        search, search_errors = _run_calls(lambda i: app.service.search(queries[i % len(queries)], "reader"),
                                           searches, concurrency)
        purge_seconds = 0.0
        if corpus:
            doc = app.store.all()[0]
            app.service.tombstone(doc.document_id, "slo-purge")
            purge_at = time.perf_counter()
            app.service.purge(datetime.now(timezone.utc) + timedelta(seconds=1), actor="slo-purge")
            purge_seconds = time.perf_counter() - purge_at
        readiness = app.service.readiness()
        health = app.service.health()
    process_after = _sample_process()
    dependency_checks = {"authority_fresh": authority_fresh, "freshness_dependency": freshness_seconds <= SLODefaults().freshness_max_seconds}
    comparison = compare_slos(search, ingest, freshness_seconds=freshness_seconds,
                              purge_seconds=purge_seconds, dependency_checks=dependency_checks)
    readiness_checks = dict(readiness.get("checks", {}), **dependency_checks)
    ready = readiness.get("status") == "ready" and all(readiness_checks.values()) and all(comparison["checks"].values())
    ended_at = datetime.now(timezone.utc)
    return {
        "schema": SCHEMA, "harness_version": HARNESS_VERSION, "result_class": "synthetic-local-simulated",
        "qualification": "not_production_qualification", "readiness": "ready" if ready else "not_ready",
        "readiness_reason": "fail-closed: authority/freshness dependencies must be fresh and authoritative" if not ready else "all local checks passed; production still unqualified",
        "timestamps": {"started_at": started_at.isoformat(), "ended_at": ended_at.isoformat()},
        "evidence_manifest": {"commit": _git_commit(), "runtime": {"python": sys.version, "executable": sys.executable, "platform": platform.platform()},
                              "topology": {"mode": "demo", "backend": "SQLite FTS5", "external_telemetry": False},
                              "workload": {"records": records, "searches": searches, "concurrency": concurrency, "warmup": warmup, "corpus": "deterministic synthetic"},
                              "timestamps": {"started_at": started_at.isoformat(), "ended_at": ended_at.isoformat()}},
        "workloads": {"ingest": {"definition": "synthetic records through KnowledgeService.ingest", "warmup": warmup},
                       "search": {"definition": "lexical queries through KnowledgeService.search", "queries": ["reliability", "knowledge", "term-3", "search"]},
                       "controls": {"warmup_records": warmup, "cold": warmup == 0, "concurrency": concurrency}},
        "metrics": {"ingest": asdict(ingest), "search": asdict(search),
                    "queue_lag": {"outbox_pending": health.get("outbox_pending", 0),
                                  "outbox_failed": health.get("outbox_failed", 0)},
                    "projection_lag": health.get("projection_lag", {}),
                    "max_projection_lag": max(health.get("projection_lag", {}).values(), default=0),
                    "errors": {"ingest": ingest_errors, "search": search_errors},
                    "process_before": process_before, "process_after": process_after,
                    "resource_capture": "stdlib resource; optional psutil IO/RSS when installed"},
        "slo_comparison": comparison,
    }

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic local SLO harness; never production qualification")
    parser.add_argument("--records", type=int, default=200)
    parser.add_argument("--searches", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=0, help="records ingested before measured run; 0=cold")
    parser.add_argument("--authority-fresh", action="store_true", help="declare synthetic authority dependency fresh")
    parser.add_argument("--freshness-seconds", type=float, default=0.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = run_harness(args.records, args.searches, args.concurrency, args.warmup, args.authority_fresh, args.freshness_seconds)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
