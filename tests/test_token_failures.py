import asyncio
import unittest
from unittest.mock import patch

import httpx

from app.sources.catalog import get_source
from app.sources.gateway import SourceGateway, SourceUnavailable


class TokenFailureTests(unittest.TestCase):
    def test_token_rejection_preserves_safe_http_status(self):
        request = httpx.Request("POST", "https://auth.example/token")
        response = httpx.Response(401, request=request)
        with patch("app.sources.gateway.get_service_token", side_effect=httpx.HTTPStatusError("rejected", request=request, response=response)):
            with self.assertRaises(SourceUnavailable) as raised:
                asyncio.run(SourceGateway(get_source("diddigo")).get("/internal/pilotage/daily-summary"))
        self.assertEqual(raised.exception.code, "token_endpoint_rejected_401")

    def test_token_network_failure_is_distinct(self):
        request = httpx.Request("POST", "https://auth.example/token")
        with patch("app.sources.gateway.get_service_token", side_effect=httpx.ConnectError("offline", request=request)):
            with self.assertRaises(SourceUnavailable) as raised:
                asyncio.run(SourceGateway(get_source("diddigo")).get("/internal/pilotage/daily-summary"))
        self.assertEqual(raised.exception.code, "token_endpoint_unavailable")


if __name__ == "__main__":
    unittest.main()
