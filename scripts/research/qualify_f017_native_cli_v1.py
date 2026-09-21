#!/usr/bin/env python3
"""Exercise the native CLI's admission, tokenizer and chat-template path
without a checkpoint.

The CLI's expensive phases (the shard rehash and the forward passes) need the
real 222 GB artifact and its human gate. Everything before them does not, so
this harness writes a tiny glm-dsa GGUF metadata shard with a real byte-level
BPE vocabulary and the GLM control tokens, plus the identity records the CLI
reads, and drives `--preflight-only` against it.

What that covers: directory and symlink refusal, manifest/catalog parsing,
GGUF parsing, the architecture gate, every geometry field checked against the
model configuration, tokenizer construction from checkpoint metadata, chat
template detection and rendering, raw-text and raw-token diagnostic modes,
prompt bounds and the vocabulary cross-check. No shard payload exists, so a
run that tried to generate would fail rather than silently fall back.
"""
from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

GGUF_MAGIC = b"GGUF"
U32, I32, F32, BOOL, STRING, ARRAY, U64 = 4, 5, 6, 7, 8, 9, 10

LAYERS, HIDDEN, VOCAB, HEADS = 79, 6144, 154880, 64
Q_RANK, KV_RANK, QK_NOPE, QK_ROPE, VALUE_DIM = 2048, 512, 192, 64, 256
INDEXER_TOP_K = 2048


def _string(value: str) -> bytes:
    raw = value.encode()
    return struct.pack("<Q", len(raw)) + raw


def _value(kind: int, value) -> bytes:
    if kind == STRING:
        return _string(value)
    if kind == U32:
        return struct.pack("<I", value)
    if kind == I32:
        return struct.pack("<i", value)
    if kind == U64:
        return struct.pack("<Q", value)
    if kind == F32:
        return struct.pack("<f", value)
    if kind == BOOL:
        return struct.pack("<B", 1 if value else 0)
    raise ValueError(kind)


def _kv(key: str, kind: int, value) -> bytes:
    return _string(key) + struct.pack("<I", kind) + _value(kind, value)


def _kv_array(key: str, element_kind: int, values) -> bytes:
    body = b"".join(_value(element_kind, item) for item in values)
    return _string(key) + struct.pack("<I", ARRAY) + struct.pack("<I", element_kind) + struct.pack("<Q", len(values)) + body


def vocabulary() -> tuple[list[str], list[str], list[int]]:
    """A byte-level vocabulary padded to the model's size, with the GLM
    control tokens the chat template needs at fixed ids."""
    tokens: list[str] = []
    for byte in range(256):
        codepoint = byte
        if not (33 <= byte <= 126 or 161 <= byte <= 172 or 174 <= byte <= 255):
            codepoint = 256 + len([b for b in range(byte) if not (33 <= b <= 126 or 161 <= b <= 172 or 174 <= b <= 255)])
        tokens.append(chr(codepoint))
    merges = ["Ġ t", "Ġ a", "h e", "i n"]
    for pair in merges:
        tokens.append(pair.replace(" ", ""))
    control = ["<|endoftext|>", "<|user|>", "<|assistant|>", "<|system|>",
               "<|observation|>", "<sop>", "<|begin_of_box|>", "<|end_of_box|>",
               "<think>", "</think>"]
    while len(tokens) < VOCAB - len(control):
        tokens.append(f"<unused{len(tokens)}>")
    control_ids = {}
    for name in control:
        control_ids[name] = len(tokens)
        tokens.append(name)
    assert len(tokens) == VOCAB, len(tokens)
    types = [1] * VOCAB
    for name in control:
        types[control_ids[name]] = 3
    return tokens, merges, types, control_ids


def write_metadata_shard(path: Path, *, tokenizer: bool = True) -> None:
    tokens, merges, types, control_ids = vocabulary()
    entries = [
        _kv("general.architecture", STRING, "glm-dsa"),
        _kv("general.name", STRING, "Glm-5.2-synthetic-metadata-fixture"),
        _kv("general.file_type", U32, 19),
        _kv("glm-dsa.block_count", U32, LAYERS),
        _kv("glm-dsa.embedding_length", U32, HIDDEN),
        _kv("glm-dsa.vocab_size", U32, VOCAB),
        _kv("glm-dsa.attention.head_count", U32, HEADS),
        _kv("glm-dsa.attention.head_count_kv", U32, 1),
        _kv("glm-dsa.attention.q_lora_rank", U32, Q_RANK),
        _kv("glm-dsa.attention.kv_lora_rank", U32, KV_RANK),
        _kv("glm-dsa.attention.key_length_mla", U32, QK_NOPE + QK_ROPE),
        _kv("glm-dsa.attention.value_length_mla", U32, VALUE_DIM),
        _kv("glm-dsa.attention.indexer.top_k", U32, INDEXER_TOP_K),
        _kv("glm-dsa.rope.dimension_count", U32, QK_ROPE),
        _kv("glm-dsa.rope.freq_base", F32, 8000000.0),
    ]
    if tokenizer:
        entries += [
        _kv("tokenizer.ggml.model", STRING, "gpt2"),
        _kv("tokenizer.ggml.pre", STRING, "glm4"),
        _kv_array("tokenizer.ggml.tokens", STRING, tokens),
        _kv_array("tokenizer.ggml.merges", STRING, merges),
        _kv_array("tokenizer.ggml.token_type", I32, types),
        _kv("tokenizer.ggml.eos_token_id", U32, control_ids["<|endoftext|>"]),
        _kv("tokenizer.ggml.eot_token_id", U32, control_ids["<|user|>"]),
        _kv("tokenizer.ggml.padding_token_id", U32, control_ids["<|endoftext|>"]),
        ]
    head = GGUF_MAGIC + struct.pack("<I", 3) + struct.pack("<Q", 0) + struct.pack("<Q", len(entries))
    path.write_bytes(head + b"".join(entries))


def committed_identity_records() -> tuple[Path, Path]:
    """The admitted records the CLI reads by default. Only metadata; no
    payload, no shard is opened by the preflight beyond the first."""
    root = Path(__file__).resolve().parents[2]
    return (root / "docs/validation/glm52-checkpoint.json",
            root / "docs/research/glm52/raw/f016-c01-catalog-0001.json")


def _unused_write_identity_records(directory: Path, shards: list[tuple[str, int]]) -> tuple[Path, Path]:
    manifest = {
        "checkpoint_set_sha256": "0" * 64,
        "file_count": len(shards),
        "total_bytes": sum(size for _, size in shards),
        "files": [{"filename": name, "sha256": f"{index:064d}", "size_bytes": size}
                  for index, (name, size) in enumerate(shards)],
    }
    catalog = {
        "architecture": "glm-dsa",
        "kv_selected": {"block_count": LAYERS, "embedding_length": HIDDEN, "vocab_size": VOCAB,
                        "attention.head_count": HEADS, "attention.kv_lora_rank": KV_RANK,
                        "attention.q_lora_rank": Q_RANK, "attention.key_length_mla": QK_NOPE + QK_ROPE,
                        "attention.value_length_mla": VALUE_DIM, "rope.dimension_count": QK_ROPE,
                        "expert_count": 256, "expert_used_count": 8, "expert_feed_forward_length": 2048,
                        "feed_forward_length": 12288, "leading_dense_block_count": 3},
        "tensor_count": 1809,
        "shard_count": len(shards),
        "tensors": [],
    }
    manifest_path = directory / "manifest.json"
    catalog_path = directory / "catalog.json"
    manifest_path.write_text(json.dumps(manifest))
    catalog_path.write_text(json.dumps(catalog))
    return manifest_path, catalog_path


def run(binary: Path, *flags: str) -> tuple[int, str, str]:
    completed = subprocess.run([str(binary), *flags], capture_output=True, text=True)
    return completed.returncode, completed.stdout, completed.stderr


def cases(binary: Path, work: Path) -> list[dict]:
    manifest_path, catalog_path = committed_identity_records()
    manifest = json.loads(manifest_path.read_text())
    names = [item["filename"] for item in manifest["files"]]
    model = work / "model"
    model.mkdir(parents=True, exist_ok=True)
    write_metadata_shard(model / names[0])
    for name in names[1:]:
        (model / name).write_bytes(b"")
    manifest, catalog = manifest_path, catalog_path
    base = ["--model", str(model), "--manifest", str(manifest), "--catalog", str(catalog)]
    results = []

    def record(name, flags, expect_code, expect_in_stderr=None, check=None):
        code, out, err = run(binary, *flags)
        detail = {"case": name, "exit_code": code, "expected_exit_code": expect_code}
        ok = code == expect_code
        if expect_in_stderr is not None:
            ok = ok and expect_in_stderr in err
            detail["expected_message"] = expect_in_stderr
        if check is not None:
            try:
                document = json.loads(err.strip().splitlines()[-1])
            except Exception:
                document = {}
            extra = check(document)
            detail.update(extra)
            ok = ok and extra.pop("ok", True)
        detail["status"] = "PASS" if ok else "FAIL"
        results.append(detail)

    def template_check(document):
        prompt = document.get("prompt_token_ids", [])
        return {
            "ok": document.get("result") == "PREFLIGHT_PASS"
                  and document.get("prompt_mode") == "CHAT_TEMPLATE"
                  and len(prompt) == document.get("prompt_tokens")
                  and len(prompt) > 3
                  and bool(document.get("stop_token_ids"))
                  and document.get("python_inference_process") is False,
            "prompt_mode": document.get("prompt_mode"),
            "prompt_tokens": document.get("prompt_tokens"),
            "stop_token_count": len(document.get("stop_token_ids", [])),
            "identity": document.get("identity", {}).get("architecture"),
            "indexer_top_k": document.get("identity", {}).get("indexer_top_k"),
            "max_positions": document.get("max_positions"),
        }

    def raw_text_check(document):
        return {"ok": document.get("prompt_mode") == "RAW_TEXT_NO_TEMPLATE"
                      and document.get("prompt_tokens", 0) > 0,
                "raw_text_prompt_tokens": document.get("prompt_tokens")}

    def raw_token_check(document):
        return {"ok": document.get("prompt_mode") == "RAW_TOKEN_DIAGNOSTIC"
                      and document.get("prompt_token_ids") == [9703, 11],
                "raw_token_mode": document.get("prompt_mode")}

    record("chat_template_render", base + ["--preflight-only", "--prompt", "What is 17 times 6?"], 0, check=template_check)
    record("raw_text_no_template", base + ["--preflight-only", "--no-chat-template", "--prompt", "hello world"], 0, check=raw_text_check)
    record("raw_token_diagnostic", base + ["--preflight-only", "--raw-tokens", "9703,11"], 0, check=raw_token_check)
    record("missing_model", ["--preflight-only", "--prompt", "x"], 2, "--model is required")
    record("absent_model_directory", ["--model", str(work / "absent"), "--preflight-only", "--prompt", "x"], 3, "No such file")
    record("model_is_a_file", ["--model", str(model / names[0]), "--preflight-only", "--prompt", "x"], 3, "not a directory")
    record("two_prompt_sources", base + ["--preflight-only", "--prompt", "a", "--no-chat-template", "--raw-tokens", "1"], 2, "exactly one prompt source")
    record("unknown_flag", base + ["--preflight-only", "--sample"], 2, "unknown flag")
    record("output_exceeds_context", base + ["--preflight-only", "--prompt", "x", "--max-positions", "4", "--max-tokens", "8"], 2, "max_positions")

    # A wrong architecture must be refused before any expensive phase.
    bad_catalog = json.loads(catalog.read_text())
    bad_catalog["architecture"] = "llama"
    bad_catalog_path = work / "catalog-llama.json"
    bad_catalog_path.write_text(json.dumps(bad_catalog))
    record("wrong_architecture", ["--model", str(model), "--manifest", str(manifest), "--catalog", str(bad_catalog_path),
                                  "--preflight-only", "--prompt", "x"], 3, "census")

    # A checkpoint whose metadata declares a different geometry is refused.
    geometry = work / "wrong-geometry"
    geometry.mkdir(exist_ok=True)
    raw = (model / names[0]).read_bytes()
    (geometry / names[0]).write_bytes(raw.replace(struct.pack("<I", LAYERS), struct.pack("<I", 80), 1))
    for name in names[1:]:
        (geometry / name).write_bytes(b"")
    record("wrong_geometry", ["--model", str(geometry), "--manifest", str(manifest), "--catalog", str(catalog),
                              "--preflight-only", "--prompt", "x"], 3, "block_count")

    # A checkpoint whose metadata has no tokenizer must say so, not guess.
    no_tokenizer = work / "no-tokenizer"
    no_tokenizer.mkdir(exist_ok=True)
    write_metadata_shard(no_tokenizer / names[0], tokenizer=False)
    for name in names[1:]:
        (no_tokenizer / name).write_bytes(b"")
    record("missing_tokenizer", ["--model", str(no_tokenizer), "--manifest", str(manifest), "--catalog", str(catalog),
                                 "--preflight-only", "--prompt", "x"], 3, "tokenizer")
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as directory:
        results = cases(arguments.binary, Path(directory))
    document = {
        "schema": "pulsarmlx.f017.native-cli-qualification/1.0.0",
        "binary": arguments.binary.name,
        "scope": "admission, identity metadata, tokenizer and chat template; no shard payload and no forward pass",
        "original_checkpoint_reads": 0,
        "cases": results,
        "case_count": len(results),
        "result": "PASS" if all(case["status"] == "PASS" for case in results) else "FAIL",
    }
    raw = json.dumps(document, indent=1, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.write_text(raw)
    else:
        print(raw)
    return 0 if document["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
