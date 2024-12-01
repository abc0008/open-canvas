import asyncio

import httpx

from langgraph_api.base.shared.serde import json_dumpb


class JsonHttpClient:
    """HTTPX client for JSON requests."""

    def __init__(self, client: httpx.AsyncClient, timeout: int) -> None:
        """Initialize the auth client."""
        self.client = client
        self.timeout = timeout

    async def post(
        self,
        path: str,
        json: dict,
    ) -> None:
        try:
            res = await asyncio.wait_for(
                self.client.post(
                    path,
                    content=json_dumpb(json),
                    headers={"Content-Type": "application/json"},
                ),
                # httpx timeout controls are additive for each operation
                # (connect, read, write), so we need an asyncio timeout instead
                self.timeout,
            )
            # Raise for retriable errors
            res.raise_for_status()
        finally:
            # We don't need the response body, so we close the response
            try:
                await res.aclose()
            except UnboundLocalError:
                pass


_webhook_client: JsonHttpClient


async def start_webhook_client() -> None:
    global _webhook_client
    _webhook_client = JsonHttpClient(
        client=httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(
                retries=2,  # this applies only to ConnectError, ConnectTimeout
                limits=httpx.Limits(
                    max_keepalive_connections=10, keepalive_expiry=60.0
                ),
            ),
        ),
        timeout=5,
    )


async def stop_webhook_client() -> None:
    global _webhook_client
    await _webhook_client.client.aclose()
    del _webhook_client


def get_webhook_client() -> JsonHttpClient:
    return _webhook_client
