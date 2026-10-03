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
            "role": "service",
            "token_type": "service",
            "status": "active",
        }

    def principal(self, client_id="odoo-staging-pilotage"):
        with patch.dict(os.environ, {"PILOTAGE_TRUSTED_SERVICE_SUBJECTS": "service:odoo", "PILOTAGE_TRUSTED_SERVICE_MODULES_JSON": '{"service:odoo":["diddigo","diddisend"]}'}), \
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

    def test_service_role_and_token_type_are_required(self):
        self.claims["role"] = "user"
        with self.assertRaises(ValueError):
            self.principal()

    def test_token_modules_claim_is_ignored(self):
        self.claims["modules"] = "diddipay"
        self.assertEqual(self.principal().modules, ("diddigo", "diddisend"))

    def test_human_token_uses_diddifree_issuer_without_audience(self):
        claims = {"sub": "user-1", "role": "user", "status": "active"}
        principal = auth.PilotagePrincipal("user-1", "audit_read", ("global",))
        with patch.dict(os.environ, {"PILOTAGE_ENV": "staging", "PILOTAGE_OIDC_ISSUER": "diddifree-id"}, clear=True), \
             patch.object(auth.jwt, "get_unverified_header", return_value={"alg": "RS256", "kid": "key-1"}), \
             patch.object(auth.jwt, "get_unverified_claims", return_value=claims), \
             patch.object(auth.jwt, "decode", return_value=claims) as decode, \
             patch.object(auth.jwk, "construct", return_value=object()), \
             patch.object(auth, "_local_principal", return_value=principal):
            result = auth.principal_from_oidc("token")
        self.assertEqual(result, principal)
        self.assertIsNone(decode.call_args.kwargs["audience"])
        self.assertEqual(decode.call_args.kwargs["issuer"], "diddifree-id")
        self.assertFalse(decode.call_args.kwargs["options"]["verify_aud"])


if __name__ == "__main__":
    unittest.main()
