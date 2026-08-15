import unittest
from types import SimpleNamespace

from kb_pipeline.gate6_recovery import SCHEMA, compare_recovery, validate_recovery_sentinels, validate_result


class Gate6RecoveryTests(unittest.TestCase):
    def test_recovery_comparisons_are_deterministic(self):
        self.assertEqual("pass", compare_recovery(0.1, 1)["rto"]["status"])
        self.assertEqual("pass", compare_recovery(4, 24)["rpo"]["status"])
        self.assertEqual("fail", compare_recovery(4.1, 24.1)["rto"]["status"])

    def test_sentinel_validation_checks_retrieval_and_absence(self):
        hit = SimpleNamespace(document_id="a")
        service = SimpleNamespace(search=lambda query, identity: [hit] if query == "a" else [],
                                   store=SimpleNamespace(get=lambda document_id: object()))
        self.assertEqual({"batch_a_retrievable": True, "batch_b_absent": True},
                         validate_recovery_sentinels(service, ("a",), ("b",)))

    def test_schema_requires_production_disclaimer_and_sentinels(self):
        result = {"schema": SCHEMA, "gate": 6, "harness": {"mode": "synthetic-local"},
                  "environment": {}, "watermark": {}, "measurements": {},
                  "checks": {"sqlite_integrity": "pass", "raw_artifact_links": "pass",
                              "batch_a_retrieval_search": "pass", "batch_b_absence": "pass"},
                  "comparisons": {"rto": {"status": "pass"}, "rpo": {"status": "pass"}},
                  "overall_status": "pass", "scope": {"production_qualification": False}}
        self.assertIs(validate_result(result), result)
        result["scope"]["production_qualification"] = True
        with self.assertRaises(ValueError):
            validate_result(result)


if __name__ == "__main__":
    unittest.main()
