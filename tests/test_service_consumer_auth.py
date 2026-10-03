import os
import unittest
from unittest.mock import patch

import app.core.auth as auth


class ServiceConsumerAuthTests(unittest.TestCase):
    def setUp(self):
        auth._jwks_cache = (9999999999, {"keys": [{"kid": "key-1"}]})
        self.claims = {
            "sub": "service:odoo",
            "client_id": "odoo-staging-pilotage",
            "aud": "pilotage",
            "scope": "pilotage:read",
            "modules": "diddigo,diddisend",
        }

    def principal(self, client_id="odoo-staging-pilotage"):
        with patch.dict(os.environ, {"PILOTAGE_TRUSTED_SERVICE_SUBJECTS": "service:odoo"}), \
             patch.object(auth.jwt, "get_unverified_header", return_value={"alg": "RS256", "kid": "key-1"}), \
             patch.object(auth.jwt, "get_unverified_claims", return_value=self.claims), \
             patch.object(auth.jwt, "decode", return_value=self.claims), \
             patch.object(auth.jwk, "construct", return_value=object()):
            return auth.principal_from_oidc("token", client_id)

    def test_service_read_scope_gets_non_financial_role_and_modules(self):
        principal = self.principal()
        self.assertEqual(principal.role, "audit_read")
        self.assertEqual(principal.modules, ("diddigo", "diddisend"))

    def test_finance_scope_gets_financial_role(self):
        self.claims["scope"] += " pilotage:finance:read"
        self.assertEqual(self.principal().role, "finance_admin")

    def test_client_header_must_match_token(self):
        with self.assertRaises(ValueError):
            self.principal("wrong-client")


if __name__ == "__main__":
    unittest.main()
