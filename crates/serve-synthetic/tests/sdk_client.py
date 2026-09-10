#!/usr/bin/env python3
"""Official OpenAI SDK compatibility check against the synthetic loopback API."""

from __future__ import annotations

import argparse
import contextlib
import io
import ipaddress
import logging
import threading
from pathlib import Path

import httpx2 as httpx
import openai


class LoopbackGuardTransport(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport | None = None) -> None:
        self.inner = inner or httpx.HTTPTransport(retries=0)

    @staticmethod
    def require_loopback(request: httpx.Request) -> None:
        if request.url.scheme != "http" or request.url.host is None:
            raise RuntimeError("SDK destination must use HTTP loopback")
        try:
            address = ipaddress.ip_address(request.url.host)
        except ValueError as error:
            raise RuntimeError("SDK destination must be a literal loopback address") from error
        if not address.is_loopback:
            raise RuntimeError("SDK destination is not loopback")

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.require_loopback(request)
        return self.inner.handle_request(request)

    def close(self) -> None:
        self.inner.close()


class CountingTransport(httpx.BaseTransport):
    def __init__(self, status: int = 200, location: str | None = None) -> None:
        self.calls = 0
        self.status = status
        self.location = location

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        headers = {"location": self.location} if self.location else {}
        return httpx.Response(self.status, headers=headers, request=request)


def prove_destination_and_redirect_guards() -> None:
    cloud_inner = CountingTransport()
    cloud_guard = LoopbackGuardTransport(cloud_inner)
    try:
        cloud_guard.handle_request(httpx.Request("GET", "https://api.openai.invalid/v1/models"))
    except RuntimeError:
        pass
    else:
        raise AssertionError("fake cloud destination was accepted")
    assert cloud_inner.calls == 0, "cloud request reached the inner transport"

    redirect_inner = CountingTransport(status=302, location="https://api.openai.invalid/v1/models")
    with httpx.Client(
        transport=LoopbackGuardTransport(redirect_inner),
        follow_redirects=False,
        trust_env=False,
    ) as client:
        response = client.get("http://127.0.0.1:1/v1/models")
    assert response.status_code == 302
    assert redirect_inner.calls == 1, "redirect caused an unexpected follow-up request"


def make_client(base_url: str, token: str, timeout: float = 5.0) -> tuple[openai.OpenAI, httpx.Client]:
    http_client = httpx.Client(
        transport=LoopbackGuardTransport(),
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(timeout),
    )
    client = openai.OpenAI(
        api_key=token,
        base_url=base_url,
        http_client=http_client,
        max_retries=0,
    )
    return client, http_client


def chat(client: openai.OpenAI, content: str, **kwargs):
    return client.chat.completions.create(
        model="pulsarmlx-synthetic-v1",
        messages=[{"role": "user", "content": content}],
        **kwargs,
    )


def error_body(error: openai.APIStatusError) -> dict:
    body = error.body
    if isinstance(body, dict):
        return body.get("error", body)
    return {}


def prove_authentication_and_errors(base_url: str, token: str) -> None:
    """Authentication and error handling for the supported route subset."""
    bad_client, bad_http = make_client(base_url, "not-the-right-token-value", )
    with bad_http:
        try:
            bad_client.models.list()
        except openai.AuthenticationError as error:
            assert error.status_code == 401
            body = error_body(error)
            assert body.get("code") == "invalid_api_key", body
            # F5: the SDK must see an authentication failure, not a caller
            # mistake, or re-authentication logic cannot trigger.
            assert body.get("type") == "authentication_error", body
        else:
            raise AssertionError("invalid bearer token was accepted")

    client, http_client = make_client(base_url, token)
    with http_client:
        try:
            client.chat.completions.create(
                model="some-other-model",
                messages=[{"role": "user", "content": "hello"}],
            )
        except openai.NotFoundError as error:
            assert error_body(error).get("code") == "model_not_found"
        except openai.BadRequestError as error:
            assert error_body(error).get("code") == "model_not_found"
        else:
            raise AssertionError("unknown model was accepted")

        try:
            chat(client, "__synthetic_fail_before__")
        except openai.InternalServerError as error:
            assert error.status_code == 500
            body = error_body(error)
            assert body.get("code") == "backend_failure", body
            assert body.get("type") == "server_error", body
        else:
            raise AssertionError("synthetic backend failure was not reported")

        try:
            chat(client, "__synthetic_slow__")
        except openai.APIStatusError as error:
            assert error.status_code == 504, error.status_code
            body = error_body(error)
            assert body.get("code") == "generation_timeout", body
            assert body.get("type") == "server_error", body
        else:
            raise AssertionError("generation timeout was not reported")
        client.close()


def prove_rate_limit(base_url: str, token: str) -> None:
    """The single generation slot must surface as a rate limit, not a hang."""
    holder_client, holder_http = make_client(base_url, token, timeout=10.0)
    observed: list[object] = []

    def hold() -> None:
        with contextlib.suppress(Exception):
            chat(holder_client, "__synthetic_slow__")

    thread = threading.Thread(target=hold, daemon=True)
    with holder_http:
        thread.start()
        client, http_client = make_client(base_url, token)
        with http_client:
            deadline = threading.Event()
            for _ in range(50):
                try:
                    chat(client, "hello")
                except openai.RateLimitError as error:
                    assert error.status_code == 429
                    body = error_body(error)
                    assert body.get("code") == "server_busy", body
                    # F5: a busy generation slot must not look like a caller
                    # mistake, or SDK backoff cannot engage.
                    assert body.get("type") == "rate_limit_error", body
                    observed.append(error)
                    break
                except openai.APIError:
                    break
                deadline.wait(0.02)
            client.close()
        thread.join(timeout=15)
    holder_client.close()
    assert observed, "the busy generation slot never surfaced as a rate limit"


def prove_timeout_cancellation_and_disconnect(base_url: str, token: str) -> None:
    """Client-side timeout, mid-stream cancellation, and recovery afterwards."""
    # A client timeout shorter than the synthetic generation deadline.
    impatient, impatient_http = make_client(base_url, token, timeout=0.25)
    with impatient_http:
        try:
            chat(impatient, "__synthetic_slow__")
        except openai.APITimeoutError:
            pass
        except openai.APIConnectionError:
            pass
        else:
            raise AssertionError("client timeout did not surface")
        impatient.close()

    client, http_client = make_client(base_url, token)
    with http_client:
        # Abandon a stream part-way; the server must release its permit.
        stream = chat(client, "hello", stream=True)
        seen = 0
        for _ in stream:
            seen += 1
            if seen >= 1:
                break
        stream.close()
        assert seen >= 1

        # The single generation slot is reusable after both events, which is
        # only true if the server released ownership on timeout and disconnect.
        completion = chat(client, "hello")
        assert completion.choices[0].message.content == "SYNTHETIC_OK: café 🚀"
        assert completion.choices[0].finish_reason == "stop"
        client.close()


def prove_streaming_failure_surfaces(base_url: str, token: str) -> None:
    """An unsuccessful stream must reach the SDK as an error, not as a clean end.

    F2: before the server emitted a terminal `event: error`, a generation that
    exceeded its deadline simply closed the SSE body. The SDK then ended its
    iteration normally with no chunks and no finish_reason, so a consumer could
    not distinguish it from a successful empty completion.
    """
    client, http_client = make_client(base_url, token, timeout=10.0)
    with http_client:
        for content in ("__synthetic_slow__", "__synthetic_fail_after__"):
            chunks = []
            finish = None
            try:
                for chunk in chat(client, content, stream=True):
                    chunks.append(chunk)
                    if chunk.choices and chunk.choices[0].finish_reason:
                        finish = chunk.choices[0].finish_reason
            except openai.APIError as error:
                assert "synthetic" in str(error).lower(), str(error)
            else:
                raise AssertionError(
                    f"{content}: stream ended without an error "
                    f"(chunks={len(chunks)}, finish_reason={finish!r})"
                )
            assert finish != "stop", f"{content}: reported a successful finish"

        # The generation slot is reusable after both failures.
        completion = chat(client, "hello")
        assert completion.choices[0].finish_reason == "stop"
        client.close()


def prove_bounded_requests_and_assembly(base_url: str, token: str) -> None:
    """Server-declared bounds surface as errors, and the server stays usable."""
    client, http_client = make_client(base_url, token)
    with http_client:
        # Over the message-count bound.
        try:
            client.chat.completions.create(
                model="pulsarmlx-synthetic-v1",
                messages=[{"role": "user", "content": "x"}] * 17,
            )
        except openai.BadRequestError as error:
            assert error_body(error).get("code") == "invalid_messages"
        else:
            raise AssertionError("message count bound was not enforced")

        # Over the per-message byte bound.
        try:
            chat(client, "x" * (2 * 1024 + 1))
        except openai.BadRequestError as error:
            assert error_body(error).get("code") == "message_too_large"
        else:
            raise AssertionError("message size bound was not enforced")

        # Outside the supported output range.
        for max_tokens in (0, 17):
            try:
                chat(client, "hello", max_tokens=max_tokens)
            except openai.BadRequestError as error:
                assert error_body(error).get("code") == "invalid_max_tokens"
            else:
                raise AssertionError(f"max_tokens={max_tokens} was accepted")

        # Truncated output assembles with the declared finish reason.
        truncated = chat(client, "hello", max_tokens=1)
        assert truncated.choices[0].message.content == "SYNTHETIC_OK:"
        assert truncated.choices[0].finish_reason == "length"
        assert truncated.usage is not None
        assert truncated.usage.completion_tokens == 1

        # Streamed truncation assembles the same way.
        content: list[str] = []
        finish = None
        for chunk in chat(client, "hello", stream=True, max_tokens=1):
            if chunk.choices[0].delta.content:
                content.append(chunk.choices[0].delta.content)
            if chunk.choices[0].finish_reason:
                finish = chunk.choices[0].finish_reason
        assert "".join(content) == "SYNTHETIC_OK:"
        assert finish == "length"

        # An empty synthetic completion is still well formed.
        empty = chat(client, "__synthetic_empty__")
        assert empty.choices[0].message.content == ""
        assert empty.choices[0].finish_reason == "stop"
        assert empty.usage is not None
        assert empty.usage.completion_tokens == 0
        client.close()


def prove_no_sensitive_content_in_client_logs(base_url: str, token: str) -> None:
    """Debug-level SDK logging must not expose the bearer token."""
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setLevel(logging.DEBUG)
    names = ("openai", "httpx2", "httpcore2")
    loggers = [logging.getLogger(name) for name in names]
    previous = [(logger.level, logger.propagate) for logger in loggers]
    for logger in loggers:
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
    try:
        client, http_client = make_client(base_url, token)
        with http_client:
            client.models.list()
            chat(client, "hello")
            for _ in chat(client, "hello", stream=True):
                pass
            client.close()
    finally:
        for logger, (level, propagate) in zip(loggers, previous):
            logger.removeHandler(handler)
            logger.setLevel(level)
            logger.propagate = propagate
    captured = buffer.getvalue()
    # Guard against a vacuous pass: an empty buffer would satisfy the
    # "token absent" assertions without any logging having happened.
    assert captured.strip(), "no SDK debug logging was captured"
    assert "chat/completions" in captured, (
        "captured logs do not mention the requests that were made"
    )
    assert token not in captured, "bearer token appeared in SDK debug logs"
    assert f"Bearer {token}" not in captured
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token-file", required=True, type=Path)
    args = parser.parse_args()

    prove_destination_and_redirect_guards()
    token = args.token_file.read_text(encoding="utf-8")
    if token.endswith("\n"):
        token = token[:-1]
    transport = LoopbackGuardTransport()
    with httpx.Client(
        transport=transport,
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(5.0),
    ) as http_client:
        client = openai.OpenAI(
            api_key=token,
            base_url=args.base_url,
            http_client=http_client,
            max_retries=0,
        )
        models = client.models.list()
        assert [model.id for model in models.data] == ["pulsarmlx-synthetic-v1"]
        completion = client.chat.completions.create(
            model="pulsarmlx-synthetic-v1",
            messages=[{"role": "user", "content": "hello"}],
        )
        assert completion.choices[0].message.content == "SYNTHETIC_OK: café 🚀"
        assert completion.choices[0].finish_reason == "stop"
        assert completion.usage is not None
        assert completion.usage.completion_tokens == 3

        chunks = client.chat.completions.create(
            model="pulsarmlx-synthetic-v1",
            messages=[{"role": "user", "content": "hello"}],
            stream=True,
        )
        content: list[str] = []
        finish_reason = None
        ids: list[str] = []
        created: list[int] = []
        for chunk in chunks:
            ids.append(chunk.id)
            created.append(chunk.created)
            if chunk.choices[0].delta.content:
                content.append(chunk.choices[0].delta.content)
            if chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason
        assert "".join(content) == "SYNTHETIC_OK: café 🚀"
        assert finish_reason == "stop"
        assert len(set(ids)) == 1
        assert len(set(created)) == 1
        client.close()

    prove_authentication_and_errors(args.base_url, token)
    prove_rate_limit(args.base_url, token)
    prove_timeout_cancellation_and_disconnect(args.base_url, token)
    prove_streaming_failure_surfaces(args.base_url, token)
    prove_bounded_requests_and_assembly(args.base_url, token)
    prove_no_sensitive_content_in_client_logs(args.base_url, token)

    print(f"SDK_COMPAT_OK openai={openai.__version__}")


if __name__ == "__main__":
    main()
