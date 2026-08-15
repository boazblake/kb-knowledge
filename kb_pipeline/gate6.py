"""Bounded, synthetic-local Gate 6 qualification harness.

This measures this repository's local implementation only.  It does not test
production infrastructure, disaster recovery, or production authentication.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from .api import create_server
from .composition import RuntimeConfig, compose
from .domain import ACL, Input


SCHEMA = "kb-pipeline.gate6-qualification.v2"
MAX_RECORDS = 10_000
MAX_SEARCH_SAMPLES = 1_000
DEFAULT_RECORDS = 1_000
DEFAULT_SEARCH_SAMPLES = 100
DEFAULT_TARGETS = {"ingest_records_per_second": 100.0, "search_p95_ms": 100.0,
                   "rpo_hours": 24.0, "rto_hours": 4.0}


def _bounded(value: int, name: str, maximum: int) -> int:
    if value < 1 or value > maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


def compare_measurements(ingest_rate: float, search_p95_ms: float,
                         rpo_hours: float | None = None,
                         rto_hours: float | None = None,
                         targets: dict[str, float] | None = None) -> dict:
    """Return threshold comparisons; absent recovery measurements stay pending."""
    targets = dict(DEFAULT_TARGETS if targets is None else targets)
    checks = {
        "ingest_throughput": (ingest_rate, targets["ingest_records_per_second"], ">=",
                               ingest_rate >= targets["ingest_records_per_second"]),
        "search_p95": (search_p95_ms, targets["search_p95_ms"], "<=",
                        search_p95_ms <= targets["search_p95_ms"]),
        "rpo": (rpo_hours, targets["rpo_hours"], "<=",
                rpo_hours is not None and rpo_hours <= targets["rpo_hours"]),
        "rto": (rto_hours, targets["rto_hours"], "<=",
                rto_hours is not None and rto_hours <= targets["rto_hours"]),
    }
    return {name: {"observed": observed, "target": target, "operator": operator,
                   "status": "not_measured" if observed is None else ("pass" if passed else "fail")}
            for name, (observed, target, operator, passed) in checks.items()}


def validate_result(result: dict) -> dict:
    """Validate stable machine-readable shape used by CI and result consumers."""
    if not isinstance(result, dict) or result.get("schema") != SCHEMA:
        raise ValueError(f"result schema must be {SCHEMA}")
    required = {"schema", "gate", "harness", "environment", "targets", "measurements",
                "comparisons", "overall_status", "scope"}
    missing = required - set(result)
    if missing:
        raise ValueError(f"missing result fields: {', '.join(sorted(missing))}")
    if result["gate"] != 6 or result["harness"].get("mode") != "synthetic-local":
        raise ValueError("result must identify Gate 6 synthetic-local harness")
    if result["overall_status"] not in {"pass", "fail", "incomplete"}:
        raise ValueError("overall_status must be pass, fail, or incomplete")
    comparisons = result["comparisons"]
    if set(comparisons) != {"ingest_throughput", "search_p95", "rpo", "rto"}:
        raise ValueError("comparisons must cover all four Gate 6 targets")
    if any(item.get("status") not in {"pass", "fail", "not_measured"}
           for item in comparisons.values()):
        raise ValueError("comparison status must be pass, fail, or not_measured")
    statuses = {item["status"] for item in comparisons.values()}
    expected_status = ("incomplete" if "not_measured" in statuses else
                       "pass" if statuses == {"pass"} else "fail")
    if result["overall_status"] != expected_status:
        raise ValueError("overall_status does not match comparison statuses")
    recovery = result["measurements"].get("rpo_rto")
    if not isinstance(recovery, dict) or recovery.get("measured") is not False:
        raise ValueError("synthetic-local harness must identify RPO/RTO as unmeasured")
    if any(comparisons[name]["status"] != "not_measured" for name in ("rpo", "rto")):
        raise ValueError("synthetic-local harness cannot qualify RPO/RTO")
    if result["scope"].get("production_qualification") is not False:
        raise ValueError("result must disclaim production qualification")
    return result


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)]


def run_harness(records: int = DEFAULT_RECORDS, search_samples: int = DEFAULT_SEARCH_SAMPLES,
                targets: dict[str, float] | None = None) -> dict:
    records = _bounded(records, "records", MAX_RECORDS)
    search_samples = _bounded(search_samples, "search_samples", MAX_SEARCH_SAMPLES)
    targets = dict(DEFAULT_TARGETS if targets is None else targets)
    for name in ("rpo_hours", "rto_hours"):
        if targets[name] < 0:
            raise ValueError(f"{name} must be non-negative")

    with tempfile.TemporaryDirectory(prefix="kb-gate6-") as directory:
        root = Path(directory)
        app = compose(RuntimeConfig(root / "database.sqlite", root))
        acl = ACL(frozenset({"reader"}), frozenset())
        inputs = tuple(Input("synthetic", f"record-{i}",
                             f"synthetic gate six record {i}".encode(),
                             f"file:synthetic/{i}",
                             datetime(2024, 1, 1, tzinfo=timezone.utc),
                             permissions=acl) for i in range(records))
        started = time.perf_counter()
        for item in inputs:
            app.service.ingest(item, "gate6-synthetic")
        ingest_elapsed = max(time.perf_counter() - started, 1e-12)

        server, token = create_server(app.service, port=0)
        server_thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        latencies: list[float] = []
        url = f"http://{server.server_address[0]}:{server.server_address[1]}/v1/search?q=synthetic"
        try:
            for _ in range(search_samples):
                started = time.perf_counter()
                with urlopen(Request(url, headers={"Authorization": f"Bearer {token}"})) as response:
                    if response.status != 200:
                        raise RuntimeError(f"authenticated search returned HTTP {response.status}")
                    response.read()
                latencies.append((time.perf_counter() - started) * 1000)
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=2)

    ingest_rate = records / ingest_elapsed
    search_p95 = _p95(latencies)
    comparisons = compare_measurements(ingest_rate, search_p95,
                                        targets=targets)
    result = {
        "schema": SCHEMA,
        "gate": 6,
        "harness": {"mode": "synthetic-local", "bounded": True,
                     "records": records, "search_samples": search_samples},
        "environment": {"python": platform.python_version(),
                        "implementation": platform.python_implementation(),
                        "platform": platform.platform()},
        "targets": targets,
        "measurements": {
            "ingest": {"records": records, "elapsed_seconds": ingest_elapsed,
                        "records_per_second": ingest_rate},
            "authenticated_api_search": {"samples": search_samples,
                                          "p95_ms": search_p95},
            "rpo_rto": {"rpo_hours": None, "rto_hours": None,
                        "status": "not_measured", "measured": False},
        },
        "comparisons": comparisons,
        "overall_status": ("incomplete" if any(item["status"] == "not_measured"
                                                for item in comparisons.values())
                           else "pass" if all(item["status"] == "pass"
                                              for item in comparisons.values())
                           else "fail"),
        "scope": {"production_qualification": False,
                  "limitations": ["synthetic local process and loopback HTTP only",
                                   "RPO/RTO are declared targets, not measured success",
                                   "does not qualify production SRE behavior"]},
    }
    return validate_result(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run bounded synthetic-local Gate 6 harness")
    parser.add_argument("--records", type=int, default=DEFAULT_RECORDS)
    parser.add_argument("--search-samples", type=int, default=DEFAULT_SEARCH_SAMPLES)
    args = parser.parse_args(argv)
    try:
        result = run_harness(args.records, args.search_samples)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["overall_status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
