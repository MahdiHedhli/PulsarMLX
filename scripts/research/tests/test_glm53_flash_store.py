"""Independent tests for the bounded GLM53-Flash synthetic store slice."""

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import glm53_flash.store as store  # noqa: E402


ROLES = ("gate", "up", "down")
PLANES = ("packed", "scales", "biases")
SEMANTIC_DOMAIN = b"PULSARMLX-GLM53-FLASH-SYNTHETIC-SEMANTIC-V1\x00"
BUNDLE_DOMAIN = b"PULSARMLX-GLM53-FLASH-SYNTHETIC-BUNDLE-V1\x00"


def oracle_canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def oracle_pack(values, bits):
    factor = 32 // bits
    words = []
    for base in range(0, len(values), factor):
        word = 0
        for field in range(factor):
            word |= values[base + field] << (bits * field)
        words.append(word)
    return struct.pack(f"<{len(words)}I", *words)


def oracle_decode(descriptor, packed, scales, biases):
    """Scalar oracle: deliberately shares no candidate arithmetic helper."""
    shape = descriptor["shape"]
    bits = descriptor["precision"]["bits"]
    group = descriptor["precision"]["group_size"]
    count = math.prod(shape)
    factor = 32 // bits
    words = struct.unpack(f"<{count // factor}I", packed)
    scale_values = struct.unpack(f"<{count // group}d", scales)
    bias_values = struct.unpack(f"<{count // group}d", biases)
    last = shape[-1]
    words_per_row = last // factor
    groups_per_row = last // group
    mask = (1 << bits) - 1
    answer = []
    for flat in range(count):
        row, column = divmod(flat, last)
        word = words[row * words_per_row + column // factor]
        q = (word // (1 << (bits * (column % factor)))) & mask
        affine = row * groups_per_row + column // group
        answer.append(q * scale_values[affine] + bias_values[affine])
    return tuple(answer)


def read_planes(root, manifest):
    result = {}
    for projection in manifest["projections"]:
        shard = (root / projection["shard"]).read_bytes()
        for plane in PLANES:
            segment = projection[plane]
            result[(projection["role"], plane)] = shard[
                segment["offset"] : segment["offset"] + segment["length"]
            ]
    return result


def oracle_semantic(root, manifest):
    rows = {row["role"]: row for row in manifest["projections"]}
    planes = read_planes(root, manifest)
    digest = hashlib.sha256()
    digest.update(SEMANTIC_DOMAIN)
    for role in ROLES:
        row = rows[role]
        descriptor = {
            key: row[key] for key in ("role", "shape", "encoding", "precision")
        }
        encoded = oracle_canonical(descriptor)
        digest.update(struct.pack("<H", len(encoded)))
        digest.update(encoded)
        for plane in PLANES:
            data = planes[(role, plane)]
            digest.update(struct.pack("<Q", len(data)))
            digest.update(data)
    return digest.hexdigest()


def resign(manifest):
    unsigned = {key: value for key, value in manifest.items() if key != "bundle_id"}
    manifest["bundle_id"] = hashlib.sha256(
        BUNDLE_DOMAIN + oracle_canonical(unsigned)
    ).hexdigest()


def oracle_padding_range_count(manifest):
    ranges = {row["name"]: [] for row in manifest["shards"]}
    sizes = {row["name"]: row["size"] for row in manifest["shards"]}
    for projection_row in manifest["projections"]:
        for plane in PLANES:
            segment = projection_row[plane]
            ranges[projection_row["shard"]].append(
                (segment["offset"], segment["offset"] + segment["length"])
            )
    gaps = 0
    for shard, shard_ranges in ranges.items():
        cursor = 0
        for start, end in sorted(shard_ranges):
            gaps += start > cursor
            cursor = end
        gaps += cursor < sizes[shard]
    return gaps


def observe(case, manifest, telemetry, **extra):
    record = {
        "case": case,
        "bundle_id": manifest["bundle_id"],
        "fixture_bytes": sum(row["size"] for row in manifest["shards"]),
        "semantic_sha256": manifest["semantic_sha256"],
        "telemetry": telemetry,
        **extra,
    }
    print("STORE_OBSERVED=" + json.dumps(record, sort_keys=True, separators=(",", ":")))


def projection(shape, bits, group, seed):
    rng = random.Random(seed)
    count = math.prod(shape)
    groups = count // group
    scales = (0.125, 0.25, 0.5, 1.0)
    biases = (-1.0, -0.5, 0.0, 1.5)
    return store.ProjectionInput(
        tuple(shape),
        bits,
        group,
        tuple(rng.randrange(1 << bits) for _ in range(count)),
        tuple(scales[index % len(scales)] for index in range(groups)),
        tuple(biases[(index + 1) % len(biases)] for index in range(groups)),
    )


def base_inputs():
    return {
        "gate": projection((2, 64), 4, 64, 0x53A401),
        "up": projection((3, 32), 8, 16, 0x53A401 + 1),
        "down": projection((2, 16), 4, 8, 0x53A401 + 2),
    }


def heldout_inputs():
    return {
        "gate": projection((3, 32), 8, 16, 0x53A402),
        "up": projection((2, 64), 4, 64, 0x53A402 + 1),
        "down": projection((5, 16), 8, 8, 0x53A402 + 2),
    }


class TemporaryFixture(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="glm53-store-")
        self.root = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def write_base(self, **changes):
        options = {
            "layer": 2,
            "expert": 3,
            "projection_order": ("gate", "up", "down"),
            "projections": base_inputs(),
            "shard_for_role": {
                "gate": "base-a.bin",
                "up": "base-a.bin",
                "down": "base-b.bin",
            },
            "alignment": 16,
        }
        options.update(changes)
        return store.write_synthetic_bundle(self.root, **options)


class BitLayoutTests(TemporaryFixture):
    def test_literal_lowbit_words_and_independent_decode(self):
        four_values = tuple(range(8))
        eight_values = (1, 2, 128, 255)
        self.assertEqual(oracle_pack(four_values, 4), b"\x10\x32\x54\x76")
        self.assertEqual(oracle_pack(eight_values, 8), b"\x01\x02\x80\xff")
        self.assertEqual(store.pack_lowbit(four_values, 4), b"\x10\x32\x54\x76")
        self.assertEqual(store.pack_lowbit(eight_values, 8), b"\x01\x02\x80\xff")

        descriptor4 = {
            "shape": [8],
            "precision": {"bits": 4, "group_size": 8},
        }
        expected4 = (-1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5)
        actual4 = oracle_decode(
            descriptor4,
            b"\x10\x32\x54\x76",
            struct.pack("<d", 0.5),
            struct.pack("<d", -1.0),
        )
        self.assertEqual(actual4, expected4)
        self.assertEqual(
            store.decode_projection(
                descriptor4,
                b"\x10\x32\x54\x76",
                struct.pack("<d", 0.5),
                struct.pack("<d", -1.0),
            ),
            expected4,
        )
        for invalid_bits in (4.0, True):
            with self.subTest(public_decode_bits=invalid_bits):
                invalid_descriptor = deepcopy(descriptor4)
                invalid_descriptor["precision"]["bits"] = invalid_bits
                with self.assertRaises(store.ManifestError):
                    store.decode_projection(
                        invalid_descriptor,
                        b"\x10\x32\x54\x76",
                        struct.pack("<d", 0.5),
                        struct.pack("<d", -1.0),
                    )
                with self.assertRaises(store.ManifestError):
                    store.pack_lowbit(four_values, invalid_bits)

        descriptor8 = {
            "shape": [4],
            "precision": {"bits": 8, "group_size": 4},
        }
        expected8 = (0.75, 1.0, 32.5, 64.25)
        actual8 = oracle_decode(
            descriptor8,
            b"\x01\x02\x80\xff",
            struct.pack("<d", 0.25),
            struct.pack("<d", 0.5),
        )
        self.assertEqual(actual8, expected8)

    def test_base_roundtrip_identity_and_independent_decode(self):
        manifest = self.write_base()
        self.assertEqual(manifest["semantic_sha256"], oracle_semantic(self.root, manifest))
        expected_id = deepcopy(manifest)
        expected_id.pop("bundle_id")
        self.assertEqual(
            manifest["bundle_id"],
            hashlib.sha256(BUNDLE_DOMAIN + oracle_canonical(expected_id)).hexdigest(),
        )
        reader = store.FixtureReader(self.root)
        demand = store.DemandStore(self.root, [manifest], reader=reader)
        with demand.acquire((2, 3)) as bundle:
            planes = read_planes(self.root, manifest)
            for descriptor in manifest["projections"]:
                role = descriptor["role"]
                expected = oracle_decode(
                    descriptor,
                    planes[(role, "packed")],
                    planes[(role, "scales")],
                    planes[(role, "biases")],
                )
                self.assertEqual(bundle.decoded[role], expected)
                for plane in PLANES:
                    self.assertEqual(bundle.raw_planes[(role, plane)], planes[(role, plane)])
        telemetry = demand.telemetry()
        self.assertEqual(telemetry["attempted_reads"], telemetry["completed_reads"])
        self.assertEqual(telemetry["requested_bytes"], telemetry["returned_bytes"])
        self.assertEqual(telemetry["physical_io"], "NOT_MEASURABLE")
        self.assertEqual(telemetry["native_map_unmap"], "NOT_EXERCISED")
        observe("base", manifest, telemetry)

    def test_heldout_changed_layout_and_semantic_relayout(self):
        first = self.write_base()
        with tempfile.TemporaryDirectory(prefix="glm53-heldout-") as directory:
            other = Path(directory)
            changed = store.write_synthetic_bundle(
                other,
                layer=7,
                expert=1,
                projection_order=("down", "gate", "up"),
                projections=heldout_inputs(),
                shard_for_role={"down": "held-c.bin", "gate": "held-b.bin", "up": "held-a.bin"},
                alignment=32,
                layout_offsets={"down": 32, "gate": 64, "up": 96},
            )
            heldout_store = store.DemandStore(other, [changed])
            with heldout_store.acquire((7, 1)) as bundle:
                self.assertEqual(bundle.semantic_sha256, oracle_semantic(other, changed))
                self.assertEqual(tuple(changed["projection_order"]), ("down", "gate", "up"))
                self.assertEqual(
                    {row["role"]: row["precision"]["bits"] for row in changed["projections"]},
                    {"down": 8, "gate": 8, "up": 4},
                )
            observe("heldout", changed, heldout_store.telemetry())

        with tempfile.TemporaryDirectory(prefix="glm53-relayout-") as directory:
            relayout_root = Path(directory)
            relayout = store.write_synthetic_bundle(
                relayout_root,
                layer=2,
                expert=3,
                projection_order=("down", "up", "gate"),
                projections=base_inputs(),
                shard_for_role={"gate": "r-g.bin", "up": "r-u.bin", "down": "r-d.bin"},
                alignment=32,
                layout_offsets={"gate": 96, "up": 64, "down": 32},
            )
            self.assertEqual(first["semantic_sha256"], relayout["semantic_sha256"])
            self.assertNotEqual(first["bundle_id"], relayout["bundle_id"])


class RejectionTests(TemporaryFixture):
    def assert_manifest_rejected(self, manifest):
        with self.assertRaises(store.StoreError):
            store.validate_manifest(self.root, manifest)

    def test_metadata_roles_shards_extras_and_geometry_rejected(self):
        original = self.write_base()
        mutations = []

        value = deepcopy(original)
        value["extra"] = 1
        mutations.append(value)
        for path in ("bundle", "projection", "precision", "segment", "shard"):
            value = deepcopy(original)
            if path == "bundle":
                value["bundle"]["extra"] = 1
            elif path == "projection":
                value["projections"][0]["extra"] = 1
            elif path == "precision":
                value["projections"][0]["precision"]["extra"] = 1
            elif path == "segment":
                value["projections"][0]["packed"]["extra"] = 1
            else:
                value["shards"][0]["extra"] = 1
            mutations.append(value)

        value = deepcopy(original)
        value["projections"] = value["projections"][:2]
        mutations.append(value)
        value = deepcopy(original)
        value["projections"][1]["role"] = "gate"
        mutations.append(value)
        value = deepcopy(original)
        value["projections"][0]["role"] = "other"
        mutations.append(value)
        value = deepcopy(original)
        value["shards"].append(deepcopy(value["shards"][0]))
        mutations.append(value)
        value = deepcopy(original)
        value["shards"].append({"name": "unused.bin", "size": 0})
        mutations.append(value)
        value = deepcopy(original)
        value["projections"][0]["shard"] = "unknown.bin"
        mutations.append(value)
        value = deepcopy(original)
        value["projections"][0]["precision"]["bits"] = 3
        mutations.append(value)
        for invalid_bits in (4.0, True):
            value = deepcopy(original)
            value["projections"][0]["precision"]["bits"] = invalid_bits
            resign(value)
            mutations.append(value)
        value = deepcopy(original)
        value["projections"][0]["shape"][0] = 0
        mutations.append(value)
        value = deepcopy(original)
        value["projections"][0]["packed"]["length"] += 4
        mutations.append(value)
        value = deepcopy(original)
        value["projections"][0]["scales"]["offset"] = value["projections"][0]["packed"]["offset"]
        mutations.append(value)
        value = deepcopy(original)
        value["projections"][0]["biases"]["offset"] += 1
        mutations.append(value)
        value = deepcopy(original)
        value["projections"][0]["packed"]["offset"] = (1 << 64) - 1
        mutations.append(value)
        value = deepcopy(original)
        value["projections"][0]["packed"]["offset"] = value["shards"][0]["size"]
        mutations.append(value)
        value = deepcopy(original)
        value["bundle_id"] = "0" * 64
        mutations.append(value)
        for mutation in mutations:
            with self.subTest(index=mutations.index(mutation)):
                self.assert_manifest_rejected(mutation)

    def test_nonfinite_padding_hash_and_actual_size_rejected(self):
        manifest = self.write_base()
        gate = next(row for row in manifest["projections"] if row["role"] == "gate")
        path = self.root / gate["shard"]
        with path.open("r+b") as handle:
            handle.seek(gate["scales"]["offset"])
            handle.write(struct.pack("<d", float("nan")))
        manifest["semantic_sha256"] = oracle_semantic(self.root, manifest)
        resign(manifest)
        with self.assertRaisesRegex(store.ManifestError, "nonfinite"):
            store.DemandStore(self.root, [manifest]).acquire((2, 3))

        with tempfile.TemporaryDirectory(prefix="glm53-nonfinite-producer-") as directory:
            inputs = base_inputs()
            inputs["gate"] = store.ProjectionInput(
                (1, 32), 8, 32, (255,) * 32, (1e308,), (0.0,)
            )
            with self.assertRaisesRegex(store.ManifestError, "decoded"):
                store.write_synthetic_bundle(
                    directory,
                    layer=0,
                    expert=0,
                    projection_order=ROLES,
                    projections=inputs,
                    shard_for_role={role: f"{role}.bin" for role in ROLES},
                )

        with tempfile.TemporaryDirectory(prefix="glm53-padding-") as directory:
            pad_root = Path(directory)
            padded = store.write_synthetic_bundle(
                pad_root,
                layer=2,
                expert=3,
                projection_order=ROLES,
                projections=base_inputs(),
                shard_for_role={role: f"{role}.bin" for role in ROLES},
                alignment=32,
                layout_offsets={"gate": 32, "up": 32, "down": 32},
            )
            target = pad_root / padded["shards"][0]["name"]
            data = bytearray(target.read_bytes())
            data[0] = 1
            target.write_bytes(data)
            with self.assertRaisesRegex(store.ManifestError, "padding"):
                store.DemandStore(pad_root, [padded]).acquire((2, 3))

        with tempfile.TemporaryDirectory(prefix="glm53-size-") as directory:
            size_root = Path(directory)
            sized = store.write_synthetic_bundle(
                size_root,
                layer=2,
                expert=3,
                projection_order=ROLES,
                projections=base_inputs(),
                shard_for_role={role: f"{role}.bin" for role in ROLES},
            )
            target = size_root / sized["shards"][0]["name"]
            with target.open("ab") as handle:
                handle.write(b"x")
            with self.assertRaisesRegex(store.ManifestError, "size"):
                store.DemandStore(size_root, [sized]).acquire((2, 3))

    def test_semantic_mismatch_rejected(self):
        manifest = self.write_base()
        manifest["semantic_sha256"] = "0" * 64
        resign(manifest)
        with self.assertRaisesRegex(store.ManifestError, "semantic"):
            store.DemandStore(self.root, [manifest]).acquire((2, 3))

    def test_symlink_and_escape_paths_rejected(self):
        outside = self.root.parent / f"{self.root.name}-outside.bin"
        outside.write_bytes(b"secret")
        try:
            final_link = self.root / "final-link.bin"
            final_link.symlink_to(outside)
            reader = store.FixtureReader(self.root)
            with self.assertRaises(store.PathSafetyError):
                reader.read("final-link.bin", 0, 1)
            self.assertEqual(outside.read_bytes(), b"secret")

            component = self.root / "component"
            component.symlink_to(outside.parent, target_is_directory=True)
            with self.assertRaises(store.PathSafetyError):
                reader.read("component" + os.sep + outside.name, 0, 1)
            with self.assertRaises(store.StoreError):
                reader.read("../" + outside.name, 0, 1)
            with self.assertRaises(store.StoreError):
                reader.read(str(outside), 0, 1)
            with self.assertRaises(store.StoreError):
                reader.read("./final-link.bin", 0, 1)
            with self.assertRaises(store.StoreError):
                reader.read("component//" + outside.name, 0, 1)

            root_link = self.root.parent / f"{self.root.name}-root-link"
            root_link.symlink_to(self.root, target_is_directory=True)
            try:
                with self.assertRaises(store.PathSafetyError):
                    store.FixtureReader(root_link)
            finally:
                root_link.unlink()

            real_parent = self.root / "real-parent"
            (real_parent / "child").mkdir(parents=True)
            ancestor_link = self.root / "ancestor-link"
            ancestor_link.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaises(store.PathSafetyError):
                store.FixtureReader(ancestor_link / "child")

            pinned = self.root / "pinned-root"
            pinned.mkdir()
            (pinned / "value.bin").write_bytes(b"first")
            pinned_reader = store.FixtureReader(pinned)
            old_pinned = self.root / "old-pinned-root"
            pinned.rename(old_pinned)
            pinned.mkdir()
            (pinned / "value.bin").write_bytes(b"second")
            with self.assertRaises(store.PathSafetyError):
                pinned_reader.read("value.bin", 0, 5)
        finally:
            outside.unlink()


class StoreBehaviorTests(TemporaryFixture):
    def test_exact_read_telemetry_fault_classes(self):
        (self.root / "read.bin").write_bytes(b"abcdefgh")
        reader = store.FixtureReader(
            self.root,
            {2: ("short", 2), 3: "fail", 5: "disconnect"},
        )
        self.assertEqual(reader.read("read.bin", 0, 4), b"abcd")
        with self.assertRaises(store.ShortReadError):
            reader.read("read.bin", 0, 4)
        with self.assertRaises(store.ReadFailure):
            reader.read("read.bin", 0, 4)
        with self.assertRaises(store.ReadFailure):
            reader.read("read.bin", 6, 4)
        with self.assertRaises(store.ReadFailure):
            reader.read("read.bin", 0, 4)
        with self.assertRaises(store.ReadFailure):
            reader.read("missing.bin", 0, 4)
        self.assertEqual(
            reader.telemetry(),
            {
                "attempted_reads": 6,
                "completed_reads": 1,
                "short_reads": 1,
                "failed_reads": 4,
                "requested_bytes": 24,
                "returned_bytes": 6,
                "physical_io": "NOT_MEASURABLE",
                "native_map_unmap": "NOT_EXERCISED",
            },
        )
        print(
            "STORE_OBSERVED="
            + json.dumps(
                {"case": "reader-faults", "telemetry": reader.telemetry()},
                sort_keys=True,
                separators=(",", ":"),
            )
        )

    def test_missing_demand_and_lease_eviction(self):
        manifest = self.write_base()
        reader = store.FixtureReader(self.root)
        demand = store.DemandStore(self.root, [manifest], reader=reader)
        with self.assertRaises(store.MissingBundle):
            demand.acquire((99, 99))
        self.assertEqual(reader.telemetry()["attempted_reads"], 0)

        first = demand.acquire((2, 3))
        count = reader.telemetry()["attempted_reads"]
        second = demand.acquire((2, 3))
        self.assertEqual(reader.telemetry()["attempted_reads"], count)
        self.assertTrue(demand.evict((2, 3)))
        self.assertTrue(demand.contains((2, 3)))
        third = demand.acquire((2, 3))
        self.assertIs(first.bundle, third.bundle)
        first.close()
        second.close()
        self.assertTrue(demand.contains((2, 3)))
        third.close()
        self.assertFalse(demand.contains((2, 3)))
        self.assertFalse(demand.evict((2, 3)))

    def test_cancellation_restart_preserves_only_complete_segments(self):
        manifest = self.write_base()
        state = {}
        cancelled_reader = store.FixtureReader(self.root, {2: "cancel"})
        first = store.DemandStore(
            self.root, [manifest], reader=cancelled_reader, preserved_state=state
        )
        with self.assertRaises(store.LoadCancelled):
            first.acquire((2, 3))
        self.assertFalse(first.contains((2, 3)))
        self.assertEqual(len(state), 1)
        self.assertEqual(cancelled_reader.telemetry()["completed_reads"], 1)
        self.assertEqual(cancelled_reader.telemetry()["failed_reads"], 1)

        preserved_count = len(state)
        resumed_reader = store.FixtureReader(self.root)
        resumed = store.DemandStore(
            self.root, [manifest], reader=resumed_reader, preserved_state=state
        )
        with resumed.acquire((2, 3)) as bundle:
            self.assertEqual(bundle.semantic_sha256, manifest["semantic_sha256"])
        expected_segment_reads = 9 - preserved_count
        expected_padding_reads = oracle_padding_range_count(manifest)
        self.assertEqual(
            resumed_reader.telemetry()["attempted_reads"],
            expected_segment_reads + expected_padding_reads,
        )
        self.assertEqual(len(state), 9)
        observe(
            "cancel-restart",
            manifest,
            resumed_reader.telemetry(),
            cancellation_telemetry=cancelled_reader.telemetry(),
            preserved_before_restart=preserved_count,
            preserved_after_restart=len(state),
        )

        contaminated = {("0" * 64, "gate", "packed"): b""}
        with self.assertRaises(store.StateError):
            store.DemandStore(self.root, [manifest], preserved_state=contaminated)

        post_init_state = {}
        post_init = store.DemandStore(
            self.root, [manifest], preserved_state=post_init_state
        )
        post_init_state[("0" * 64, "up", "biases")] = b"bad"
        with self.assertRaises(store.StateError):
            post_init.acquire((2, 3))

        with tempfile.TemporaryDirectory(prefix="glm53-reader-root-") as other:
            with self.assertRaises(store.PathSafetyError):
                store.DemandStore(
                    self.root,
                    [manifest],
                    reader=store.FixtureReader(other),
                )

    def test_allocation_ceilings_reject_before_read(self):
        manifest = self.write_base()
        oversized = deepcopy(manifest)
        oversized["shards"][0]["size"] = store.MAX_FIXTURE_BYTES + 1
        resign(oversized)
        with self.assertRaisesRegex(store.ManifestError, "ceiling"):
            store.validate_manifest(self.root, oversized)

        reader = store.FixtureReader(self.root)
        with self.assertRaises(store.ReadFailure):
            reader.read("base-a.bin", 0, store.MAX_FIXTURE_BYTES + 1)
        self.assertEqual(reader.telemetry()["returned_bytes"], 0)
        self.assertEqual(reader.telemetry()["failed_reads"], 1)


if __name__ == "__main__":
    unittest.main()
