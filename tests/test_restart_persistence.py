import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from kb_pipeline.composition import RuntimeConfig, compose


def jpeg():
    return b"\xff\xd8\xff\xc0\x00\x0b\x08\x00\x02\x00\x03\x01\x01\x11\x00\xff\xd9"


class Observer:
    model = "fake"
    def __init__(self): self.calls = 0
    def observe(self, payload, filename):
        self.calls += 1
        return {"visible_text": ["RESTART"], "orientation": "landscape", "markers_devices": [],
                "image_quality": "clear", "summary": "A local image.", "uncertainty": [],
                "label_candidates": {"modality": [{"candidate": "photograph", "source": "model_observation"}],
                                     "body_region": [], "projection_view": [], "subject_species": []}}


class RestartPersistenceTests(unittest.TestCase):
    def test_fresh_compose_rebuilds_projections_without_observer_calls(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); source = root / "source"; source.mkdir()
            (source / "note.txt").write_text("durable restart text")
            (source / "photo.jpg").write_bytes(jpeg())
            database = root / "database.sqlite"
            observer = Observer()
            first = compose(RuntimeConfig(database, source, vision_observer=observer))
            for item in first.connector.read(): first.service.ingest(item, "initial")
            self.assertEqual(1, observer.calls)
            self.assertEqual("ready", first.service.readiness()["status"])

            class NoStartupObserver(Observer):
                def observe(self, payload, filename): raise AssertionError("startup must not observe")

            restarted = compose(RuntimeConfig(database, source, vision_observer=NoStartupObserver()))
            self.assertEqual("ready", restarted.service.readiness()["status"])
            self.assertTrue(restarted.service.search("durable restart", "reader"))
            answer = restarted.service.answer("restart", "reader")
            self.assertTrue(answer["visual_evidence"])
            self.assertTrue(answer["citations"])
            self.assertIn("RESTART", answer["summary"]["visible_text"])


if __name__ == "__main__": unittest.main()
