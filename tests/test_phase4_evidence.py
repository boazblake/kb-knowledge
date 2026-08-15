"""Evidence validator for checked-in P1/P2 Given/When/Then traceability."""
import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
LEDGER = ROOT / "docs/evidence/phase4-qa-bdd-ledger-2026-08-15.json"
SPEC = ROOT / "docs/specs/phase4-p1-p2-backend.feature.md"


class Phase4EvidenceTests(unittest.TestCase):
    def test_phase4_bdd_evidence_validator(self):
        ledger = json.loads(LEDGER.read_text())
        spec = SPEC.read_text()
        current_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        self.assertIs(ledger["production_qualification"], False)
        self.assertEqual(0, subprocess.run(
            ["git", "merge-base", "--is-ancestor", ledger["commit"], current_commit],
            cwd=ROOT,
        ).returncode)
        self.assertEqual("migrations/006_phase4_projection.sql", ledger["schema_scope"]["migration"])
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
                     "test_p4011_dlq_replay_authorized_vs_unauthorized_principal"):
            self.assertIn(name, spec)
