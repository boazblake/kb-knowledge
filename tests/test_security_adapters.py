import base64, hashlib, hmac, json, time, unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from kb_pipeline.security import FakeOIDCValidator, FakeKMSProvider, AuthenticationError, EnvelopeError, Principal
from kb_pipeline.composition import RuntimeConfig

def token(claims, key=b"secret", kid="k1", alg="HS256"):
    enc = lambda x: base64.urlsafe_b64encode(json.dumps(x, separators=(",", ":")).encode()).rstrip(b"=").decode()
    head, body = enc({"alg": alg, "kid": kid}), enc(claims)
    sig = base64.urlsafe_b64encode(hmac.new(key, f"{head}.{body}".encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    return f"{head}.{body}.{sig}"

class SecurityContractTests(unittest.TestCase):
    def claims(self, **extra):
        value = {"iss": "https://issuer", "aud": "kb", "sub": "alice", "tenant": "t1", "roles": ["reader"], "source_scopes": ["s1"], "exp": time.time() + 60}; value.update(extra); return value
    def test_jwt_claim_and_signature_fail_closed(self):
        validator = FakeOIDCValidator("https://issuer", "kb", {"k1": b"secret"}); principal = validator.validate(token(self.claims()))
        self.assertTrue(principal.can_read("t1", "s1")); self.assertFalse(principal.can_read("t2", "s1"))
        for claims in (self.claims(iss="wrong"), self.claims(aud="wrong"), self.claims(exp=1), self.claims(tenant="")):
            with self.assertRaises(AuthenticationError): validator.validate(token(claims))
        with self.assertRaises(AuthenticationError): validator.validate(token(self.claims())[:-1] + "x")
    def test_envelope_context_tamper_and_key_failure(self):
        kms = FakeKMSProvider(b"master-key"); context = {"object_key": "o", "tenant": "t1", "purpose": "raw-artifact"}; envelope = kms.encrypt(b"secret", key_id="kms-v1", context=context)
        self.assertEqual(b"secret", kms.decrypt(envelope, context=context))
        with self.assertRaises(EnvelopeError): kms.decrypt(envelope, context={"object_key": "other"})
        kms.retire("kms-v1")
        with self.assertRaises(EnvelopeError): kms.decrypt(envelope, context=context)
    def test_production_rejects_test_security(self):
        with TemporaryDirectory() as directory:
            with self.assertRaises(ValueError): RuntimeConfig(Path(directory) / "db", Path(directory), mode="production", identity_provider=FakeOIDCValidator("i", "a", {}), key_provider=FakeKMSProvider(b"x")).validate()
    def test_principal_role_isolation(self):
        p = Principal("a", "t1", frozenset({"admin"}), frozenset({"source-a"})); self.assertTrue(p.is_admin("t1")); self.assertFalse(p.is_admin("t2")); self.assertFalse(p.can_read("t1", "source-b"))

if __name__ == "__main__": unittest.main()
