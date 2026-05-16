from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.config import settings
from app.logging_setup import get_logger

log = get_logger(__name__)

_RETRYABLE = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
)


@asynccontextmanager
async def http_client(**overrides) -> AsyncIterator[httpx.AsyncClient]:
    defaults: dict = {
        "timeout": settings.http_timeout_seconds,
        "headers": {
            "User-Agent": settings.http_user_agent,
            "Accept": "application/json, text/html;q=0.9, */*;q=0.5",
            "Accept-Language": "en-US,en;q=0.9",
        },
        "follow_redirects": True,
        "http2": False,
    }
    defaults.update(overrides)
    async with httpx.AsyncClient(**defaults) as client:
        yield client


async def get_json(client: httpx.AsyncClient, url: str, **kwargs) -> dict | list:
    return await _request(client, "GET", url, want="json", **kwargs)


async def post_json(client: httpx.AsyncClient, url: str, **kwargs) -> dict | list:
    return await _request(client, "POST", url, want="json", **kwargs)


async def get_text(client: httpx.AsyncClient, url: str, **kwargs) -> str:
    return await _request(client, "GET", url, want="text", **kwargs)


async def _request(client: httpx.AsyncClient, method: str, url: str, *, want: str, **kwargs):
    last_exc: Exception | None = None
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(settings.http_max_retries),
            wait=wait_exponential_jitter(initial=1.0, max=15.0),
            retry=retry_if_exception_type(_RETRYABLE),
            reraise=True,
        ):
            with attempt:
                resp = await client.request(method, url, **kwargs)
                if resp.status_code == 429:
                    log.warning("rate_limited", url=url, status=resp.status_code)
                    raise httpx.HTTPStatusError("rate limited", request=resp.request, response=resp)
                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"server {resp.status_code}", request=resp.request, response=resp
                    )
                resp.raise_for_status()
                if want == "json":
                    return resp.json()
                return resp.text
    except RetryError as e:
        last_exc = e
    except httpx.HTTPStatusError as e:
        # Non-retryable 4xx: surface immediately
        raise e
    if last_exc:
        raise last_exc
    raise RuntimeError("unreachable")
