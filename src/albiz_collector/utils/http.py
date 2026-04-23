from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import before_sleep_log, retry, retry_if_exception, stop_after_attempt, wait_exponential

from ..config import settings

logger = logging.getLogger(__name__)
RETRYABLE_STATUS_CODES = {408, 425, 429}
PROXY_ENV_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)


def _is_retryable_http_status(status_code: int) -> bool:
    return status_code in RETRYABLE_STATUS_CODES or 500 <= status_code < 600


def _is_retryable_http_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.LocalProtocolError):
        return False
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return _is_retryable_http_status(exc.response.status_code)
    return False


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
        configured_proxy_env_vars = [name for name in PROXY_ENV_VARS if os.getenv(name)]
        if configured_proxy_env_vars:
            logger.info(
                "HTTP client will honor proxy-related environment variables: %s",
                ", ".join(configured_proxy_env_vars),
            )

        self._client = httpx.Client(
            timeout=settings.http_timeout_seconds,
            follow_redirects=True,
            trust_env=True,
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
        retry=retry_if_exception(_is_retryable_http_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def get(self, url: str) -> ResponsePayload:
        return self._request("GET", url)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception(_is_retryable_http_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def post(
        self,
        url: str,
        *,
        data: Any = None,
        headers: dict[str, str] | None = None,
        cookies: httpx.Cookies | None = None,
    ) -> ResponsePayload:
        return self._request("POST", url, data=data, headers=headers, cookies=cookies)

    def _request(self, method: str, url: str, **kwargs: Any) -> ResponsePayload:
        logger.info("%s %s", method, url)
        response = self._client.request(method, url, **kwargs)
        return self._build_response_payload(response)

    @staticmethod
    def _build_response_payload(response: httpx.Response) -> ResponsePayload:
        if response.is_error:
            method = response.request.method if response.request is not None else "HTTP"
            retryable = _is_retryable_http_status(response.status_code)
            logger.log(
                logging.WARNING if retryable else logging.ERROR,
                "%s %s returned HTTP %s%s",
                method,
                response.url,
                response.status_code,
                " (retryable)" if retryable else "",
            )
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
