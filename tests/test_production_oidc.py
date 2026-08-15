import json
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timedelta, timezone

try:
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jwt.algorithms import RSAAlgorithm
    HAS_OIDC_DEPS = True
except ImportError:
    HAS_OIDC_DEPS = False

from kb_pipeline.security import AuthenticationError, FakeOIDCValidator, OIDCJWKSValidator


class _ProductionScopeAPI(unittest.TestCase):
    def test_tenant_bypass_is_denied_before_search(self):
        from kb_pipeline.api import create_server
        from kb_pipeline.security import Principal

        class Validator:
            production_oidc = True
            test_only = False
            def validate(self, token):
                self.seen = token
                return Principal("u", "tenant-a", frozenset({"reader"}), frozenset({"source-a"}))

        class Service:
            def search(self, *_): raise AssertionError("authorization must precede retrieval")

        server, _ = create_server(Service(), port=0, identity_provider=Validator(), production=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            url = f"http://{server.server_address[0]}:{server.server_address[1]}/v1/search?q=x&tenant=tenant-b"
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(url, headers={"Authorization": "Bearer synthetic"}))
            self.assertEqual(403, error.exception.code)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)


@unittest.skipUnless(HAS_OIDC_DEPS, "PyJWT[crypto] unavailable; local OIDC evidence not runnable")
class ProductionOIDCTests(unittest.TestCase):
    def setUp(self):
        self.keys = {}
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"keys": [owner.keys[k] for k in sorted(owner.keys)]}).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body)
            def log_message(self, *_): pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.issuer = "https://issuer.example"; self.audience = "kb-api"
        self.private = {}
        self.rotate("one")
        self.validator = OIDCJWKSValidator(self.issuer, self.audience, self.url,
                                           cache_lifespan=1, leeway=0)

    @property
    def url(self):
        return f"http://{self.server.server_address[0]}:{self.server.server_address[1]}/jwks"

    def rotate(self, kid):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.private[kid] = key
        public = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
        public.update({"kid": kid, "use": "sig", "alg": "RS256"})
        self.keys[kid] = public

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)

    def token(self, key: str = "one", **overrides):
        claims = {"iss": self.issuer, "aud": self.audience, "sub": "user-1",
                  "tenant": "tenant-a", "roles": ["reader"],
                  "source_scopes": ["source-a"],
                  "iat": datetime.now(timezone.utc),
                  "nbf": datetime.now(timezone.utc),
                  "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}
        claims.update(overrides)
        return jwt.encode(claims, self.private.get(key, self.private["one"]), algorithm="RS256", headers={"kid": key})

    def test_claims_and_scope_mapping(self):
        principal = self.validator.validate(self.token())
        self.assertEqual("tenant-a", principal.tenant)
        self.assertTrue(principal.can_read("tenant-a", "source-a"))
        self.assertFalse(principal.can_read("tenant-b", "source-a"))
        self.assertFalse(principal.can_read("tenant-a", "source-b"))

    def test_wrong_issuer_audience_and_expiry_fail(self):
        for claims in ({"iss": "wrong"}, {"aud": "wrong"},
                       {"exp": datetime.now(timezone.utc) - timedelta(seconds=1)}):
            with self.subTest(claims=claims), self.assertRaises(AuthenticationError):
                self.validator.validate(self.token(**claims))

    def test_not_before_algorithm_and_network_fail_closed(self):
        with self.assertRaises(AuthenticationError):
            self.validator.validate(self.token(nbf=datetime.now(timezone.utc) + timedelta(minutes=5)))
        with self.assertRaises(AuthenticationError):
            self.validator.validate(jwt.encode({"sub": "u"}, "not-a-rsa-key", algorithm="HS256", headers={"kid": "one"}))
        unavailable = OIDCJWKSValidator(self.issuer, self.audience, "http://127.0.0.1:1/jwks", timeout=0.1)
        with self.assertRaises(AuthenticationError):
            unavailable.validate(self.token())

    def test_rotation_refreshes_unknown_kid_and_unknown_key_fails(self):
        self.rotate("two")
        self.assertEqual("user-1", self.validator.validate(self.token("two")).subject)
        unknown = OIDCJWKSValidator(self.issuer, self.audience, self.url, leeway=0)
        with self.assertRaises(AuthenticationError):
            unknown.validate(self.token("missing"))

    def test_fake_identity_is_not_production_validator(self):
        self.assertTrue(getattr(FakeOIDCValidator("i", "a", {}), "test_only"))
        self.assertFalse(getattr(FakeOIDCValidator("i", "a", {}), "production_oidc", False))


if __name__ == "__main__":
    unittest.main()
