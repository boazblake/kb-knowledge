"""Evidence validator for checked-in P1/P2 Given/When/Then traceability."""
import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
LEDGER = ROOT / "docs/evidence/phase4-qa-bdd-ledger-2026-08-15.json"
SPEC = ROOT / "docs/specs/phase4-p1-p2-backend.feature.md"
TESTED_COMMIT = "397911e01029c8e626d98b9661263f8a2f7ff00c"
EXPECTED_RUNTIME = {
    "nix_python": "Python 3.11.11",
    "node": "v22.16.0",
    "postgres": "PostgreSQL 16 disposable local instance",
    "browser": "HeadlessChrome 149",
}
EXPECTED_SCHEMA = {
    "migration": "migrations/006_phase4_projection.sql",
    "schema_claim": "Phase 4 dev/mock projection, FTS, checkpoint, and identity-alias schema",
}
EXPECTED_COMMANDS = [
    "nix develop --command bash -s (Phase 4 protocol)",
    "initdb --no-locale --encoding=UTF8 -D <temporary evidence>/pgdata",
    "pg_ctl <temporary evidence>/pgdata -o <temporary socket and port> start",
    "python - <<PY MigrationRunner().run(connection) [pass 1]",
    "python - <<PY MigrationRunner().run(connection) [pass 2]",
    "P3_POSTGRES_DSN=<redacted> python -m unittest discover -s tests -p 'test*.py' -v",
    "P3_POSTGRES_DSN=<redacted> python -m unittest tests.test_p4_core tests.test_p4_postgres_integration -v",
    "python -m compileall -q kb_pipeline tests",
    "node --check frontend/*.js",
    "agent-browser open http://127.0.0.1:8769/project-visualization.html",
    "agent-browser snapshot -i --json",
    "agent-browser network requests",
]
EXPECTED_EVIDENCE_REVISION = "phase4-20260815T214315Z-38130-r2"


def validate_phase4_ledger(ledger, current_commit):
    """Validate provenance without requiring evidence metadata to be code."""
    required = {
        "production_qualification", "tested_commit", "evidence_revision",
        "tested_tree_status", "runtime", "schema_scope", "temporary_evidence",
        "artifact_metadata",
    }
    missing = required - set(ledger)
    if missing:
        raise AssertionError(f"ledger missing provenance fields: {', '.join(sorted(missing))}")
    if ledger["production_qualification"] is not False:
        raise AssertionError("evidence must remain non-production")
    if ledger["tested_commit"] != TESTED_COMMIT:
        raise AssertionError("ledger must identify exact tested code commit")
    if not re.fullmatch(r"[0-9a-f]{40}", ledger["tested_commit"]):
        raise AssertionError("tested_commit must be full Git object ID")
    if ledger["tested_commit"] == current_commit:
        raise AssertionError("tested_commit cannot self-reference future ledger HEAD")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ledger["tested_commit"], current_commit],
        cwd=ROOT,
    )
    if ancestor.returncode != 0:
        raise AssertionError("tested_commit must be an ancestor of current HEAD")
    if ledger["tested_tree_status"] != "clean":
        raise AssertionError("execution must come from clean code tree")
    if ledger["evidence_revision"] != EXPECTED_EVIDENCE_REVISION:
        raise AssertionError("evidence revision must identify current ledger artifact history")
    if ledger["runtime"] != EXPECTED_RUNTIME:
        raise AssertionError("runtime evidence must match recorded execution")
    if ledger["schema_scope"] != EXPECTED_SCHEMA:
        raise AssertionError("schema evidence must match recorded migration")
    commands = ledger["temporary_evidence"]["commands"]
    if commands != EXPECTED_COMMANDS:
        raise AssertionError("commands must match exact recorded execution")
    artifact = ledger["artifact_metadata"]
    if artifact["path"] != "docs/evidence/phase4-qa-bdd-ledger-2026-08-15.json":
        raise AssertionError("artifact path must identify checked-in ledger")
    if artifact.get("artifact_commit") is not None:
        if not re.fullmatch(r"[0-9a-f]{40}", artifact["artifact_commit"]):
            raise AssertionError("artifact_commit must be full Git object ID")
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", artifact["artifact_commit"], current_commit],
            cwd=ROOT,
        )
        if result.returncode != 0:
            raise AssertionError("artifact_commit must be an ancestor of current HEAD")


class Phase4EvidenceTests(unittest.TestCase):
    def test_phase4_bdd_evidence_validator(self):
        ledger = json.loads(LEDGER.read_text())
        spec = SPEC.read_text()
        current_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        validate_phase4_ledger(ledger, current_commit)
        self.assertEqual(ledger["tested_commit"], TESTED_COMMIT)
        self.assertEqual(ledger["evidence_revision"], EXPECTED_EVIDENCE_REVISION)
        expected = {f"E2E-{i:03d}" for i in range(1, 11)} | {f"P4-{i:02d}" for i in range(1, 12)}
        self.assertEqual(expected, {item["id"] for item in ledger["runs"]})
        self.assertEqual(expected, set(re.findall(r"\b(?:E2E-\d{3}|P4-\d{2})\b", spec)))
        for run in ledger["runs"]:
            self.assertIn(run["status"], {"pass", "fail"})
            self.assertIsInstance(run["evidence"], str)
            self.assertTrue(run["evidence"].strip())
        for name in ("test_e2e001_authority_commit_outbox_projection_barrier_query",
                     "test_e2e002_duplicate_same_revision_conflict_full_identity_tuple",
                     "test_e2e003_gap_quarantine_recovery", "test_e2e004_delete_no_resurrection",
                     "test_e2e006_citation_tombstone_source_scope_rejection",
                     "test_p4011_dlq_replay_authorized_vs_unauthorized_principal",
                     "test_replay_envelope_serialization_round_trip",
                     "test_e2e007_p4_09_retry_bounded_dlq_authorized_recovery_and_tombstone"):
            self.assertIn(name, spec)

    def test_phase4_validator_rejects_unrelated_tested_commit(self):
        ledger = json.loads(LEDGER.read_text())
        ledger["tested_commit"] = "0" * 40
        with self.assertRaises(AssertionError):
            validate_phase4_ledger(ledger, "f" * 40)

    def test_phase4_validator_rejects_self_referential_commit(self):
        ledger = json.loads(LEDGER.read_text())
        with self.assertRaises(AssertionError):
            validate_phase4_ledger(ledger, ledger["tested_commit"])

    def test_phase4_validator_rejects_dirty_execution_tree(self):
        ledger = json.loads(LEDGER.read_text())
        ledger["tested_tree_status"] = "dirty-uncommitted"
        current_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        with self.assertRaises(AssertionError):
            validate_phase4_ledger(ledger, current_commit)
