"""Artifact and identity checks for the explicitly unpruned paged serving path (stdlib; unpruned-persistent G55)."""
import hashlib
import json
import os


def verify_artifact(offload_dir: str, max_expert_cache_bytes: int, expert_cache_bytes: int) -> dict:
    """Refuse before any load: missing repack, non-contiguous layout, pruned checkpoint, over-budget cache."""
    index_path = os.path.join(offload_dir, "offload_index.json")
    if not os.path.exists(index_path):
        raise SystemExit(f"REPACK_MISSING {index_path} (this entrypoint never repacks)")
    idx = json.load(open(index_path))
    if idx.get("layout") != "expert-contiguous/1":
        raise SystemExit(f"LAYOUT_NOT_CONTIGUOUS {idx.get('layout')!r}: the accepted configuration (coalescing gap) needs the contiguous repack")
    config = json.load(open(os.path.join(offload_dir, "config.json")))
    text = config.get("text_config", config)
    n_experts = int(text.get("n_routed_experts") or 0); topk = int(text.get("num_experts_per_tok") or 0)
    if config.get("reap") is not None or n_experts != 288:
        raise SystemExit(f"NOT_UNPRUNED n_routed_experts={n_experts} reap={config.get('reap')!r}: this path serves the unpruned checkpoint only")
    if int(idx.get("num_experts", 0)) != n_experts:
        raise SystemExit(f"EXPERT_COUNT_MISMATCH index {idx.get('num_experts')} vs config {n_experts}")
    if expert_cache_bytes > max_expert_cache_bytes:
        raise SystemExit(f"EXPERT_CACHE_OVER_BUDGET {expert_cache_bytes} > {max_expert_cache_bytes}")
    layers = [os.path.join(offload_dir, "experts", f"layer_{lid:04d}.safetensors") for lid in idx["layers"]]
    missing = [p for p in layers if not os.path.exists(p)]
    if missing:
        raise SystemExit(f"EXPERT_FILES_MISSING {len(missing)} (first: {missing[0]})")
    return {"n_routed_experts": n_experts, "num_experts_per_tok": topk, "moe_layers": len(idx["layers"]), "layout": idx["layout"], "quantization_default": {k: config.get("quantization", {}).get(k) for k in ("group_size", "bits")},
            "model_type": text.get("model_type"), "config_sha256": _sha(os.path.join(offload_dir, "config.json")), "tokenizer_sha256": _sha(os.path.join(offload_dir, "tokenizer.json")), "chat_template_sha256": _sha(os.path.join(offload_dir, "chat_template.jinja")), "offload_index_sha256": _sha(index_path)}


def _sha(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


