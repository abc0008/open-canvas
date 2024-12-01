from collections.abc import Callable
from typing import ParamSpec, TypeVar
from urllib.parse import urlencode

import pycurl
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)
from tornado.httpclient import (
    AsyncHTTPClient,
    HTTPClientError,
    HTTPRequest,
    HTTPResponse,
)

from langgraph_api.base import config

P = ParamSpec("P")
R = TypeVar("R")
AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")
_client: AsyncHTTPClient | None = None


def is_retriable_error(exception: Exception) -> bool:
    if isinstance(exception, HTTPClientError):
        return exception.code >= 500
    return False


retry_pycurl = retry(
    reraise=True,
    retry=retry_if_exception(is_retriable_error),
    wait=wait_exponential_jitter(),
    stop=stop_after_attempt(3),
)


@retry_pycurl
async def http_request(
    method: str,
    url: str,
    /,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    body: bytes | str | None = None,
    connect_timeout: float | None = 5,
    request_timeout: float | None = 30,
    prepare_curl_callback: Callable[[pycurl.Curl], None] | None = None,
    raise_error: bool = True,
) -> HTTPResponse:
    global _client
    if not url.startswith("http"):
        raise ValueError("path must start with / or http")
    if _client is None:
        _client = AsyncHTTPClient(max_clients=config.HTTP_CONCURRENCY)
    if params:
        url += "?" + urlencode(params)
    request = HTTPRequest(
        url=url,
        method=method,
        headers=headers,
        body=body,
        connect_timeout=connect_timeout,
        request_timeout=request_timeout,
        prepare_curl_callback=prepare_curl_callback,
        follow_redirects=False,
    )
    return await _client.fetch(request, raise_error=raise_error)
