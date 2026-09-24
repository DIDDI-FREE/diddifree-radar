"""Controlled HTTP boundary for Pilotage source collection."""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.core.logging import Stopwatch, log_json
from app.core.request_context import get_request_id
from app.core.service_auth import get_service_token, service_request_headers
from app.sources.catalog import PilotageSource


class SourceError(RuntimeError):
    """Base error exposed to the collector, never raw httpx errors."""

    def __init__(self, source: str, code: str, message: str, *, status_code: int | None = None) -> None:
        super().__init__(f"{source}: {message}")
        self.source = source
        self.code = code
        self.status_code = status_code


class SourceUnavailable(SourceError):
    pass


class SourceRejected(SourceError):
    pass


def _controlled_path(path: str) -> str:
    if not path.startswith("/") or path.startswith("//") or ".." in path.split("/"):
        raise ValueError("Source path must be a normalized relative path")
    return path


class SourceGateway:
    """One network boundary shared by every Pilotage source client."""

    def __init__(self, source: PilotageSource, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.source = source
        self._transport = transport

    def _timeout(self) -> httpx.Timeout:
        total = float(os.getenv("PILOTAGE_SOURCE_TIMEOUT_SECONDS", "10"))
        return httpx.Timeout(total, connect=min(total, 5.0))

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict:
        path = _controlled_path(path)
        headers = dict(service_request_headers(self.source.key))
        request_id = get_request_id()
        if request_id:
            headers.setdefault("X-Request-ID", request_id)
        if self.source.requires_token:
            try:
                token = get_service_token(self.source.key, scope=self.source.scope())
            except httpx.HTTPError as error:
                log_json({"event": "source_error", "source": self.source.key, "path": path, "category": "token_endpoint_failure", "error": str(error)})
                raise SourceUnavailable(self.source.key, "token_endpoint_failure", "service token endpoint rejected or unavailable") from error
            if not token:
                log_json({"event": "source_error", "source": self.source.key, "path": path, "category": "credential_missing"})
                raise SourceUnavailable(self.source.key, "credential_missing", "service credential missing")
            headers.setdefault("Authorization", f"Bearer {token}")
        timer = Stopwatch()
        try:
            async with httpx.AsyncClient(
                base_url=self.source.base_url(), timeout=self._timeout(), transport=self._transport
            ) as client:
                response = await client.get(path, params=params, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            log_json({"event": "source_error", "source": self.source.key, "path": path, "duration_ms": timer.elapsed_ms(), "category": "timeout"})
            raise SourceUnavailable(self.source.key, "timeout", "source unavailable") from error
        except httpx.HTTPError as error:
            log_json({"event": "source_error", "source": self.source.key, "path": path, "duration_ms": timer.elapsed_ms(), "category": "client_failure", "error": str(error)})
            raise SourceUnavailable(self.source.key, "client_failure", "HTTP client failure") from error
        log_json({"event": "source_request", "source": self.source.key, "path": path, "status_code": response.status_code, "duration_ms": timer.elapsed_ms()})
        if response.status_code in {401, 403}:
            raise SourceRejected(self.source.key, "credential_rejected", "service credential or scope is not accepted", status_code=response.status_code)
        if response.status_code == 404:
            raise SourceRejected(self.source.key, "route_missing", "source does not expose this Pilotage route yet", status_code=404)
        if response.is_error:
            raise SourceRejected(self.source.key, "rejected", "source rejected the request", status_code=response.status_code)
        try:
            return response.json()
        except ValueError as error:
            raise SourceRejected(self.source.key, "invalid_payload", "source returned a non-JSON payload") from error
