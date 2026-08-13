import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from kb_pipeline.adapters import LocalFilesConnector, PlainTextCanonicalizer
from kb_pipeline.domain import ACL, Input, RawRecord
from kb_pipeline.service import KnowledgeService
from kb_pipeline.storage import LexicalIndex, MemoryAuditStore, MemoryDocumentStore


class ACLResolver:
    def __init__(self, acl): self.acl = acl
    def resolve(self, record): return self.acl


def service(acl=ACL(frozenset({"alice"}))):
    return KnowledgeService(MemoryDocumentStore(), LexicalIndex(), ACLResolver(acl), PlainTextCanonicalizer(), MemoryAuditStore())


def item(name="one", text=b"secret retrieval text"):
    return Input("test", name, text, "file:///" + name)


class PipelineTests(unittest.TestCase):
    def test_contract_provenance_and_idempotency(self):
        svc = service(); self.assertTrue(svc.ingest(item(), "job-1")); self.assertFalse(svc.ingest(item(), "job-1"))
        hits = svc.search("retrieval", "alice"); self.assertEqual(len(hits), 1); self.assertTrue(hits[0].source_version)

    def test_acl_deny_uncertainty_and_no_leakage(self):
        svc = service(ACL(None)); svc.ingest(item(), "j"); self.assertEqual([], svc.search("secret", "alice"))

    def test_tombstone_no_resurrection(self):
        svc = service(); svc.ingest(item(), "j"); svc.tombstone("one", "admin"); svc.ingest(item(), "j2"); self.assertEqual([], svc.search("secret", "alice"))

    def test_revocation_suppresses_source(self):
        svc = service(); svc.ingest(item(), "j"); svc.revoke_source("one"); self.assertEqual([], svc.search("secret", "alice"))

    def test_tombstone_purge_remains_nonresurrectable(self):
        svc = service(); svc.ingest(item(), "j"); svc.tombstone("one", "admin")
        self.assertEqual(1, svc.store.purge(datetime.now(timezone.utc) + timedelta(seconds=1)))
        svc.ingest(item(), "j2"); self.assertEqual([], svc.search("secret", "alice"))

    def test_failure_recovery_retry(self):
        class Failing:
            def __init__(self): self.calls = 0
            def resolve(self, record):
                self.calls += 1
                if self.calls == 1: raise RuntimeError("temporary")
                return ACL(frozenset({"alice"}))
        svc = KnowledgeService(MemoryDocumentStore(), LexicalIndex(), Failing(), PlainTextCanonicalizer(), MemoryAuditStore())
        with self.assertRaises(RuntimeError): svc.ingest(item(), "j")
        self.assertTrue(svc.ingest(item(), "j")); self.assertEqual(1, len(svc.search("secret", "alice")))

    def test_local_connector(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "mail.txt"; path.write_text("attachment")
            records = list(LocalFilesConnector(Path(root)).read())
            self.assertEqual("mail.txt", records[0].external_id)


if __name__ == "__main__": unittest.main()
