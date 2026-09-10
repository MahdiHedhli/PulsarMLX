#!/usr/bin/env python3
"""Official OpenAI SDK compatibility check against the synthetic loopback API."""

from __future__ import annotations

import argparse
import ipaddress
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

    print(f"SDK_COMPAT_OK openai={openai.__version__}")


if __name__ == "__main__":
    main()
