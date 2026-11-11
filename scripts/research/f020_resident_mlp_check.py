"""Resident-only numerical and retirement admission. All references start at original input."""

import hashlib
import json
import struct
import platform
import sys
from pathlib import Path
import f020_expert_mlp_qualify_v1 as donor
import f020_expert_mlp_r1_v1 as r1
import f020_resident_mlp_fixtures as fixtures
from f020_resident_mlp_fixtures import require, sha

ORDER = (0, 1, 0, 2, 1, 0, 0, 1, 0)
ARMS = tuple((p, a) for p in ("default", "mixed") for a in ("allocating", "cached"))
SLOTS = ((0, 1), (1, 1), (0, 1), (0, 2), (1, 1), (0, 3), (0, 3), (1, 1), (0, 3))
VIEW_SHA = "23bad0b4c40086dfec75eda1273a7af999c3cca98027f17aed0d4a61690507d8"
NATIVE = 32 << 20
ROLES = ("gate", "up", "down")


def binding(recipe, expert):
    """Reconstruct the sealed reader's serialized plan from original fixture authority."""
    root = fixtures.VIEW / recipe["name"]
    header = (root / "model.safetensors").read_bytes()[:8]
    metadata = (
        sum(
            (root / n).stat().st_size
            for n in ("config.json", "model.safetensors.index.json")
        )
        + 8
        + int.from_bytes(header, "little")
    )
    planes = []
    require(len(recipe["planes"][expert]) == len(ROLES), "role count")
    for role, p in zip(ROLES, recipe["planes"][expert]):
        ranges = [
            {k: x[k] for k in ("tensor", "shard", "begin", "len")} for x in p["ranges"]
        ]
        planes.append(
            dict(
                role=role,
                module=p["module"],
                expert=expert,
                bits=p["bits"],
                group_size=64,
                resolved_from="override" if p["bits"] == 8 else "default",
                metadata_dtype="BF16",
                logical_shape=p["logical_shape"],
                ranges=ranges,
            )
        )
    request = dict(
        modules=[p["module"] for p in planes],
        expert=expert,
        experts=3,
        d=128,
        h=64,
        bits=[p["bits"] for p in planes],
        group_size=64,
    )
    size = sum(x["len"] for p in planes for x in p["ranges"])
    plan = dict(
        schema="pulsarmlx.bounded-expert-plan/1",
        checkpoint=recipe["name"],
        metadata_snapshot_sha256=recipe["metadata"],
        metadata_bytes_read=metadata,
        request=request,
        planes=planes,
        selected_bytes=size,
        identity_scope="metadata snapshot and selected ranges only; no whole-checkpoint payload identity",
    )
    digest = hashlib.sha256(
        b"pulsarmlx.copied-residency/1" + bytes(4) + bytes.fromhex(recipe["content"])
    )
    for p in recipe["planes"][expert]:
        for h in p["sha256"]:
            digest.update(bytes.fromhex(h))
    digest.update(json.dumps(plan, separators=(",", ":")).encode())
    return digest.hexdigest(), size


class Reference:
    def __init__(self):
        self.recipes = fixtures.prepare()["recipes"]
        require(
            sha((fixtures.VIEW / "manifest.json").read_bytes()) == VIEW_SHA,
            "indexed manifest",
        )
        original = json.loads((fixtures.ORIGINAL / "manifest.json").read_bytes())
        self.cases = {}
        for profile in self.recipes:
            for expert in range(3):
                ident = f"mlp-d128-h64-m1-e{expert}-{profile}"
                case = next(x for x in original["cases"] if x["id"] == ident)
                self.cases[profile, expert] = donor.refs(original, case)


def memory(values):
    require(
        isinstance(values, list)
        and len(values) == 3
        and all(type(n) is int and 0 <= n <= NATIVE for n in values),
        "allocator telemetry",
    )


def row_check(row, profile, arm, index, reference):
    require(
        set(row)
        == set(
            "ordinal step expert recipe slot_generation binding component_sha256_before component_sha256_after staging_capacity copies cleanup gate up activation down down_admission".split()
        ),
        "closed occurrence schema",
    )
    expert = ORDER[index]
    recipe = reference.recipes[profile]
    plan = recipe["planes"][expert]
    expected, size = binding(recipe, expert)
    hashes = [p["sha256"] for p in plan]
    require(
        (row["ordinal"], row["step"], row["expert"], row["recipe"])
        == (index, int(index >= 6), expert, profile),
        "occurrence identity",
    )
    require(
        "error" not in row
        and row["binding"] == expected
        and row["component_sha256_before"] == row["component_sha256_after"] == hashes,
        "selected tuple",
    )
    require(
        row["slot_generation"] == (list(SLOTS[index]) if arm == "cached" else None),
        "slot/generation",
    )
    require(
        size <= row["staging_capacity"] <= 65536
        and row["copies"]
        == dict(
            staging_components=9,
            staging_bytes=size,
            qmm_data_imports=12,
            qmm_metadata_widenings=6,
            projection_readbacks=3,
            activation_input_imports=2,
            scalar_imports=2,
            activation_readbacks=3,
            down_host_reimport=1,
        ),
        "copy ledger",
    )
    cleanup = row["cleanup"]
    require(
        all(cleanup[k] == 0 for k in ("live", "double_free", "errors", "messages"))
        and cleanup["freed"] > 0
        and cleanup["results"][0] == cleanup["results"][1] > 0
        and cleanup["results"][2] == 0,
        "ownership retirement",
    )
    for i, role in enumerate(ROLES):
        stage = row[role]
        require(
            set(stage)
            == set(
                "bits group_size packed_weight_sha256 output bound_gamma_n device_facts_gpu cpu_guard_checks imports_before_decision numerical_before_decision imports numerical active_cache_peak".split()
            ),
            "closed projection budget",
        )
        n, k = plan[i]["logical_shape"]
        require(
            stage["bits"] == plan[i]["bits"]
            and stage["group_size"] == 64
            and stage["packed_weight_sha256"] == hashes[i][0]
            and stage["bound_gamma_n"] == r1.gamma_n(1, n, k),
            "stage recipe/gamma",
        )
        require(
            stage["device_facts_gpu"] is True
            and stage["cpu_guard_checks"] == 2
            and stage["imports_before_decision"]
            == stage["numerical_before_decision"]
            == 0
            and stage["imports"] == 4
            and stage["numerical"] > 0,
            "projection guards/imports",
        )
        memory(stage["active_cache_peak"])
    activation = row["activation"]
    require(
        activation["status"] == 0
        and activation["stats"][0] == 2
        and activation["stats"][2:] == [9, 4, 13, 1, 9, 0]
        and activation["materializations"] == 1,
        "activation ownership/materialization",
    )
    memory(activation["active_cache_peak"])
    obs = [
        donor.decoded_output(row[stage]["output"], [1, n])
        for stage, n in (("gate", 64), ("up", 64), ("activation", 64), ("down", 128))
    ]
    g, u, h, y = obs
    for role, v in (("gate", g), ("up", u)):
        require(
            all(abs(n) <= 16 for n in v[0])
            and activation[role + "_clamp_bits"]
            == donor.clamp_bits(row[role]["output"]["f32_bits"], role),
            "activation domain/clamps",
        )
    require(
        row["down_admission"]
        == dict(
            actual_input_sha256=activation["output"]["sha256"],
            decision="admitted",
            imports_before_decision=0,
            numerical_before_decision=0,
        ),
        "actual down input",
    )
    require(
        all(n == 0 or r1.F(1, 2**32) <= abs(n) <= 2**32 for n in h[0])
        and sum(map(abs, h[0])) <= 2**40,
        "down domain",
    )
    ref = reference.cases[profile, expert]
    local, bd = r1.qmm(h, ref["down"])
    for j in range(64):
        require(abs(g[0][j] - ref["g"][0][j]) <= ref["bg"][0][j], "gate numerical")
        require(abs(u[0][j] - ref["u"][0][j]) <= ref["bu"][0][j], "up numerical")
        require(
            r1.distance_pass(h[0][j], ref["h"][0][j], ref["bh"][0][j]),
            "hidden numerical",
        )
    for j in range(128):
        require(abs(y[0][j] - local[0][j]) <= bd[0][j], "down-local numerical")
        require(
            r1.distance_pass(
                y[0][j], ref["y"][0][j], bd[0][j] + ref["propagated"][0][j]
            ),
            "end-to-end numerical",
        )
    return tuple(
        struct.pack(
            "<" + "I" * len(row[k]["output"]["f32_bits"]), *row[k]["output"]["f32_bits"]
        )
        for k in ("gate", "up", "activation", "down")
    )


def read(root, name, limit):
    block = fixtures.contents(root, name, limit)
    return json.loads(block), len(block)


ABI_STAMP = "pulsarmlx.resident-layout/1|aarch64-apple-darwin|rustc 1.95.0 (59807616e 2026-04-14)|end"

# Bytes measured for the locked Darwin arm64 build with size_of; the private
# held row is String plus File and seven u64/i64 stamp fields, including padding.
LAYOUT = dict(
    source=368,
    shard=80,
    optional_file=4,
    header=72,
    string_pair=48,
    header_row=112,
    u64=8,
    catalog_row=112,
    override_row=32,
    held_row=88,
    json_row=56,
    json_value=32,
)


def checked_sum(*terms):
    require(all(type(x) is int and x >= 0 for x in terms), "nonnegative ledger terms")
    n = sum(terms)
    require(n <= (1 << 64) - 1, "ledger u64 overflow")
    return n


def text_bytes(value):
    return len(value.encode("utf-8"))


def json_payload(value):
    if isinstance(value, str):
        return text_bytes(value)
    if isinstance(value, list):
        return checked_sum(
            len(value) * LAYOUT["json_value"], *(json_payload(v) for v in value)
        )
    if isinstance(value, dict):
        return checked_sum(
            len(value) * LAYOUT["json_row"],
            *(text_bytes(k) + json_payload(v) for k, v in value.items()),
        )
    return 0


def metadata_terms(repo, profile):
    require(
        profile in ("default", "mixed") and repo == repo.resolve(strict=True),
        "canonical accounting root",
    )
    view = repo / "fixtures/resident-expert-mlp"
    manifest_raw = fixtures.contents(view, "manifest.json", 1 << 20)
    require(sha(manifest_raw) == VIEW_SHA, "accounting fixture manifest")
    recipe = json.loads(manifest_raw)["recipes"][profile]
    root = view / recipe["name"]
    require(root == root.resolve(strict=True), "canonical fixture root")

    def fixed(file, role):
        b = fixtures.contents(root, file, 1 << 20)
        require(sha(b) == recipe["files"][role], "accounting " + role)
        return b

    config = json.loads(fixed("config.json", "config"))
    index = json.loads(fixed("model.safetensors.index.json", "index"))["weight_map"]
    shard = "model.safetensors"
    raw = fixed(shard, "shard")
    tensors = json.loads(raw[8 : 8 + int.from_bytes(raw[:8], "little")])
    meta = tensors.pop("__metadata__")
    require(
        set(index) == set(tensors)
        and set(index.values()) == {shard}
        and len(tensors) == 9,
        "fixed accounting catalog",
    )
    names = sum(text_bytes(k) for k in tensors)
    dims = sum(len(v["shape"]) * LAYOUT["u64"] for v in tensors.values())
    overrides = [k for k, v in config["quantization"].items() if isinstance(v, dict)]
    held = ("config.json", "model.safetensors.index.json", shard)
    terms = dict(
        bounded_source=LAYOUT["source"],
        identity_string=64,
        checkpoint_name=text_bytes(root.name),
        shard_row=LAYOUT["shard"] + LAYOUT["optional_file"] + text_bytes(shard),
        header=LAYOUT["header"],
        header_metadata=sum(
            LAYOUT["string_pair"] + text_bytes(k) + text_bytes(v)
            for k, v in meta.items()
        ),
        header_tensors=len(tensors) * LAYOUT["header_row"] + 2 * names + dims,
        catalog=len(tensors) * LAYOUT["catalog_row"] + 2 * names + dims,
        index=sum(
            LAYOUT["string_pair"] + text_bytes(k) + text_bytes(v)
            for k, v in index.items()
        ),
        overrides=len(overrides) * LAYOUT["override_row"]
        + sum(text_bytes(k) for k in overrides),
        held_files=len(held) * LAYOUT["held_row"] + sum(text_bytes(k) for k in held),
        config_document=json_payload(config),
    )
    fixed_sum = checked_sum(*terms.values())
    root_bytes = str(root).encode("utf-8")
    return dict(
        terms=terms,
        fixed_bytes=fixed_sum,
        root_bytes=len(root_bytes),
        root_sha256=sha(root_bytes),
        M=checked_sum(fixed_sum, len(root_bytes)),
    )


def accounting_proof(repo, stamp):
    require(
        stamp == ABI_STAMP
        and sys.platform == "darwin"
        and platform.machine() == "arm64"
        and sys.byteorder == "little"
        and struct.calcsize("P") == 8,
        "unsupported resident accounting ABI",
    )
    return dict(
        schema="resident-accounting/1",
        abi_stamp=stamp,
        layout=LAYOUT.copy(),
        checker_sha256=sha(Path(__file__).read_bytes()),
        view_sha256=VIEW_SHA,
        profiles={p: metadata_terms(repo, p) for p in ("default", "mixed")},
    )


def expect_ledger(profile, arm, recipe, repo=None):
    size = binding(recipe, 0)[1]
    meta = metadata_terms(fixtures.ROOT if repo is None else repo, profile)["M"]
    control_meta = meta if arm == "allocating" else 0
    control = size if arm == "allocating" else 0
    base = checked_sum(2 * size, meta, 1 << 20, 64 << 10)
    parts = []
    for i, p in enumerate(recipe["planes"][0]):
        n, k = p["logical_shape"]
        packed = n * k * p["bits"] // 8
        raw = 4 * n * (k // 64)
        parts.append(
            dict(
                packed=packed,
                metadata_raw=raw,
                metadata_f32=2 * raw,
                input=4 * k,
                output=4 * n,
                bytes=packed + 3 * raw + 4 * (k + n),
            )
        )
    extra = dict(
        control_metadata=control_meta,
        control_tuple=control,
        staging_tuple=size,
        descriptor_key_and_shape_allowance=32768,
        input_copy=512,
        qmm_readbacks=1536,
        activation_temporaries=1280,
        saved_row_capacity=9 * 32768,
        record_and_serialization_workspace=192 << 10,
    )
    native = dict(
        qmm=parts,
        activation=1800,
        temporary_headroom=4 << 20,
        bound=(4 << 20) + max(1800, *(v["bytes"] for v in parts)),
        envelope=NATIVE,
        cache_limit=0,
    )
    return dict(
        S=size,
        M=meta,
        W_cache=base,
        H_extra=1 << 20,
        N_native=NATIVE,
        W_total=checked_sum(base, 1 << 20, NATIVE),
        host_bound=checked_sum(*extra.values()),
        native=native,
        **extra,
    )


def admit_arm(root, profile, arm, identity, reference, intent_hash):
    report, total = read(root, "report.json", 128 << 10)
    require(
        report["schema"] == "resident-mlp-v1"
        and report["identity"] == identity
        and report["intent_sha256"] == intent_hash
        and (report["profile"], report["arm"]) == (profile, arm),
        "arm custody",
    )
    recipe = reference.recipes[profile]
    require(
        report["fixture"]
        == dict(
            profile=profile,
            checkpoint=recipe["name"],
            content=recipe["content"],
            metadata=recipe["metadata"],
            shard_sha256=recipe["files"]["shard"],
            input_sha256=fixtures.INPUT,
            view_sha256=VIEW_SHA,
        ),
        "fixture custody",
    )
    require(report["failure"] is None and report["row_count"] == 9, "incomplete arm")
    provenance = report["provenance"]
    require(
        all(
            provenance[n]["sha256"] == identity["native"][n]
            for n in ("libmlx", "libmlxc", "metallib")
        )
        and not provenance["other_mlx_named_images"]
        and provenance["build"]["qualify_executable_sha256"]
        == identity["binary_sha256"]
        and provenance["mlx_commit_pinned"] == identity["native"]["mlx_commit"]
        and provenance["mlx_c_commit_pinned"] == identity["native"]["mlx_c_commit"]
        and provenance["environment"]["MLX_ENABLE_TF32"] == "0",
        "runtime/build custody",
    )
    require(
        all(
            report["allocator"][k] == 0
            for k in ("cache_limit", "initial_clear", "initial_cache")
        ),
        "cache initialization",
    )
    require(
        identity["accounting"] == accounting_proof(fixtures.ROOT, ABI_STAMP),
        "current root and accounting proof",
    )
    ledger = report["ledger"]
    require(ledger == expect_ledger(profile, arm, recipe), "exact fixed reservation")
    require(
        ledger["W_total"] == ledger["W_cache"] + (1 << 20) + NATIVE
        and ledger["H_extra"] == 1 << 20
        and ledger["N_native"] == NATIVE
        and ledger["host_bound"] <= 1 << 20
        and ledger["native"]["bound"] <= NATIVE
        and ledger["control_tuple"] == (ledger["S"] if arm == "allocating" else 0),
        "working reservation",
    )
    seq = report["sequence"]
    require(
        seq["activation_reads"] == [1, 1, 2]
        and seq["positions"] == [1, 1, 2]
        and seq["delivery_failed"] is True
        and seq["replay_same_commit"] is True
        and seq["first"] == seq["replay"]
        and seq["final"] == report["final"]
        and seq["active_reservation"] == 0
        and seq["peak_reservation"] == ledger["W_total"] + 512 + 3072 + 1536 + 8,
        "coordinator sequence",
    )
    for key, count in (("before", 0), ("first", 6), ("final", 9)):
        s = seq[key]
        cached = arm == "cached"
        expected = dict(
            cache_reads=36 if count and cached else 0,
            control_reads=0 if cached else count * 9,
            cache_fills=4 if count and cached else 0,
            cache_hits=count - 4 if count and cached else 0,
            cache_evictions=2 if count and cached else 0,
            cache_consumed=count if cached else 0,
            occupied=2 * ledger["S"] if count and cached else 0,
            dispatches={0: 0, 6: 1, 9: 2}[count],
            mlp_calls=count,
            records=count,
            qmm_imports=count * 12,
            projections=count * 3,
            activations=count,
            quarantined=False,
            working_bytes=ledger["W_total"],
        )
        require(s == expected, "actual storage and native operation counts")
    expected_files = {"report.json"} | {f"occ-{i:02}.json" for i in range(9)}
    require({p.name for p in root.iterdir()} == expected_files, "ordered population")
    stages = []
    for i in range(9):
        row, n = read(root, f"occ-{i:02}.json", 32768)
        total += n
        stages.append(row_check(row, profile, arm, i, reference))
    require(
        total <= 512 << 10
        and seq["output_sha256"]
        == [sha(b"".join(x[3] for x in group)) for group in (stages[:6], stages[6:])],
        "step concatenation and report bound",
    )
    return stages


def compare(arms):
    require(list(arms) == list(ARMS), "complete four-arm population")
    for profile in ("default", "mixed"):
        require(
            len(arms[profile, "allocating"]) == 9
            and arms[profile, "allocating"] == arms[profile, "cached"],
            "control/cached byte parity",
        )
