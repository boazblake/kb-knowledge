import hashlib
import unittest

from kb_pipeline.production_adapters import (
    ArtifactContext, EncryptionBoundaryError, S3RawObjectStore,
)
from kb_pipeline.security import FakeKMSProvider, EnvelopeError
from kb_pipeline.postgres_authority import _without_credentials


class _Body:
    def __init__(self, value): self.value = value
    def read(self): return self.value


class _S3:
    def __init__(self): self.objects = {}
    def put_object(self, **kwargs): self.objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs
    def get_object(self, *, Bucket, Key):
        value = self.objects[(Bucket, Key)]
        return {"Body": _Body(value["Body"]), "Metadata": value["Metadata"]}
    def delete_object(self, *, Bucket, Key): self.objects.pop((Bucket, Key), None)


class RawArtifactContractTests(unittest.TestCase):
    def setUp(self):
        self.kms = FakeKMSProvider(b"0123456789abcdef0123456789abcdef")
        self.s3 = _S3()
        self.store = S3RawObjectStore("private", client=self.s3, prefix="tenant-data/", kms=self.kms)
        self.context = ArtifactContext("github", "tenant-a", "nango", "conn-a", "obj-1", "7")
        self.key = self.context.key(self.store.prefix)

    def test_contract_writes_ciphertext_and_round_trips_with_hash(self):
        plaintext = b"bearer=do-not-store-plaintext"
        uri = self.store.put(self.key, plaintext, context=self.context)
        stored = self.s3.objects[("private", self.key)]
        self.assertEqual("s3://private/tenant-data/raw/github/tenant-a/nango/conn-a/obj-1/7", uri)
        self.assertNotIn(plaintext, stored["Body"])
        self.assertEqual(hashlib.sha256(plaintext).hexdigest(), stored["Metadata"]["content-sha256"])
        self.assertEqual(plaintext, self.store.get(self.key, context=self.context))

    def test_context_mismatch_and_cross_tenant_fail_closed(self):
        self.store.put(self.key, b"payload", context=self.context)
        other = ArtifactContext("github", "tenant-b", "nango", "conn-a", "obj-1", "7")
        with self.assertRaises(EncryptionBoundaryError): self.store.get(self.key, context=other)
        with self.assertRaises(EncryptionBoundaryError): self.store.put(self.key, b"x", context=other)
        with self.assertRaises(EnvelopeError): self.kms.decrypt(
            self.kms.encrypt(b"x", key_id=self.kms.current_key_id, context=self.context.as_mapping()),
            context=other.as_mapping())

    def test_missing_object_and_unsafe_key_fail_closed(self):
        with self.assertRaises(EncryptionBoundaryError): self.store.get(self.key, context=self.context)
        with self.assertRaises(ValueError): ArtifactContext("github", "tenant/a", "nango", "conn", "obj", "1").key("raw")

    def test_rotation_reads_old_key_and_retirement_rejects_it(self):
        self.store.put(self.key, b"old", context=self.context)
        self.kms.rotate("kms-v2")
        self.assertEqual(b"old", self.store.get(self.key, context=self.context))
        self.kms.retire("kms-v1")
        with self.assertRaises(EnvelopeError): self.store.get(self.key, context=self.context)

    def test_credentials_are_redacted_before_authority_metadata(self):
        clean = _without_credentials({"access_token": "secret", "oidc_token": "jwt", "safe": "ok"})
        self.assertEqual({"safe": "ok"}, clean)


if __name__ == "__main__": unittest.main()
