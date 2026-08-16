import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from kb_pipeline.answer import DeterministicAnswerer, OllamaAnswerer, OpenAIAnswerer
from kb_pipeline.cli import _answerer_from_args
from kb_pipeline.composition import RuntimeConfig, compose


class OllamaActivationTests(unittest.TestCase):
    def test_openai_requires_explicit_model_and_keeps_key_out_of_config(self):
        answerer = _answerer_from_args("serve", openai_model="gpt-test", openai_timeout=4, openai_retries=1)
        self.assertIsInstance(answerer, OpenAIAnswerer)
        self.assertEqual(("gpt-test", 4, 1), (answerer.model, answerer.timeout_seconds, answerer.max_retries))
        with self.assertRaises(ValueError):
            _answerer_from_args("serve", openai_timeout=4)
        with self.assertRaises(ValueError):
            _answerer_from_args("serve", "local", openai_model="gpt-test")
    def test_default_composition_abstains_without_network(self):
        with TemporaryDirectory() as directory:
            app = compose(RuntimeConfig(Path(directory) / "db", Path(directory)))
            self.assertIsInstance(app.service.answerer, DeterministicAnswerer)
            self.assertFalse(app.service.answer("question", "reader")["grounded"])

    def test_explicit_flags_create_loopback_adapter(self):
        answerer = _answerer_from_args("serve", "local-model", "http://127.0.0.1:11434/api/generate", 2.5)
        assert isinstance(answerer, OllamaAnswerer)
        self.assertEqual("local-model", answerer.model)
        self.assertEqual(2.5, answerer.timeout_seconds)

    def test_unsafe_or_incomplete_activation_is_rejected(self):
        with self.assertRaises(ValueError):
            _answerer_from_args("serve", None, "http://example.test/generate", None)
        with self.assertRaises(ValueError):
            _answerer_from_args("serve", "local-model", "https://127.0.0.1/generate", None)
        with self.assertRaises(ValueError):
            _answerer_from_args("serve", "local-model", None, 0)
        with self.assertRaises(ValueError):
            _answerer_from_args("serve", None, None, 2)


if __name__ == "__main__":
    unittest.main()
