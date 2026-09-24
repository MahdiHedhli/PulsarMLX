#!/usr/bin/env python3
"""F020 Slice 2C -- synthetic expert-plane composition fixtures and the independent selection oracle.

Standard library only. Deterministic: the same generator bytes (and the same
frozen Slice 2B generator bytes it borrows helpers from) always produce the
same fixture bytes and the same manifest. Nothing here calls MLX, any array
library, cargo, or any PulsarMLX crate. In particular the production slicing
(`AffineTriple::expert_slice` / `row_slice`) and the production decoder are
never invoked: every expected byte range and every expected plane byte is
computed by this file's own oracle from the fixture SPECIFICATION (module
geometry, shard layout, per-expert generated arrays), and is then cross-checked
against a second, separate stdlib parse of the written shard headers.

Contract: specs/020-mlx-safetensors-affine/contracts/native-composition-v1.json.
Inherited: specs/020-mlx-safetensors-affine/contracts/native-primitives-v1.json
(Slice 2B, sha256 76959ccb...). The Slice 2B generator
(scripts/research/f020_native_primitives_fixtures_v1.py, sha256 28078a6d...) is
loaded read-only, after its sha256 is verified, for its PRNG, its frozen value
draws, its LSB-first packer, its 0.31.2 kernel-family transcription and its
per-guard domain classifier; it is never edited and never re-implemented here.

The only arithmetic performed is exact integer arithmetic on offsets and sizes
(to state the oracle's ranges and the refusal guards) and the Slice 2B exact
classifier (to prove each accepted plane is inside D-GEOM/D-NUM and each
inherited-refusal probe violates exactly one Slice 2B guard). Nothing predicts
an MLX output.

Usage:
    f020_native_composition_fixtures_v1.py --out fixtures/native-composition
    f020_native_composition_fixtures_v1.py --out fixtures/native-composition --check
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path

SCHEMA = "pulsarmlx.f020.native-composition-fixtures/1.0.0"
CONTRACT_SCHEMA = "pulsarmlx.f020.native-composition-contract/1.0.0-draft.1"
GENERATOR_PATH = "scripts/research/f020_native_composition_fixtures_v1.py"

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
S2B_GENERATOR_PATH = "scripts/research/f020_native_primitives_fixtures_v1.py"
S2B_GENERATOR_SHA256 = "28078a6d0a6de859c1a1ac557fef3f683d8ecd75a780198b4c0bc7c15c267999"
S2B_CONTRACT_SHA256 = "76959ccb13046c664db67469fd8186b7fb668910072060400b38b682e92fec72"

U64_MAX = (1 << 64) - 1
PY_EXACT_MAC_LIMIT = 1 << 21        # Slice 2B frozen_population / generator constant
FORBIDDEN_NAME_TOKENS = ("glm", "pipenetwork", "qwen", "switch_mlp", "self_attn", "lm_head",
                         "deepseek", "mixtral", "llama", "gpt")

# Composition refusal order (contract composition_refusals.order), evaluated
# before any native call; the Slice 2B order then applies to the selected plane.
COMPOSITION_REFUSAL_ORDER = [
    "C-R-RESOLVE", "C-R-SOURCE-BINDING", "C-R-MODULE-BINDING",
    "C-R-INDEX-RANK", "C-R-INDEX-RANGE", "C-R-OVERFLOW", "C-R-BACKING",
]
SELECTION_CHECKS = ["S-IDENTITY", "S-RANGES", "S-BYTES", "S-STAGED-EQUAL", "S-SOURCE-UNCHANGED"]
COMPONENTS = ("weight", "scales", "biases")
SUFFIX = {"weight": ".weight", "scales": ".scales", "biases": ".biases"}
WIDTH = {"U32": 4, "F32": 4, "F16": 2, "BF16": 2}


# ------------------------------------------------ the frozen Slice 2B helpers --
def load_slice2b():
    """Load the frozen Slice 2B generator as a module, refusing any other bytes."""
    path = REPOSITORY_ROOT / S2B_GENERATOR_PATH
    raw = path.read_bytes()
    got = hashlib.sha256(raw).hexdigest()
    if got != S2B_GENERATOR_SHA256:
        raise SystemExit("frozen Slice 2B generator sha256 %s != %s" % (got, S2B_GENERATOR_SHA256))
    spec = importlib.util.spec_from_file_location("f020_slice2b_frozen_generator", path)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load the frozen Slice 2B generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S = load_slice2b()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def seed(label: str) -> int:
    """Per-draw seed: first 8 bytes (big-endian) of sha256(b'f020-2c:' + label)."""
    return int.from_bytes(hashlib.sha256(b"f020-2c:" + label.encode()).digest()[:8], "big")


def canonical(value) -> bytes:
    return (json.dumps(value, indent=1, sort_keys=True) + "\n").encode()


# ------------------------------------------------------------ module specs ----
class ModuleSpec:
    """One stacked affine module [E, N, K*bits/32] / [E, N, K/group], metadata BF16."""

    def __init__(self, name, bits, E, N, K, group=64, meta="BF16", tweak=None):
        self.name, self.bits, self.E, self.N, self.K = name, bits, E, N, K
        self.group, self.meta, self.tweak = group, meta, tweak
        assert K % group == 0 and (K * bits) % 32 == 0
        self.P = K * bits // 32          # packed u32 columns
        self.G = K // group              # groups per row
        # Oracle plane sizes, from the specification (not from stored shapes).
        self.plane_bytes = {"weight": N * self.P * 4,
                            "scales": N * self.G * WIDTH[meta],
                            "biases": N * self.G * WIDTH[meta]}

    def shapes(self):
        return {"weight": ("U32", [self.E, self.N, self.P]),
                "scales": (self.meta, [self.E, self.N, self.G]),
                "biases": (self.meta, [self.E, self.N, self.G])}


def tweak_meta_range_expert1(e, scales, biases):
    """stack_r, expert 1 only: one scale becomes 2^-33 -- a NORMAL bfloat16 value
    below the D-NUM magnitude floor 2^-32 (R-DOMAIN-META-RANGE), and nothing else."""
    if e == 1:
        scales[5] = S.pow2_bits("BF16", -33)


def generate_module(data_key: str, spec: ModuleSpec):
    """Per-expert arrays, each drawn from its own seed. Returns a list (one per
    expert) of dicts: codes, words, scale/bias bit patterns and the three
    serialized components. The stacked tensor is their concatenation."""
    planes = []
    for e in range(spec.E):
        rng = S.SplitMix64(seed("%s/%s/expert/%d" % (data_key, spec.name, e)))
        codes = S.draw_codes(rng, spec.N * spec.K, spec.bits)
        scales = S.draw_meta(rng, spec.meta, spec.N * spec.G, "scale")
        biases = S.draw_meta(rng, spec.meta, spec.N * spec.G, "bias")
        if spec.tweak:
            spec.tweak(e, scales, biases)
        words = S.pack_rows(codes, spec.N, spec.K, spec.bits)
        planes.append({
            "codes": codes, "words": words, "scale_bits": scales, "bias_bits": biases,
            "weight": S.to_bytes("U32", words),
            "scales": S.to_bytes(spec.meta, scales),
            "biases": S.to_bytes(spec.meta, biases),
        })
    return planes


def dense_bytes(data_key: str, name: str, dtype: str, count: int) -> bytes:
    rng = S.SplitMix64(seed("%s/dense/%s" % (data_key, name)))
    return S.to_bytes(dtype, [S.draw_float(rng, dtype, -4, 2, 0) for _ in range(count)])


# ------------------------------------------------------- checkpoint layouts ---
# Tensor data order inside each shard is deliberate: every stacked tensor except
# block.1.stack_c.scales starts at a NONZERO offset of its shard's data section
# (stack_c.scales starts exactly at the data section's first byte, the other
# boundary), companions of block.2.stack_q live in three different shards, and
# block.2.stack_q.biases is the LAST tensor of its shard (backing-window probe).
CK_A_MODULES = [
    ModuleSpec("block.0.stack_a", 4, 4, 64, 256),
    ModuleSpec("block.0.stack_b", 4, 4, 64, 256),
]
CK_A_SHARDS = {
    "model.safetensors": [
        ("dense", "block.0.norm.weight", "F32", [64]),
        ("stack", "block.0.stack_a.weight"), ("stack", "block.0.stack_a.scales"),
        ("stack", "block.0.stack_a.biases"),
        ("stack", "block.0.stack_b.biases"), ("stack", "block.0.stack_b.weight"),
        ("stack", "block.0.stack_b.scales"),
    ],
}
CK_B_MODULES = [
    ModuleSpec("block.1.stack_d", 8, 4, 64, 256),            # 8-bit by explicit override
    ModuleSpec("block.1.stack_c", 4, 2, 64, 512),            # 4-bit by default
    ModuleSpec("block.2.stack_q", 8, 3, 128, 128),           # 8-bit override, companions in 3 shards
    ModuleSpec("block.2.stack_r", 4, 3, 64, 128, tweak=tweak_meta_range_expert1),
    ModuleSpec("block.2.narrow", 4, 2, 32, 128),             # N = 32: inherited R-GEOMETRY
]
CK_B_SHARDS = {
    "model-00001-of-00003.safetensors": [
        ("dense", "block.1.norm.weight", "F32", [128]),
        ("stack", "block.1.stack_d.weight"), ("stack", "block.1.stack_d.biases"),
        ("stack", "block.1.stack_d.scales"), ("stack", "block.2.stack_q.scales"),
    ],
    "model-00002-of-00003.safetensors": [
        ("stack", "block.1.stack_c.scales"), ("stack", "block.1.stack_c.weight"),
        ("stack", "block.1.stack_c.biases"),
        ("stack", "block.2.stack_r.weight"), ("stack", "block.2.stack_r.scales"),
        ("stack", "block.2.stack_r.biases"),
        ("stack", "block.2.stack_q.biases"),
    ],
    "model-00003-of-00003.safetensors": [
        ("dense", "block.2.bias_vec", "BF16", [64]),
        ("stack", "block.2.stack_q.weight"),
        ("stack", "block.2.narrow.weight"), ("stack", "block.2.narrow.scales"),
        ("stack", "block.2.narrow.biases"),
    ],
}
QUANT_DEFAULT = {"bits": 4, "group_size": 64}
CK_B_OVERRIDES = {"block.1.stack_d": {"bits": 8, "group_size": 64},
                  "block.2.stack_q": {"bits": 8, "group_size": 64}}

CHECKPOINTS = {
    # id: (data_key, layout, modules, shards, overrides)
    "ck-a-single": ("ck-a", "single", CK_A_MODULES, CK_A_SHARDS, {}),
    # Byte-identical HEADER to ck-a-single (same names, dtypes, shapes, offsets),
    # different payload: the source-binding probe cannot be decided by the
    # catalog or its digest, only by a payload-inclusive source identity.
    "ck-a-sibling": ("ck-a-sibling", "single", CK_A_MODULES, CK_A_SHARDS, {}),
    "ck-b-sharded": ("ck-b", "indexed", CK_B_MODULES, CK_B_SHARDS, CK_B_OVERRIDES),
}


def config_document(overrides) -> dict:
    quantization = dict(QUANT_DEFAULT)
    for module, spec in overrides.items():
        quantization[module] = dict(spec)
    return {"model_type": "synthetic-composition", "quantization": quantization}


def write_shard(entries):
    """entries: [(name, dtype, shape, bytes)] in DATA order. Returns (blob, header_len,
    {name: (begin, end)} relative to the data section). The header JSON is written
    with sorted keys and compact separators and padded with spaces to a multiple
    of 8 bytes, so every data section starts 8-byte aligned."""
    header = {"__metadata__": {"format": "mlx"}}
    offsets = {}
    cursor = 0
    for name, dtype, shape, payload in entries:
        header[name] = {"dtype": dtype, "shape": list(shape), "data_offsets": [cursor, cursor + len(payload)]}
        offsets[name] = (cursor, cursor + len(payload))
        cursor += len(payload)
    text = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
    text += b" " * ((-len(text)) % 8)
    blob = struct.pack("<Q", len(text)) + text + b"".join(p for _, _, _, p in entries)
    return blob, len(text), offsets


def build_checkpoint(ck_id: str):
    data_key, layout, modules, shards, overrides = CHECKPOINTS[ck_id]
    by_name = {m.name: m for m in modules}
    planes = {m.name: generate_module(data_key, m) for m in modules}
    files = {}
    tensors = {}                  # tensor name -> dict(shard, dtype, shape, begin, end, abs_begin, abs_end)
    for shard, order in shards.items():
        entries = []
        for item in order:
            if item[0] == "dense":
                _, name, dtype, shape = item
                count = 1
                for d in shape:
                    count *= d
                entries.append((name, dtype, shape, dense_bytes(data_key, name, dtype, count)))
            else:
                name = item[1]
                module, comp = name.rsplit(".", 1)
                spec = by_name[module]
                dtype, shape = spec.shapes()[comp]
                payload = b"".join(p[comp] for p in planes[module])
                entries.append((name, dtype, shape, payload))
        blob, header_len, offsets = write_shard(entries)
        files[shard] = blob
        for name, dtype, shape, _ in entries:
            begin, end = offsets[name]
            tensors[name] = {"shard": shard, "dtype": dtype, "shape": list(shape),
                             "data_offsets": [begin, end],
                             "abs_begin": 8 + header_len + begin, "abs_end": 8 + header_len + end}
    placed = set(tensors)
    for m in modules:
        for comp in COMPONENTS:
            assert m.name + SUFFIX[comp] in placed, (ck_id, m.name, comp)
    extra = {}
    if layout == "indexed":
        weight_map = {name: t["shard"] for name, t in tensors.items()}
        total = sum(len(b) - 8 - struct.unpack("<Q", b[:8])[0] for b in files.values())
        extra["model.safetensors.index.json"] = canonical({"metadata": {"total_size": total},
                                                            "weight_map": weight_map})
    else:
        assert len(files) == 1
    extra["config.json"] = canonical(config_document(overrides))
    return {"id": ck_id, "layout": layout, "modules": by_name, "planes": planes, "shards": files,
            "tensors": tensors, "extra": extra, "overrides": overrides}


def source_identity(shards: dict) -> str:
    """sha256 of the `shasum -a 256` listing of the checkpoint's shard files in
    C-locale name order, i.e. inside the checkpoint directory:
    LC_ALL=C shasum -a 256 *.safetensors | shasum -a 256"""
    listing = "".join("%s  %s\n" % (sha256_hex(shards[n]), n) for n in sorted(shards))
    return sha256_hex(listing.encode())


# ------------------------------------- independent stdlib header re-parse ------
def parse_shard_header(blob: bytes):
    """A second, separate reading of a written shard: the 8-byte prefix, a header
    that begins with '{', and strictly tiling data offsets. Returns
    {name: (dtype, shape, abs_begin, abs_end)} and asserts the Safetensors rules
    the Slice 1 catalog enforces (so every fixture checkpoint is admissible)."""
    (n,) = struct.unpack("<Q", blob[:8])
    text = blob[8:8 + n]
    assert text[:1] == b"{", "header must begin with '{'"
    header = json.loads(text)
    data_len = len(blob) - 8 - n
    out = {}
    spans = []
    for name, entry in header.items():
        if name == "__metadata__":
            continue
        begin, end = entry["data_offsets"]
        count = 1
        for d in entry["shape"]:
            count *= d
        assert 0 <= begin <= end <= data_len and end - begin == count * WIDTH[entry["dtype"]], name
        out[name] = (entry["dtype"], list(entry["shape"]), 8 + n + begin, 8 + n + end)
        spans.append((begin, end))
    cursor = 0
    for begin, end in sorted(spans):
        assert begin == cursor, "gap or overlap"
        cursor = end
    assert cursor == data_len, "uncovered trailing bytes"
    return out


# ------------------------------------------------------------ the oracle ------
def oracle_selection(ck, module: str, index: int):
    """Expected (shard, absolute begin, length) of each component of plane `index`
    of `module`, from the SPECIFICATION: the tensor's placement recorded by the
    writer plus index * plane_bytes, where plane_bytes comes from the module's
    (N, K, bits, group, metadata dtype) -- never from production slicing."""
    spec = ck["modules"][module]
    assert 0 <= index < spec.E
    ranges = {}
    for comp in COMPONENTS:
        t = ck["tensors"][module + SUFFIX[comp]]
        length = spec.plane_bytes[comp]
        ranges[comp] = {"shard": t["shard"], "begin": t["abs_begin"] + index * length, "len": length}
    expected = {comp: ck["planes"][module][index][comp] for comp in COMPONENTS}
    return ranges, expected


def header_derived_selection(ck, module: str, index: int):
    """The same ranges re-derived from the independent header re-parse: begin +
    index * (byte_len / E). Used only to cross-check the oracle."""
    ranges = {}
    for comp in COMPONENTS:
        name = module + SUFFIX[comp]
        shard = ck["tensors"][name]["shard"]
        dtype, shape, a, b = parse_shard_header(ck["shards"][shard])[name]
        per = (b - a) // shape[0]
        assert per * shape[0] == b - a
        ranges[comp] = {"shard": shard, "begin": a + index * per, "len": per}
    return ranges


def slice_file(ck, rng) -> bytes:
    blob = ck["shards"][rng["shard"]]
    return blob[rng["begin"]:rng["begin"] + rng["len"]]


# --------------------------------------------------------- case assembly ------
def draw_x_values(key: str, count: int):
    return S.draw_x(S.SplitMix64(seed("x/" + key)), count)


def s2b_case(cid, spec, plane, x_shape, x_vals):
    """The selected plane (and its x) as a Slice 2B OP-QMM case, so the frozen
    Slice 2B classifier and family transcription apply to it unchanged."""
    c = S.Case(cid, "FX-QMM", "quantized_matmul")
    m_eff = 1
    for d in x_shape[:-1]:
        m_eff *= d
    c.add("x", "F32", tuple(x_shape), x_vals)
    c.add("w", "U32", (spec.N, spec.P), plane["words"])
    c.add("scales", spec.meta, (spec.N, spec.G), plane["scale_bits"])
    c.add("biases", spec.meta, (spec.N, spec.G), plane["bias_bits"])
    c.params = {"bits": spec.bits, "group_size": spec.group, "metadata_dtype": spec.meta,
                "x_shape": list(x_shape), "M_eff": m_eff, "K": spec.K,
                "N": spec.N, "transpose": True, "x_dtype": "F32"}
    return c


def standalone_blob(c):
    blob = bytearray()
    tensors = []
    for name, dtype, shape, vals in c.tensors:
        b = S.to_bytes(dtype, vals)
        tensors.append({"name": name, "dtype": dtype, "shape": list(shape), "offset": len(blob),
                        "nbytes": len(b), "sha256": sha256_hex(b)})
        blob += b
    return bytes(blob), tensors


def identity_of(ck_id, ck, module, index):
    spec = ck["modules"][module]
    resolved_from = "override" if module in ck["overrides"] else "default"
    return {"source_identity": source_identity(ck["shards"]), "checkpoint": ck_id, "module": module,
            "index_path": [index], "bits": spec.bits, "group_size": spec.group, "resolved_from": resolved_from,
            "metadata_dtype": spec.meta, "logical_shape": [spec.N, spec.K],
            "packed_shape": [spec.N, spec.P], "metadata_shape": [spec.N, spec.G], "transpose": True}


def resolution_consistent(spec: ModuleSpec, config_bits: int, config_group: int):
    """Independent restatement of the Slice 1 shape rule (C-SHAPE): packed*32 ==
    groups*group*bits. Returns (consistent, implied_bits)."""
    consistent = spec.P * 32 == spec.G * config_group * config_bits
    implied = None
    denom = spec.G * config_group
    if not consistent and denom and (spec.P * 32) % denom == 0:
        implied = spec.P * 32 // denom
    return consistent, implied


def composition_guards(sit):
    """Evaluate EVERY composition guard independently (True violated, False
    satisfied, "n/a: ..." when its precondition does not hold)."""
    G = {}
    if sit["entry"] == "E-RANGE":
        for rid in COMPOSITION_REFUSAL_ORDER[:5]:
            G[rid] = "n/a: range-resolution probe"
        begin, length = sit["range"]["begin"], sit["range"]["len"]
        G["C-R-OVERFLOW"] = begin + length > U64_MAX
        G["C-R-BACKING"] = ("n/a: end undefined" if G["C-R-OVERFLOW"]
                            else begin + length > sit["range"]["window"])
        return G
    G["C-R-RESOLVE"] = not sit["resolve_consistent"]
    if G["C-R-RESOLVE"]:
        for rid in COMPOSITION_REFUSAL_ORDER[1:]:
            G[rid] = "n/a: module unresolved"
        return G
    G["C-R-SOURCE-BINDING"] = sit["backing_source"] != sit["triple_source"]
    G["C-R-MODULE-BINDING"] = any(sit["triple_names"][c] != sit["module"] + SUFFIX[c] for c in COMPONENTS)
    rank_ok = len(sit["index_path"]) == len(sit["leading"])
    G["C-R-INDEX-RANK"] = not rank_ok
    if not rank_ok:
        G["C-R-INDEX-RANGE"] = "n/a: index rank"
    else:
        G["C-R-INDEX-RANGE"] = any(i >= e for i, e in zip(sit["index_path"], sit["leading"]))
    if G["C-R-INDEX-RANGE"] is not False:
        G["C-R-OVERFLOW"] = G["C-R-BACKING"] = "n/a: index not admitted"
        return G
    ends = []
    overflow = False
    for c in COMPONENTS:
        r = sit["ranges"][c]
        if r["begin"] > U64_MAX or r["begin"] + r["len"] > U64_MAX:
            overflow = True
        ends.append((r["shard"], r["begin"] + r["len"]))
    G["C-R-OVERFLOW"] = overflow
    G["C-R-BACKING"] = "n/a: end undefined" if overflow else any(end > sit["windows"][shard] for shard, end in ends)
    return G


def violated(G, order):
    return [rid for rid in order if G.get(rid) is True]


def not_evaluable(G):
    return sorted(rid for rid, v in G.items() if isinstance(v, str))


# ------------------------------------------------------------- population -----
def population():
    cks = {ck_id: build_checkpoint(ck_id) for ck_id in CHECKPOINTS}
    # --- oracle self-consistency, every run including --check -------------------
    for ck in cks.values():
        for shard, blob in ck["shards"].items():
            parsed = parse_shard_header(blob)
            for name, (dtype, shape, a, b) in parsed.items():
                t = ck["tensors"][name]
                assert (t["dtype"], t["shape"], t["abs_begin"], t["abs_end"], t["shard"]) == (dtype, shape, a, b, shard)
        for module, spec in ck["modules"].items():
            for e in range(spec.E):
                ranges, expected = oracle_selection(ck, module, e)
                assert ranges == header_derived_selection(ck, module, e), (ck["id"], module, e)
                for comp in COMPONENTS:
                    assert slice_file(ck, ranges[comp]) == expected[comp], (ck["id"], module, e, comp)
            # Distinguishability: every component differs between every two experts.
            for comp in COMPONENTS:
                seen = [ck["planes"][module][e][comp] for e in range(spec.E)]
                assert len(set(seen)) == spec.E, (ck["id"], module, comp)
    # Same header, different payload.
    a, s = cks["ck-a-single"], cks["ck-a-sibling"]
    for shard in a["shards"]:
        na = struct.unpack("<Q", a["shards"][shard][:8])[0]
        assert a["shards"][shard][:8 + na] == s["shards"][shard][:8 + na]
        assert a["shards"][shard] != s["shards"][shard]
    assert source_identity(a["shards"]) != source_identity(s["shards"])

    cases = []

    def windows_full(ck):
        return {n: len(b) for n, b in ck["shards"].items()}

    def base_situation(ck_id, module, index_path, entry="E-COMPOSE"):
        ck = cks[ck_id]
        spec = ck["modules"][module]
        ranges = None
        if len(index_path) == 1 and index_path[0] < spec.E:
            ranges, _ = oracle_selection(ck, module, index_path[0])
        return {"entry": entry, "module": module, "index_path": list(index_path), "leading": [spec.E],
                "resolve_consistent": True, "backing_source": source_identity(ck["shards"]),
                "triple_source": source_identity(ck["shards"]),
                "triple_names": {c: module + SUFFIX[c] for c in COMPONENTS},
                "ranges": ranges, "windows": windows_full(ck)}

    def composition_block(ck_id, module, index_path, entry="E-COMPOSE", **more):
        ck = cks[ck_id]
        block = {"entry": entry, "checkpoint": "checkpoints/" + ck_id, "config": "checkpoints/%s/config.json" % ck_id,
                 "module": module, "index_path": list(index_path),
                 "backing": {"checkpoint": "checkpoints/" + ck_id, "windows": {}}}
        block.update(more)
        return block

    def accepted(cid, family, ck_id, module, index, m, x_key, note, sequence=None):
        ck = cks[ck_id]
        spec = ck["modules"][module]
        plane = ck["planes"][module][index]
        x_shape = [m, spec.K]
        x_vals = draw_x_values(x_key, m * spec.K)
        c = s2b_case(cid, spec, plane, x_shape, x_vals)
        G = S.guard_results(c)
        assert S.violations(G) == [] and S.not_evaluable(G) == [], (cid, S.violations(G), S.not_evaluable(G))
        sit = base_situation(ck_id, module, [index])
        CG = composition_guards(sit)
        assert violated(CG, COMPOSITION_REFUSAL_ORDER) == [] and not_evaluable(CG) == [], (cid, CG)
        ranges, expected = oracle_selection(ck, module, index)
        blob, tensors = standalone_blob(c)
        p = c.params
        macs = p["M_eff"] * p["N"] * p["K"]
        refs = ["rust_binary64_r1"] + (["python_exact_r1"] if macs <= PY_EXACT_MAC_LIMIT else [])
        checks = ["S-IDENTITY", "S-RANGES", "S-BYTES", "S-STAGED-EQUAL", "S-SOURCE-UNCHANGED", "N-COMP-ARRAYS",
                  "N-QMM-SHAPE-DTYPE(A)", "N-QMM-SHAPE-DTYPE(B)", "N-COMP-AB",
                  "G-QMM-EXACT(A)", "G-QMM-RUST(A)", "G-QMM-EXACT(B)", "G-QMM-RUST(B)", "G-R1-SELF-QMM(C)"]
        if sequence and sequence.get("same_output_as"):
            checks.append("N-COMP-ABA")
        entry = {
            "id": cid, "family": family, "op": "quantized_matmul", "params": p,
            "expected": {
                "outcome": "accept", "checks": checks,
                "families_0_31_2": S.families(p),
                "architecture_dependent": 6 <= p["M_eff"] <= 31,
                "array_census": [
                    {"role": "x", "op": "import", "dtype": "F32", "shape": x_shape},
                    {"role": "w", "op": "import", "dtype": "U32", "shape": [spec.N, spec.P]},
                    {"role": "scales", "op": "import", "dtype": spec.meta, "shape": [spec.N, spec.G]},
                    {"role": "biases", "op": "import", "dtype": spec.meta, "shape": [spec.N, spec.G]},
                    {"role": "scales_f32", "op": "astype", "dtype": "F32", "shape": [spec.N, spec.G]},
                    {"role": "biases_f32", "op": "astype", "dtype": "F32", "shape": [spec.N, spec.G]},
                    {"role": "out", "op": "quantized_matmul", "dtype": "F32", "shape": [m, spec.N]},
                ],
                "output_nbytes": m * spec.N * 4,
            },
            "references": refs,
            "composition": composition_block(ck_id, module, [index], x_from="standalone:x", **(
                {"sequence": sequence} if sequence else {})),
            "oracle": {"identity": identity_of(ck_id, ck, module, index), "ranges": ranges,
                       "sha256": {comp: sha256_hex(expected[comp]) for comp in COMPONENTS},
                       "composition_guards": CG},
            "note": note,
            "file": "standalone/%s.bin" % cid, "file_sha256": sha256_hex(blob), "tensors": tensors,
        }
        # the standalone plane bytes ARE the oracle's expected bytes
        assert [t["sha256"] for t in tensors[1:]] == [sha256_hex(expected[c_]) for c_ in COMPONENTS]
        cases.append((entry, blob))
        return entry

    # ---- accepted compositions (A, B, C) ---------------------------------------
    accepted("acc-a-stack_a-e0-m1", "FX-COMP-ACCEPT", "ck-a-single", "block.0.stack_a", 0, 1, "acc-a-e0",
             "first expert; vector x; default 4-bit; single shard; tensor at a nonzero data offset")
    accepted("acc-a-stack_a-e3-m32", "FX-COMP-ACCEPT", "ck-a-single", "block.0.stack_a", 3, 32, "acc-a-e3",
             "last expert; matrix x (M_eff 32: matrix family on every architecture)")
    accepted("acc-a-stack_b-e1-m32", "FX-COMP-ACCEPT", "ck-a-single", "block.0.stack_b", 1, 32, "acc-b-e1",
             "middle expert of a second module with identical geometry and a different placement")
    accepted("acc-a-stack_b-e2-m1", "FX-COMP-ACCEPT", "ck-a-single", "block.0.stack_b", 2, 1, "acc-b-e2",
             "middle expert; vector x")
    accepted("acc-b-stack_d-e0-m32", "FX-COMP-ACCEPT", "ck-b-sharded", "block.1.stack_d", 0, 32, "acc-d-e0",
             "8-bit resolved by explicit per-module override over a 4-bit default; first expert; matrix x")
    accepted("acc-b-stack_d-e3-m1", "FX-COMP-ACCEPT", "ck-b-sharded", "block.1.stack_d", 3, 1, "acc-d-e3",
             "8-bit override; last expert; vector x")
    accepted("acc-b-stack_c-e1-m1", "FX-COMP-ACCEPT", "ck-b-sharded", "block.1.stack_c", 1, 1, "acc-c-e1",
             "4-bit by default inside the mixed checkpoint; last of two experts; K 512 (qmv_fast)")
    accepted("acc-b-stack_c-e0-m32", "FX-COMP-ACCEPT", "ck-b-sharded", "block.1.stack_c", 0, 32, "acc-c-e0",
             "first expert whose scales range starts at the first byte of its shard's data section")
    accepted("acc-b-stack_q-e1-m32", "FX-COMP-ACCEPT", "ck-b-sharded", "block.2.stack_q", 1, 32, "acc-q-e1",
             "8-bit override; weight, scales and biases in three different shards; middle expert; N 128")
    accepted("acc-b-stack_q-e2-m1", "FX-COMP-ACCEPT", "ck-b-sharded", "block.2.stack_q", 2, 1, "acc-q-e2",
             "last expert, companions in three shards; K 128 (qmv_quad); biases end at their shard's end")
    accepted("acc-b-stack_r-e2-m1", "FX-COMP-ACCEPT", "ck-b-sharded", "block.2.stack_r", 2, 1, "acc-r-e2",
             "admitted expert of the module whose expert 1 is refused (inh-meta-range-e1): refusal is per plane")
    # ---- repeated A-B-A selection in one child ---------------------------------
    accepted("seq-aba-0", "FX-COMP-SEQUENCE", "ck-b-sharded", "block.1.stack_d", 1, 32, "seq-aba-a",
             "A-B-A step 0: 8-bit override module, expert 1",
             sequence={"group": "aba", "position": 0, "same_output_as": None})
    accepted("seq-aba-1", "FX-COMP-SEQUENCE", "ck-b-sharded", "block.1.stack_c", 0, 32, "seq-aba-b",
             "A-B-A step 1: a different module at a different bit width (4-bit default) in the same child",
             sequence={"group": "aba", "position": 1, "same_output_as": None})
    accepted("seq-aba-2", "FX-COMP-SEQUENCE", "ck-b-sharded", "block.1.stack_d", 1, 32, "seq-aba-a",
             "A-B-A step 2: the step-0 selection and x again; A output must equal step 0's bit for bit",
             sequence={"group": "aba", "position": 2, "same_output_as": "seq-aba-0"})

    # ---- composition refusals, before any native call --------------------------
    def refusal(cid, ck_id, module, index_path, rid, note, entry="E-COMPOSE", sit_patch=None, block_more=None):
        sit = base_situation(ck_id, module, index_path, entry)
        if sit_patch:
            sit_patch(sit)
        CG = composition_guards(sit)
        v = violated(CG, COMPOSITION_REFUSAL_ORDER)
        assert v == [rid], (cid, v, rid)
        block = composition_block(ck_id, module, index_path, entry=entry, **(block_more or {}))
        cases.append(({"id": cid, "family": "FX-COMP-REFUSE", "op": "quantized_matmul", "params": {},
                       "expected": {"outcome": "refuse", "refusal_id": rid, "stage": "composition",
                                    "violated_guards": v, "not_evaluable_guards": not_evaluable(CG),
                                    "native_calls_in_case": {"numerical": 0, "imports": 0}},
                       "references": [], "composition": block,
                       "oracle": {"composition_guards": CG}, "note": note}, None))

    refusal("ref-index-range", "ck-a-single", "block.0.stack_a", [4], "C-R-INDEX-RANGE",
            "expert index E (4 of 4 experts): one past the last expert")
    refusal("ref-index-range-u64max", "ck-a-single", "block.0.stack_a", [U64_MAX], "C-R-INDEX-RANGE",
            "expert index 2^64-1: must be refused as out of range, never wrapped or narrowed")
    refusal("ref-index-rank-empty", "ck-a-single", "block.0.stack_a", [], "C-R-INDEX-RANK",
            "empty index path for a tensor with one leading dimension")
    refusal("ref-index-rank-two", "ck-a-single", "block.0.stack_a", [0, 0], "C-R-INDEX-RANK",
            "two indices for a tensor with one leading dimension")

    ck_a = cks["ck-a-single"]
    shard_a = "model.safetensors"
    probe = {"shard": shard_a, "begin": U64_MAX - 7, "len": 16, "window": len(ck_a["shards"][shard_a])}

    def patch_range(sit):
        sit["range"] = dict(probe)
    refusal("ref-range-overflow", "ck-a-single", "block.0.stack_a", [0], "C-R-OVERFLOW",
            "range-resolution probe: begin 2^64-8, len 16 over a valid backing; begin + len overflows u64. "
            "Unreachable through an admitted catalog and a validated triple (catalog rules 10-12, Slice 1 C-SLICE); "
            "this probes the composition layer's own checked range arithmetic directly",
            entry="E-RANGE", sit_patch=patch_range,
            block_more={"range_probe": {"shard": shard_a, "begin": U64_MAX - 7, "len": 16}})

    ck_b = cks["ck-b-sharded"]
    shard_q_biases = ck_b["tensors"]["block.2.stack_q.biases"]["shard"]
    last_shard_len = len(ck_b["shards"][shard_q_biases])
    assert ck_b["tensors"]["block.2.stack_q.biases"]["abs_end"] == last_shard_len

    def patch_window(sit):
        sit["windows"][shard_q_biases] = last_shard_len - 1
    refusal("ref-backing-window-short", "ck-b-sharded", "block.2.stack_q", [2], "C-R-BACKING",
            "the backing for the biases' shard is a window one byte shorter than the shard; the selected "
            "biases plane ends at the shard's last byte (a valid file, an insufficient backing)",
            sit_patch=patch_window,
            block_more={"backing": {"checkpoint": "checkpoints/ck-b-sharded",
                                    "windows": {shard_q_biases: last_shard_len - 1}}})

    def patch_sibling(sit):
        sit["backing_source"] = source_identity(cks["ck-a-sibling"]["shards"])
    refusal("ref-source-sibling", "ck-a-single", "block.0.stack_a", [1], "C-R-SOURCE-BINDING",
            "triple resolved from ck-a-single, backing loaded from ck-a-sibling: identical headers and catalog, "
            "different payload; only the payload-inclusive source identity distinguishes them",
            entry="E-SELECT", sit_patch=patch_sibling,
            block_more={"backing": {"checkpoint": "checkpoints/ck-a-sibling", "windows": {}}})

    def patch_mixed(sit):
        sit["triple_names"] = {"weight": "block.0.stack_a.weight", "scales": "block.0.stack_b.scales",
                               "biases": "block.0.stack_b.biases"}
    refusal("ref-module-mixed", "ck-a-single", "block.0.stack_a", [1], "C-R-MODULE-BINDING",
            "a triple built through the public AffineTriple::new for module block.0.stack_a from stack_a's "
            "weight and stack_b's scales and biases (identical shapes, so Slice 1 admits it)",
            entry="E-SELECT", sit_patch=patch_mixed,
            block_more={"triple_components": {"weight": "block.0.stack_a.weight",
                                              "scales": "block.0.stack_b.scales",
                                              "biases": "block.0.stack_b.biases"},
                        "triple_spec": {"bits": 4, "group_size": 64}})

    # ---- inherited Slice 2B refusals on the selected plane ---------------------
    def inherited(cid, ck_id, module, index, rid, note, x_shape_override=None):
        ck = cks[ck_id]
        spec = ck["modules"][module]
        plane = ck["planes"][module][index]
        x_shape = x_shape_override or [1, spec.K]
        count = 1
        for d in x_shape:
            count *= d
        x_vals = draw_x_values(cid, count)
        c = s2b_case(cid, spec, plane, x_shape, x_vals)
        G = S.guard_results(c)
        v = S.violations(G)
        assert v == [rid], (cid, v, rid)
        sit = base_situation(ck_id, module, [index])
        CG = composition_guards(sit)
        assert violated(CG, COMPOSITION_REFUSAL_ORDER) == [], (cid, CG)
        ranges, expected = oracle_selection(ck, module, index)
        blob, tensors = standalone_blob(c)
        cases.append(({"id": cid, "family": "FX-COMP-INHERITED-REFUSE", "op": "quantized_matmul", "params": c.params,
                       "expected": {"outcome": "refuse", "refusal_id": rid, "stage": "bridge",
                                    "b_refusal_id": rid, "violated_guards": v,
                                    "not_evaluable_guards": S.not_evaluable(G),
                                    "checks": ["S-IDENTITY", "S-RANGES", "S-BYTES", "S-STAGED-EQUAL",
                                               "S-SOURCE-UNCHANGED"],
                                    "native_numerical_before_decision": 0, "native_imports_before_decision": 0},
                       "references": [],
                       "composition": composition_block(ck_id, module, [index], x_from="standalone:x"),
                       "oracle": {"identity": identity_of(ck_id, ck, module, index), "ranges": ranges,
                                  "sha256": {comp: sha256_hex(expected[comp]) for comp in COMPONENTS},
                                  "composition_guards": CG},
                       "note": note, "file": "standalone/%s.bin" % cid, "file_sha256": sha256_hex(blob),
                       "tensors": tensors}, blob))

    inherited("inh-geometry-narrow", "ck-b-sharded", "block.2.narrow", 0, "R-GEOMETRY",
              "the selected plane has N = 32 (N % 64 != 0): Slice 2B D-GEOM refuses it after a correct selection")
    inherited("inh-meta-range-e1", "ck-b-sharded", "block.2.stack_r", 1, "R-DOMAIN-META-RANGE",
              "expert 1 carries one normal bfloat16 scale 2^-33 < 2^-32; experts 0 and 2 are admitted")
    inherited("inh-xshape", "ck-a-single", "block.0.stack_a", 1, "R-XSHAPE",
              "x last dimension 128 against the plane's logical K = 256 (derived from the resolved spec, "
              "not from the packed width)", x_shape_override=[1, 128])

    # ---- mutation controls ------------------------------------------------------
    by_id = {e["id"]: e for e, _ in cases}

    def mutation(cid, baseline, kind, detected_by, note, mutate):
        base = by_id[baseline]
        comp = base["composition"]
        ck = cks[comp["checkpoint"].split("/", 1)[1]]
        module = comp["module"]
        index = comp["index_path"][0]
        exp_ranges = base["oracle"]["ranges"]
        spec = ck["modules"][module]
        mut = mutate(ck, spec, module, index, exp_ranges)
        record = {"kind": kind}
        if "ranges" in mut:
            mranges = mut["ranges"]
            record["ranges"] = mranges
            record["sha256"] = {c_: sha256_hex(slice_file(ck, mranges[c_])) for c_ in COMPONENTS}
            for c_ in COMPONENTS:
                changed = mranges[c_] != exp_ranges[c_]
                assert changed == (("S-RANGES:" + c_) in detected_by), (cid, c_)
                assert (record["sha256"][c_] != base["oracle"]["sha256"][c_]) == changed, (cid, c_)
                assert changed == (("S-BYTES:" + c_) in detected_by), (cid, c_)
                # the mutated range still lies inside its tensor, so only an
                # independent comparison can detect it
                t = ck["tensors"][module + SUFFIX[c_]]
                assert t["abs_begin"] <= mranges[c_]["begin"] and \
                    mranges[c_]["begin"] + mranges[c_]["len"] <= t["abs_end"], (cid, c_)
        if "identity" in mut:
            record["identity"] = mut["identity"]
            assert mut["identity"] != base["oracle"]["identity"]
        if "config" in mut:
            record["config"] = mut["config"]
            consistent, implied = resolution_consistent(spec, mut["config_bits"], mut["config_group"])
            assert not consistent and implied == spec.bits, (cid, implied)
            record["slice1_refusal"] = {"variant": "InconsistentOverride", "implied_bits": implied}
        cases.append(({"id": cid, "family": "FX-COMP-MUTATION", "op": "quantized_matmul", "params": {},
                       "expected": {"outcome": "detected", "detected_by": detected_by,
                                    "native_calls_in_case": {"numerical": 0, "imports": 0}},
                       "references": [],
                       "composition": dict(comp, baseline_case=baseline, mutation=record),
                       "oracle": {"baseline_ranges": exp_ranges, "baseline_sha256": base["oracle"]["sha256"],
                                  "baseline_identity": base["oracle"]["identity"]},
                       "note": note}, None))

    def wrong_index(ck, spec, module, index, exp):
        other = (index + 1) % spec.E
        r, _ = oracle_selection(ck, module, other)
        return {"ranges": r}

    def wrong_stride(ck, spec, module, index, exp):
        r = json.loads(json.dumps(exp))
        t = ck["tensors"][module + ".weight"]
        stride = spec.plane_bytes["weight"] + 4
        r["weight"] = {"shard": t["shard"], "begin": t["abs_begin"] + index * stride, "len": spec.plane_bytes["weight"]}
        return {"ranges": r}

    def swap(component, other_index):
        def f(ck, spec, module, index, exp):
            r = json.loads(json.dumps(exp))
            o, _ = oracle_selection(ck, module, other_index)
            r[component] = o[component]
            return {"ranges": r}
        return f

    def override_ignored_resolve(ck, spec, module, index, exp):
        return {"config": "mutations/ck-b-sharded-config-without-stack_d-override.json",
                "config_bits": QUANT_DEFAULT["bits"], "config_group": QUANT_DEFAULT["group_size"]}

    def override_ignored_plane(ck, spec, module, index, exp):
        ident = dict(by_id["acc-b-stack_d-e3-m1"]["oracle"]["identity"])
        ident["bits"] = QUANT_DEFAULT["bits"]
        ident["resolved_from"] = "default"
        return {"identity": ident}

    mutation("mut-wrong-index", "acc-a-stack_b-e1-m32", "wrong_expert_index",
             ["S-RANGES:weight", "S-RANGES:scales", "S-RANGES:biases",
              "S-BYTES:weight", "S-BYTES:scales", "S-BYTES:biases"],
             "selection arithmetic uses expert 2 while the plane identity records expert 1", wrong_index)
    mutation("mut-wrong-stride", "acc-a-stack_b-e2-m1", "wrong_plane_stride",
             ["S-RANGES:weight", "S-BYTES:weight"],
             "weight plane stride one u32 word too large (expert 2 of 4, so the range stays inside the tensor); "
             "a stride error is invisible on expert 0 by construction", wrong_stride)
    mutation("mut-swap-scales", "acc-a-stack_a-e3-m32", "scales_from_other_expert",
             ["S-RANGES:scales", "S-BYTES:scales"],
             "weight and biases of expert 3, scales of expert 2", swap("scales", 2))
    mutation("mut-swap-biases", "acc-b-stack_q-e1-m32", "biases_from_other_expert",
             ["S-RANGES:biases", "S-BYTES:biases"],
             "weight and scales of expert 1, biases of expert 0 (companions in three shards)", swap("biases", 0))
    mutation("mut-override-ignored-resolve", "acc-b-stack_d-e0-m32", "override_ignored_at_resolution",
             ["C-R-RESOLVE"],
             "the 8-bit override is dropped from the configuration; Slice 1 resolution refuses "
             "(InconsistentOverride, implied bits 8) before any selection", override_ignored_resolve)
    mutation("mut-override-ignored-plane", "acc-b-stack_d-e3-m1", "override_ignored_in_plane",
             ["S-IDENTITY:bits"],
             "the plane records the 4-bit default instead of the resolved 8-bit override; ranges and bytes are "
             "unchanged, so only the identity comparison detects it (the bridge's R-META would refuse later)",
             override_ignored_plane)
    return cks, cases


# ----------------------------------------------------------------- output -----
def listing_sha256(files: dict) -> str:
    """sha256 of the `shasum -a 256` listing of every fixture file except the
    manifest, in C-locale path order; inside fixtures/native-composition:
    find checkpoints mutations standalone -type f | LC_ALL=C sort | xargs shasum -a 256 | shasum -a 256"""
    names = sorted((n for n in files if n != "manifest.json"), key=lambda n: n.encode())
    return sha256_hex("".join("%s  %s\n" % (sha256_hex(files[n]), n) for n in names).encode())


def build_files():
    gen_bytes = Path(__file__).read_bytes()
    cks, cases = population()
    files = {}
    ck_manifest = {}
    for ck_id, ck in cks.items():
        base = "checkpoints/%s/" % ck_id
        entries = {}
        for name, blob in list(ck["shards"].items()) + list(ck["extra"].items()):
            files[base + name] = blob
            entries[name] = {"sha256": sha256_hex(blob), "bytes": len(blob)}
        modules = {}
        for name, spec in ck["modules"].items():
            modules[name] = {
                "bits": spec.bits, "group_size": spec.group, "metadata_dtype": spec.meta,
                "resolved_from": "override" if name in ck["overrides"] else "default",
                "experts": spec.E, "N": spec.N, "K": spec.K, "packed_cols": spec.P, "groups": spec.G,
                "plane_bytes": spec.plane_bytes,
                "tensors": {c: ck["tensors"][name + SUFFIX[c]] for c in COMPONENTS},
                "expert_sha256": [{c: sha256_hex(p[c]) for c in COMPONENTS} for p in ck["planes"][name]],
            }
        ck_manifest[ck_id] = {"dir": "checkpoints/" + ck_id, "layout": ck["layout"], "files": entries,
                              "source_identity": source_identity(ck["shards"]),
                              "source_identity_method": "inside the checkpoint directory: "
                                                        "LC_ALL=C shasum -a 256 *.safetensors | shasum -a 256",
                              "config": "checkpoints/%s/config.json" % ck_id, "modules": modules}
    files["mutations/ck-b-sharded-config-without-stack_d-override.json"] = canonical(
        config_document({k: v for k, v in CK_B_OVERRIDES.items() if k != "block.1.stack_d"}))
    ids = [e["id"] for e, _ in cases]
    assert len(ids) == len(set(ids)), "duplicate case id"
    for entry, blob in cases:
        if blob is not None:
            files[entry["file"]] = blob
    # Model neutrality of every name and every text file.
    for name, blob in files.items():
        if name.endswith(".json"):
            low = blob.lower()
            for token in FORBIDDEN_NAME_TOKENS:
                assert token.encode() not in low, (name, token)
    counts = {}
    for entry, _ in cases:
        counts[entry["family"]] = counts.get(entry["family"], 0) + 1
    manifest = {
        "schema": SCHEMA,
        "contract_schema": CONTRACT_SCHEMA,
        "generator": GENERATOR_PATH,
        "generator_sha256": sha256_hex(gen_bytes),
        "inherits": {"slice2b_contract_sha256": S2B_CONTRACT_SHA256,
                     "slice2b_generator": S2B_GENERATOR_PATH, "slice2b_generator_sha256": S2B_GENERATOR_SHA256},
        "encoding": ("standalone/<id>.bin uses the Slice 2B case encoding: the concatenation of the tensors x, w, "
                     "scales, biases (little-endian; U32/F32 4-byte words, BF16 2-byte words) at the recorded "
                     "offsets; w/scales/biases are the ORACLE's expected plane bytes, never sliced from a shard"),
        "composition_refusal_order": COMPOSITION_REFUSAL_ORDER,
        "selection_checks": SELECTION_CHECKS,
        "files_listing_sha256": listing_sha256(files),
        "files_listing_method": ("inside fixtures/native-composition: find checkpoints mutations standalone -type f "
                                 "| LC_ALL=C sort | xargs shasum -a 256 | shasum -a 256"),
        "checkpoints": ck_manifest,
        "case_count": len(cases),
        "case_count_by_family": dict(sorted(counts.items())),
        "cases": [entry for entry, _ in cases],
    }
    files["manifest.json"] = (json.dumps(manifest, indent=1, sort_keys=False) + "\n").encode()
    return files


def build(out_dir: Path, check: bool) -> int:
    files = build_files()
    if check:
        bad = 0
        for rel, data in sorted(files.items()):
            p = out_dir / rel
            if not p.is_file() or p.read_bytes() != data:
                print("MISMATCH", rel)
                bad += 1
        present = {p.relative_to(out_dir).as_posix() for p in out_dir.rglob("*") if p.is_file()}
        extra = sorted(present - set(files))
        for rel in extra:
            print("UNEXPECTED", rel)
        if bad or extra:
            return 1
        print("check OK: %d files" % len(files))
        return 0
    for rel, data in files.items():
        p = out_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    print("wrote %d files, %d bytes" % (len(files), sum(len(d) for d in files.values())))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    return build(a.out, a.check)


if __name__ == "__main__":
    sys.exit(main())
