import unittest
from pathlib import Path

from kb_pipeline.cli import _serve_startup_output


class ServeStartupOutputTests(unittest.TestCase):
    def test_demo_output_explains_local_bearer_and_cookie_use(self):
        output = _serve_startup_output("127.0.0.1:8080", "demo", "demo-token")
        self.assertIn("serving on 127.0.0.1:8080", output)
        self.assertIn("local-only Bearer token", output)
        self.assertIn("Authorization: Bearer demo-token", output)
        self.assertIn("HttpOnly kb_session cookie", output)
        self.assertIn("valid until server stops", output)

    def test_production_output_never_includes_token(self):
        output = _serve_startup_output("0.0.0.0:443", "production", "oidc-secret")
        self.assertIn("configured OIDC Bearer token", output)
        self.assertNotIn("oidc-secret", output)
        self.assertNotIn("local-only Bearer token", output)

    def test_runbook_records_auth_routes_lifetime_and_answer_policy(self):
        runbook = (Path(__file__).parents[1] / "docs" / "runbook.md").read_text()
        for phrase in (
            "HttpOnly",
            "expires when server stops",
            "Authenticated",
            "/v1/answer",
            "deterministic abstention",
            "--ollama-model MODEL",
            "OIDC Bearer tokens",
        ):
            self.assertIn(phrase, runbook)


if __name__ == "__main__":
    unittest.main()
