"""Completion-termination policy for the paged GLM-5.3-Flash paths (unpruned-persistent G54). Stdlib only.

Diagnosis (raw-id evidence in the private record): the checkpoint declares three assistant-turn terminal ids in its own
config.json / generation_config.json - <|endoftext|> 154820, <|user|> 154827, <|observation|> 154829 - but the paged
loader builds the processor with mlx_vlm.utils.load_processor(path) and no eos_token_ids, so the tokenizer's
StoppingCriteria holds only the tokenizer's own eos (<|endoftext|>). mlx_vlm.generate() resets the criteria from
model.config.eos_token_id before generating; stream_generate() does not. The streaming runner and the HTTP server
therefore ran past <|user|> (the model's end-of-assistant-turn marker), which then spelled a new role and kept going
until max_tokens. The historical held-out token streams show exactly that: the answer, then 154827, then more tokens,
never 154820.

Policy glm5-eos-v1: terminal ids = the checkpoint config's eos_token_id list, each verified to be a special (control)
token of the tokenizer, installed into the tokenizer's StoppingCriteria before generation. The generator stops on the
first terminal id: that token is never yielded as text and never followed by another sampled token; finish_reason is
'stop'; generation_tokens counts only the yielded tokens (the terminal id is not counted). Single-token boundaries
only: this model's turn boundaries are single control ids, so no multi-token matcher or holdback is needed. Prompt-side
markers are never scanned: the criteria apply to generated ids only. Upstream ambiguity: the tokenizer maps the literal
text "<|user|>" inside a prompt to the control id 154827 as well; a generated 154827 is therefore always the control
token (there is no separate text spelling), which is the correct thing to stop on. Tool boundaries (<|observation|>)
end the turn as declared by the checkpoint; tool calls are not supported by these paths and are not claimed.
"""
from __future__ import annotations

import json
import os
from typing import Optional

POLICY_VERSION = "glm5-eos-v1"
LEGACY_VERSION = "legacy-tokenizer-eos"


def terminal_ids_from_config(config: dict) -> list:
    """The checkpoint's declared eos ids (top level, else text_config); an int becomes a one-element list."""
    for c in (config, config.get("text_config") or {}):
        ids = c.get("eos_token_id")
        if ids is not None:
            return [int(ids)] if isinstance(ids, int) else [int(i) for i in ids]
    raise ValueError("EOS_TOKEN_ID_MISSING")


def verify_terminal_ids(ids, tokenizer) -> dict:
    """Each terminal id must be a control token of the tokenizer (an added/special token), never ordinary text."""
    special = set(getattr(tokenizer, "all_special_ids", []) or [])
    added = getattr(tokenizer, "added_tokens_decoder", {}) or {}
    names = {}
    for i in ids:
        tok = tokenizer.convert_ids_to_tokens(int(i))
        is_special = int(i) in special or int(i) in added or (isinstance(tok, str) and tok.startswith("<") and tok.endswith(">"))
        if not is_special:
            raise ValueError(f"TERMINAL_ID_NOT_SPECIAL {i} -> {tok!r}")
        names[int(i)] = tok
    return names


def build(model_dir: str, tokenizer, version: str = POLICY_VERSION) -> dict:
    """The policy record for a checkpoint directory: {'version', 'terminal_ids', 'names', 'source'}."""
    if version == LEGACY_VERSION:
        ids = [int(tokenizer.eos_token_id)]
        return {"version": LEGACY_VERSION, "terminal_ids": ids, "names": {ids[0]: tokenizer.convert_ids_to_tokens(ids[0])}, "source": "tokenizer.eos_token_id only (the pre-G54 behaviour of the streaming paths)"}
    if version != POLICY_VERSION:
        raise ValueError(f"STOP_POLICY_UNKNOWN {version}")
    config = json.load(open(os.path.join(model_dir, "config.json")))
    ids = terminal_ids_from_config(config)
    names = verify_terminal_ids(ids, tokenizer)
    return {"version": POLICY_VERSION, "terminal_ids": ids, "names": names, "source": "config.json eos_token_id, verified as control tokens"}


def apply(processor, policy: dict) -> dict:
    """Install the policy into the tokenizer's StoppingCriteria (what mlx_vlm.stream_generate consults). Returns the
    installed id list as read back from the criteria."""
    tok = processor.tokenizer if hasattr(processor, "tokenizer") else processor
    crit = getattr(tok, "stopping_criteria", None)
    if crit is None:
        raise RuntimeError("NO_STOPPING_CRITERIA")
    crit.reset(list(policy["terminal_ids"]))
    installed = list(crit.eos_token_ids)
    if sorted(installed) != sorted(int(i) for i in policy["terminal_ids"]):
        raise RuntimeError(f"STOP_POLICY_NOT_INSTALLED {installed} != {policy['terminal_ids']}")
    return {"installed_terminal_ids": installed}


class StopMatcher:
    """Single-token terminal matcher usable by fake generators and tests: is_terminal(id)."""
    def __init__(self, terminal_ids):
        self.terminal_ids = set(int(i) for i in terminal_ids)

    def is_terminal(self, token_id) -> bool:
        return token_id is not None and int(token_id) in self.terminal_ids

    def truncate(self, ids):
        """The prefix a stopping generator would have emitted: ids before the first terminal id (the terminal id excluded)."""
        out = []
        for t in ids:
            if self.is_terminal(t):
                break
            out.append(t)
        return out
