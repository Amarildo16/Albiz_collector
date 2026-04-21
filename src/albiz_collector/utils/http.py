from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ResponsePayload:
    url: str
    status_code: int
    content_type: str | None
    content: bytes
    text: str | None = None
    cookies: httpx.Cookies | None = None


class HttpClient:
    def __init__(self) -> None:
        self._client = httpx.Client(
            timeout=settings.http_timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": settings.http_user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "sq,en;q=0.9",
            },
        )

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.HTTPError,)),
    )
    def get(self, url: str) -> ResponsePayload:
        logger.info("GET %s", url)
        response = self._client.get(url)
        return self._build_response_payload(response)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.HTTPError,)),
    )
    def post(
        self,
        url: str,
        *,
        data: Any = None,
        headers: dict[str, str] | None = None,
        cookies: httpx.Cookies | None = None,
    ) -> ResponsePayload:
        logger.info("POST %s", url)
        response = self._client.post(url, data=data, headers=headers, cookies=cookies)
        return self._build_response_payload(response)

    @staticmethod
    def _build_response_payload(response: httpx.Response) -> ResponsePayload:
        response.raise_for_status()
        return ResponsePayload(
            url=str(response.url),
            status_code=response.status_code,
            content_type=response.headers.get("content-type"),
            content=response.content,
            text=response.text,
            cookies=response.cookies,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
