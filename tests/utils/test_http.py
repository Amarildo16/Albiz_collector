from __future__ import annotations

import unittest

import httpx

from albiz_collector.utils.http import HttpClient, _is_retryable_http_error


class HttpRetryClassificationTests(unittest.TestCase):
    def test_retries_retryable_status_codes(self) -> None:
        request = httpx.Request("GET", "https://example.test/retry")
        response = httpx.Response(503, request=request)
        exc = httpx.HTTPStatusError("server error", request=request, response=response)

        self.assertTrue(_is_retryable_http_error(exc))

    def test_does_not_retry_non_retryable_client_status_codes(self) -> None:
        request = httpx.Request("GET", "https://example.test/bad-request")
        response = httpx.Response(400, request=request)
        exc = httpx.HTTPStatusError("bad request", request=request, response=response)

        self.assertFalse(_is_retryable_http_error(exc))

    def test_retries_transport_errors_but_not_local_protocol_errors(self) -> None:
        request = httpx.Request("GET", "https://example.test/network")
        transport_error = httpx.ConnectError("connection failed", request=request)
        protocol_error = httpx.LocalProtocolError("invalid request state")

        self.assertTrue(_is_retryable_http_error(transport_error))
        self.assertFalse(_is_retryable_http_error(protocol_error))

    def test_error_response_payload_builder_raises_http_status_error_not_name_error(self) -> None:
        request = httpx.Request("GET", "https://example.test/retry")
        response = httpx.Response(503, request=request)

        with self.assertRaises(httpx.HTTPStatusError):
            HttpClient._build_response_payload(response)


if __name__ == "__main__":
    unittest.main()
