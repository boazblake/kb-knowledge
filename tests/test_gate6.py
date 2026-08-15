import unittest

from kb_pipeline.gate6 import SCHEMA, compare_measurements, run_harness, validate_result


class Gate6HarnessTests(unittest.TestCase):
    def test_comparison_logic_is_deterministic(self):
        comparisons = compare_measurements(100.0, 100.0)
        self.assertEqual("not_measured", comparisons["rpo"]["status"])
        self.assertEqual("not_measured", comparisons["rto"]["status"])
        self.assertEqual({"pass"}, {comparisons[name]["status"] for name in
                                     ("ingest_throughput", "search_p95")})
        failed = compare_measurements(99.9, 100.1, rpo_hours=24.1, rto_hours=4.1)
        self.assertEqual("fail", failed["ingest_throughput"]["status"])
        self.assertEqual("fail", failed["search_p95"]["status"])
        self.assertEqual("fail", failed["rpo"]["status"])
        self.assertEqual("fail", failed["rto"]["status"])

    def test_harness_does_not_claim_declared_recovery_targets_passed(self):
        result = run_harness(records=1, search_samples=1)
        self.assertEqual("not_measured", result["comparisons"]["rpo"]["status"])
        self.assertEqual("not_measured", result["comparisons"]["rto"]["status"])
        self.assertEqual("incomplete", result["overall_status"])
        self.assertFalse(result["measurements"]["rpo_rto"]["measured"])

    def test_result_schema_requires_production_disclaimer(self):
        comparisons = compare_measurements(100, 100)
        result = {
            "schema": SCHEMA, "gate": 6,
            "harness": {"mode": "synthetic-local"}, "environment": {"python": "3.11"},
            "targets": {},
            "measurements": {"rpo_rto": {"measured": False}},
            "comparisons": comparisons,
            "overall_status": "incomplete",
            "scope": {"production_qualification": False},
        }
        self.assertIs(validate_result(result), result)
        result["scope"]["production_qualification"] = True
        with self.assertRaises(ValueError):
            validate_result(result)


if __name__ == "__main__":
    unittest.main()
