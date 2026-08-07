#!/usr/bin/env python3
"""Tokenizer-optional generation harness with pluggable forward()."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


# Frozen prompt texts (token IDs filled when tokenizer available)
FROZEN_PROMPTS = {
    "P-MIN": "Hello",
    "P-FACT": "What is the capital of France?",
    "P-CODE": "Write a Python function that returns 42.",
    "P-REASON": (
        "If all cats are animals and some animals are black, "
        "can we conclude some cats are black? Answer yes or no and one sentence."
    ),
}


class ForwardFn(Protocol):
    def __call__(self, token_ids: list[int]) -> list[float]:
        """Return logits for last position."""
        ...


@dataclass
class GenStep:
    prefix: list[int]
    logits_top1: int
    top5: list[int]


def greedy_argmax(logits: list[float]) -> int:
    best_i = 0
    best_v = logits[0]
    for i, v in enumerate(logits):
        if v > best_v or (v == best_v and i < best_i):
            best_v = v
            best_i = i
    return best_i


def topk(logits: list[float], k: int = 5) -> list[int]:
    return sorted(range(len(logits)), key=lambda i: (-logits[i], i))[:k]


def generate_greedy(
    prompt_ids: list[int],
    forward: ForwardFn,
    n_new: int,
) -> dict:
    tokens = list(prompt_ids)
    steps: list[dict] = []
    for _ in range(n_new):
        logits = forward(tokens)
        g = greedy_argmax(logits)
        steps.append(
            {
                "prefix_len": len(tokens),
                "greedy": g,
                "top5": topk(logits, 5),
            }
        )
        tokens.append(g)
    return {
        "prompt_ids": list(prompt_ids),
        "generated_ids": tokens[len(prompt_ids) :],
        "full_ids": tokens,
        "steps": steps,
    }


class DummyForward:
    """Deterministic fake logits for harness tests (not a model)."""

    def __init__(self, vocab: int = 1000) -> None:
        self.vocab = vocab

    def __call__(self, token_ids: list[int]) -> list[float]:
        # next token = (sum(ids) + len) % vocab with a clear peak
        peak = (sum(token_ids) + len(token_ids)) % self.vocab
        logits = [-1.0] * self.vocab
        logits[peak] = 10.0
        return logits
