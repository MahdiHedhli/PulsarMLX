#!/usr/bin/env python3
"""Official OpenAI SDK compatibility check against the synthetic loopback API."""

from __future__ import annotations

import argparse
import io
import ipaddress
import logging
import threading
import time
import json
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


class InvalidContentionExperiment(AssertionError):
    """The holder lost its bounded lease; no capacity conclusion is valid."""


class ContentionHolder:
    """Continuously observe a streaming holder within its unchanged 2s lease."""

    def __init__(self, client: openai.OpenAI) -> None:
        self.client = client
        self.started = threading.Event()
        self.admitted = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()
        self.failure: BaseException | None = None
        self.stream = None
        self.request_started = None
        self.events = []
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._run)

    def note(self, event: str) -> None:
        with self.lock:
            self.events.append({"event": event, "monotonic": time.monotonic()})

    def start(self) -> None:
        self.thread.start()

    def _run(self) -> None:
        self.request_started = time.monotonic()
        self.note("request_started")
        self.started.set()
        try:
            self.stream = chat(self.client, "__synthetic_hold__", stream=True)
            for chunk in self.stream:
                delta = chunk.choices[0].delta
                if delta.role == "assistant":
                    self.note("admitted")
                    self.admitted.set()
            if not self.admitted.is_set():
                raise AssertionError("holder stream ended before admission")
            if not self.release.is_set():
                raise InvalidContentionExperiment("HOLDER_STREAM_ENDED")
        except BaseException as error:
            if not self.release.is_set():
                self.note("holder_failed_" + type(error).__name__)
                self.failure = error
        finally:
            try:
                if self.stream is not None:
                    self.stream.close()
            except BaseException as error:
                self.failure = self.failure or error
            finally:
                self.note("reader_finished")
                self.finished.set()

    def await_admission(self, seconds: float = 5.0) -> None:
        if not self.started.wait(seconds):
            raise AssertionError("holder did not start")
        if not self.admitted.wait(seconds):
            if self.failure is not None:
                raise AssertionError(
                    f"holder failed before admission: {type(self.failure).__name__}"
                ) from self.failure
            raise AssertionError("holder did not acknowledge admission")
        if self.failure is not None:
            raise AssertionError(
                f"holder failed after admission: {type(self.failure).__name__}"
            ) from self.failure
        self.ensure_active()

    def ensure_active(self) -> None:
        if self.failure is not None:
            raise InvalidContentionExperiment("HOLDER_FAILED") from self.failure
        if self.finished.is_set() or self.release.is_set():
            raise InvalidContentionExperiment("HOLDER_RELEASED")
        # A conservative bound starts before the server creates its deadline.
        # We never infer continued ownership merely from Python scheduling.
        if self.request_started is None or time.monotonic() - self.request_started >= 2.0:
            raise InvalidContentionExperiment("HOLDER_LEASE_WINDOW_EXPIRED")

    def close(self) -> None:
        self.note("release_requested")
        self.release.set()
        close_error = None
        try:
            if self.stream is not None:
                self.stream.close()
        except BaseException as error:
            close_error = error
        self.thread.join(timeout=10.0)
        if self.thread.is_alive():
            raise AssertionError("holder did not finish after release")
        if not self.finished.is_set():
            raise AssertionError("holder cleanup signaling was lost")
        if close_error is not None or self.failure is not None:
            error = close_error or self.failure
            raise AssertionError(
                f"holder failed: {type(error).__name__}"
            ) from error


def validate_busy_error(error: openai.APIError) -> None:
    if not isinstance(error, openai.RateLimitError):
        raise AssertionError("CONTENDER_WRONG_ERROR_CLASS")
    assert error.status_code == 429, "CONTENDER_WRONG_BUSY_STATUS"
    body = error_body(error)
    assert body.get("code") == "server_busy", "CONTENDER_WRONG_BUSY_CODE"
    assert body.get("type") == "rate_limit_error", "CONTENDER_WRONG_BUSY_TYPE"


def perform_contention(holder, contender) -> None:
    holder.await_admission()
    holder.ensure_active()
    holder.note("contender_started")
    try:
        contender()
    except openai.APIError as error:
        holder.note("contender_response")
        holder.ensure_active()
        validate_busy_error(error)
    else:
        holder.note("contender_response")
        holder.ensure_active()
        raise AssertionError("CONTENDER_SUCCEEDED_WHILE_HELD")


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
    """A holder proven admitted must make one contender receive server_busy."""
    # Keep cancellation's read wakeup strictly inside the owned join bound.
    holder_client, holder_http = make_client(base_url, token, timeout=1.0)
    holder = ContentionHolder(holder_client)
    client, http_client = make_client(base_url, token)
    try:
        holder.start()
        with http_client:
            perform_contention(holder, lambda: chat(client, "hello"))
            client.close()
    finally:
        try:
            holder.close()
        finally:
            holder_client.close()
            holder_http.close()
            client.close()
            http_client.close()
    print("SDK_CONTENTION_EVENTS " + json.dumps(holder.events, sort_keys=True))


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
