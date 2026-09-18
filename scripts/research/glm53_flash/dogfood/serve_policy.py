"""Request-side decisions of the dogfood server that need no model (graph 34): speculative eligibility.

MTPSpeculator.generate prefills the prompt in ONE chunk (the MTP layer needs the hidden state of every prompt position)
and rejects prompts longer than its limit; the server must know that before it commits to the speculative path - after
the SSE headers are out there is no clean error. Eligibility is decided here from the request's sampling parameters and
the tokenized prompt length, and the ordinary stream_generate path is the fallback. Stdlib only.
"""
from __future__ import annotations

from typing import Optional


def speculative_eligible(has_speculator: bool, temperature: float, top_p: Optional[float], repetition_penalty: Optional[float],
                         prompt_tokens: int, max_prompt_tokens: int) -> tuple:
    """(eligible, reason). Greedy sampling only (the verifier accepts argmax drafts), and the prompt must fit the
    speculator's one-chunk prefill: prompt_tokens <= max_prompt_tokens."""
    if not has_speculator:
        return False, "no speculator loaded"
    if temperature != 0.0:
        return False, f"temperature {temperature} != 0 (speculation verifies argmax drafts only)"
    if top_p is not None:
        return False, "top_p set (speculation is greedy only)"
    if repetition_penalty is not None:
        return False, "repetition_penalty set (speculation is greedy only)"
    if prompt_tokens > max_prompt_tokens:
        return False, f"prompt {prompt_tokens} tokens > speculative one-chunk limit {max_prompt_tokens}"
    return True, f"greedy; prompt {prompt_tokens} <= {max_prompt_tokens}"
