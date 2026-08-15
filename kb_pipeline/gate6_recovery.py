"""Bounded synthetic-local Gate 6 backup/restore recovery rehearsal."""

from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .cli import _backup, _restore, _validate_bundle
from .composition import RuntimeConfig, compose
from .domain import ACL, Input
from .storage import SQLiteStore


SCHEMA = "kb-pipeline.gate6-recovery.v1"
MAX_RECORDS = 1_000
DEFAULT_RECORDS_A = 20
DEFAULT_RECORDS_B = 10
DEFAULT_RTO_HOURS = 4.0
DEFAULT_RPO_HOURS = 24.0


def _count(value: int, name: str) -> int:
    if value < 1 or value > MAX_RECORDS:
        raise ValueError(f"{name} must be between 1 and {MAX_RECORDS}")
    return value


def compare_recovery(rto_hours: float, rpo_hours: float,
                     rto_target_hours: float = DEFAULT_RTO_HOURS,
                     rpo_target_hours: float = DEFAULT_RPO_HOURS) -> dict:
    return {
        "rto": {"observed_hours": rto_hours, "target_hours": rto_target_hours,
                "operator": "<=", "status": "pass" if rto_hours <= rto_target_hours else "fail"},
        "rpo": {"observed_hours": rpo_hours, "target_hours": rpo_target_hours,
                "operator": "<=", "status": "pass" if rpo_hours <= rpo_target_hours else "fail"},
    }


def validate_recovery_sentinels(service, batch_a_queries: tuple[str, ...],
                                batch_b_queries: tuple[str, ...]) -> dict:
    """Check durable retrieval/search for A and absence of post-watermark B."""
    a_retrievable = True
    for query in batch_a_queries:
        hits = service.search(query, "reader")
        a_retrievable &= bool(hits) and all(service.store.get(hit.document_id) is not None for hit in hits)
    b_absent = all(not service.search(query, "reader") for query in batch_b_queries)
    return {"batch_a_retrievable": a_retrievable, "batch_b_absent": b_absent}


def validate_result(result: dict) -> dict:
    if not isinstance(result, dict) or result.get("schema") != SCHEMA:
        raise ValueError(f"result schema must be {SCHEMA}")
    required = {"schema", "gate", "harness", "environment", "watermark", "measurements",
                "checks", "comparisons", "overall_status", "scope"}
    missing = required - set(result)
    if missing:
        raise ValueError(f"missing result fields: {', '.join(sorted(missing))}")
    if result["gate"] != 6 or result["harness"].get("mode") != "synthetic-local":
        raise ValueError("result must identify Gate 6 synthetic-local recovery")
    required_checks = {"sqlite_integrity", "raw_artifact_links", "batch_a_retrieval_search", "batch_b_absence"}
    if set(result["checks"]) != required_checks or any(value not in {"pass", "fail"} for value in result["checks"].values()):
        raise ValueError("checks must contain exact recovery sentinels")
    if set(result["comparisons"]) != {"rto", "rpo"} or any(value.get("status") not in {"pass", "fail"} for value in result["comparisons"].values()):
        raise ValueError("comparisons must contain RTO and RPO statuses")
    if result["overall_status"] not in {"pass", "fail", "incomplete"}:
        raise ValueError("overall_status must be pass, fail, or incomplete")
    if result["scope"].get("production_qualification") is not False:
        raise ValueError("result must disclaim production qualification")
    return result


def run_rehearsal(records_a: int = DEFAULT_RECORDS_A, records_b: int = DEFAULT_RECORDS_B) -> dict:
    records_a, records_b = _count(records_a, "records_a"), _count(records_b, "records_b")
    with tempfile.TemporaryDirectory(prefix="kb-gate6-recovery-") as directory:
        root = Path(directory)
        live_db = root / "live.sqlite"
        bundle = root / "backup"
        target_db = root / "restored.sqlite"
        app = compose(RuntimeConfig(live_db, root))
        acl = ACL(frozenset({"reader"}), frozenset())
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)

        def batch(prefix: str, count: int, observed_at: datetime) -> tuple[Input, ...]:
            return tuple(Input("synthetic", f"{prefix}-{i}",
                               f"gate6-{prefix}-sentinel-{i}".encode(),
                               f"file:synthetic/{prefix}/{i}", observed_at, permissions=acl)
                         for i in range(count))

        batch_a = batch("batch-a", records_a, base)
        batch_b = batch("batch-b", records_b, base + timedelta(hours=1))
        for item in batch_a:
            app.service.ingest(item, "gate6-recovery-a")
        watermark = {"ledger_sequence": app.service.health()["ledger_sequence"],
                     "observed_at": max(item.observed_at for item in batch_a).isoformat()}
        _backup(live_db, bundle)
        for item in batch_b:
            app.service.ingest(item, "gate6-recovery-b")

        restore_started = time.perf_counter()
        _restore(target_db, bundle)
        integrity = sqlite3.connect(target_db).execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        restored_store = SQLiteStore(target_db, Path(str(target_db) + ".raw"))
        links = restored_store.validate_artifact_links() is True
        restored = compose(RuntimeConfig(target_db, root))
        a_queries = tuple(item.payload.decode() for item in batch_a)
        b_queries = tuple(item.payload.decode() for item in batch_b)
        sentinels = validate_recovery_sentinels(restored.service, a_queries, b_queries)
        rto_hours = (time.perf_counter() - restore_started) / 3600
        rpo_hours = (max(item.observed_at for item in batch_b) - max(item.observed_at for item in batch_a)).total_seconds() / 3600
        checks = {"sqlite_integrity": "pass" if integrity else "fail",
                  "raw_artifact_links": "pass" if links else "fail",
                  "batch_a_retrieval_search": "pass" if sentinels["batch_a_retrievable"] else "fail",
                  "batch_b_absence": "pass" if sentinels["batch_b_absent"] else "fail"}
        comparisons = compare_recovery(rto_hours, rpo_hours)
        result = {
            "schema": SCHEMA, "gate": 6,
            "harness": {"mode": "synthetic-local", "bounded": True,
                         "records_a": records_a, "records_b": records_b},
            "environment": {"python": platform.python_version(), "platform": platform.platform()},
            "watermark": watermark,
            "measurements": {"restore": {"rto_hours": rto_hours},
                             "rpo": {"lost_record_count": records_b,
                                     "time_window_hours": rpo_hours,
                                     "status": "derived_from_post_watermark_absence",
                                     "backup_duration_excluded": True}},
            "checks": checks, "comparisons": comparisons,
            "overall_status": "pass" if all(value == "pass" for value in checks.values()) and all(value["status"] == "pass" for value in comparisons.values()) else "fail",
            "scope": {"production_qualification": False,
                      "limitations": ["synthetic local process and filesystem only",
                                       "excludes production disaster recovery and infrastructure failure scenarios",
                                       "RPO is lost-record/time-window assessment, not backup duration"]},
        }
    return validate_result(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run bounded synthetic-local Gate 6 recovery rehearsal")
    parser.add_argument("--records-a", type=int, default=DEFAULT_RECORDS_A)
    parser.add_argument("--records-b", type=int, default=DEFAULT_RECORDS_B)
    args = parser.parse_args(argv)
    try:
        result = run_rehearsal(args.records_a, args.records_b)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["overall_status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
