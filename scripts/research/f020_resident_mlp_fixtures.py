"""Build or verify the two indexed views of the frozen synthetic fixture."""

import argparse
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / "fixtures/expert-mlp-composition"
VIEW = ROOT / "fixtures/resident-expert-mlp"
MANIFEST = "2a63e04cb3e690a5b9b4b7c6440e279fad51b0b697771904ac22fbbef84d2a3d"
INPUT = "3c563f14ae18c17c9365324c2fd265ee96251a3448d5ae43e0fee1474cd5233c"
ROLES = ("gate", "up", "down")
PARTS = ("weight", "scales", "biases")


def require(test, why):
    if not test:
        raise ValueError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(v):
    return (json.dumps(v, sort_keys=True, indent=2) + "\n").encode()


def framed(*values):
    h = hashlib.sha256()
    for value in values:
        h.update(struct.pack("<Q", len(value)))
        h.update(value)
    return h.hexdigest()


def contents(root, name, size):
    path = root / name
    require(
        path.resolve(strict=True) == path
        and path.is_file()
        and path.stat().st_size <= size,
        "unexpected fixture path or size",
    )
    with path.open("rb") as f:
        data = f.read(size + 1)
    require(len(data) <= size, "fixture grew beyond limit")
    return data


def prepare(write=False):
    raw = contents(ORIGINAL, "manifest.json", 1 << 20)
    require(sha(raw) == MANIFEST, "original manifest")
    m = json.loads(raw)
    recipes = {}

    def emit(path, data):
        if write and not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as out:
                out.write(data)
        require(
            contents(VIEW, str(path.relative_to(VIEW)), 1 << 20) == data,
            "indexed fixture differs",
        )

    for profile in ("default", "mixed"):
        name = "d128-h64-" + profile
        cp = m["checkpoints"][name]

        def original(rel):
            b = contents(ORIGINAL, rel, 1 << 20)
            require(
                m["files"][rel] == {"bytes": len(b), "sha256": sha(b)}, "original file"
            )
            return b

        config = original(cp["path"] + "/config.json")
        shard = original(cp["path"] + "/model.safetensors")
        offset = 8 + int.from_bytes(shard[:8], "little")
        header = json.loads(shard[8:offset])
        names = {"synthetic.experts." + r + "." + p for r in ROLES for p in PARTS}
        require(set(header) == names | {"__metadata__"}, "nine tensor header")
        index = canonical({"weight_map": {k: "model.safetensors" for k in names}})
        for leaf, data in [
            ("config.json", config),
            ("model.safetensors", shard),
            ("model.safetensors.index.json", index),
        ]:
            emit(VIEW / name / leaf, data)
        planes = []
        for expert in range(3):
            roles = []
            for role in ROLES:
                expected = cp["expected_planes"][f"{role}/{expert}"]
                ranges = []
                require(len(expected["sha256"]) == len(PARTS), "component count")
                for part, digest in zip(PARTS, expected["sha256"]):
                    tensor = expected["module"] + "." + part
                    obj = header[tensor]
                    lo, hi = obj["data_offsets"]
                    length = (hi - lo) // 3
                    begin = offset + lo + expert * length
                    require(
                        (hi - lo) % 3 == 0
                        and sha(shard[begin : begin + length]) == digest,
                        "original plane",
                    )
                    ranges.append(
                        {
                            "tensor": tensor,
                            "shard": "model.safetensors",
                            "begin": begin,
                            "len": length,
                        }
                    )
                roles.append({**expected, "ranges": ranges})
            planes.append(roles)
        inputs = []
        for expert in range(3):
            cid = f"mlp-d128-h64-m1-e{expert}-{profile}"
            case = next(c for c in m["cases"] if c["id"] == cid)
            b = original(case["input"])
            require(len(b) == 512 and sha(b) == INPUT, "original input")
            inputs.append(case["input"])
        identities = dict(
            original_manifest=MANIFEST,
            config=sha(config),
            shard=sha(shard),
            index=sha(index),
        )
        recipes[profile] = dict(
            name=name,
            files=identities,
            content=sha(canonical(identities)),
            metadata=framed(
                b"pulsarmlx.bounded-expert-metadata/1",
                b"config.json",
                config,
                b"model.safetensors.index.json",
                index,
                b"model.safetensors",
                struct.pack("<Q", len(shard)),
                shard[:offset],
            ),
            inputs=inputs,
            input_sha256=INPUT,
            planes=planes,
        )
    manifest = {"schema": "pulsarmlx.resident-mlp-fixtures/1", "recipes": recipes}
    emit(VIEW / "manifest.json", canonical(manifest))
    return manifest


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--prepare", action="store_true")
    prepare(p.parse_args().prepare)
