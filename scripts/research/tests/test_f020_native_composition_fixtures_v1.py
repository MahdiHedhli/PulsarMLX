"""F020 Slice 2C: the composition fixture generator is deterministic, stdlib-only and its
oracle is independent of production slicing; the committed population is exactly what
it regenerates.

Standard library only. Nothing here imports MLX, runs cargo or reads a PulsarMLX crate's
output. Where this test re-derives a range it does so with its own header reader, which
shares no code with the generator's.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
GENERATOR = REPOSITORY_ROOT / "scripts" / "research" / "f020_native_composition_fixtures_v1.py"
EXACT_R1 = REPOSITORY_ROOT / "scripts" / "research" / "mlx_affine_qmm_reference_v1.py"
FIXTURES = REPOSITORY_ROOT / "fixtures" / "native-composition"
MANIFEST = FIXTURES / "manifest.json"

# The six frozen Slice 2B identities (COMMON-2C) and the Slice 1 contracts.
FROZEN = {
    "specs/020-mlx-safetensors-affine/contracts/native-primitives-v1.json":
        "76959ccb13046c664db67469fd8186b7fb668910072060400b38b682e92fec72",
    "specs/020-mlx-safetensors-affine/slice2b-plan.md":
        "24a06db0a34ee4ec8ca9af8728d3d27e26cfe3c4a6c22dcba06011c8ab2796df",
    "specs/020-mlx-safetensors-affine/source-pins-slice2.json":
        "02e963a02cf1d63168c57cff316c1d3471313498396b2abd7b3e5ec432267bb4",
    "scripts/research/f020_native_primitives_fixtures_v1.py":
        "28078a6d0a6de859c1a1ac557fef3f683d8ecd75a780198b4c0bc7c15c267999",
    "fixtures/native-primitives/manifest.json":
        "472b5b64aaddfe7ecbfd05930ba2f4d261023a9a829f957b5b23b110fcf37d04",
    "specs/020-mlx-safetensors-affine/contracts/numerics-v1.json":
        "ac61f0b66dac670ede2ed8dcb0a0db9cd98718bbd4ed9b364b805a1a535ca1bb",
    "specs/020-mlx-safetensors-affine/contracts/catalog-contract.md":
        "dc8fceba3556fdafba853c3a2f18ec7ce6c410be39ab4f827d068d660d691351",
}
SLICE2B_CASES_LISTING = "ed0c2e73420213a1ae316ea90a20100fcefee87bade32dec36ff7dac25461f82"

STDLIB_IMPORTS = {"__future__", "argparse", "hashlib", "importlib", "importlib.util", "json",
                  "struct", "sys", "pathlib"}
EXPECTED_FAMILIES = {"FX-COMP-ACCEPT": 11, "FX-COMP-SEQUENCE": 3, "FX-COMP-REFUSE": 9,
                     "FX-COMP-INHERITED-REFUSE": 3, "FX-COMP-MUTATION": 6}
COMPONENTS = ("weight", "scales", "biases")
WIDTH = {"U32": 4, "F32": 4, "F16": 2, "BF16": 2}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_side_header(blob: bytes) -> dict:
    """This test's own reading of a shard header (independent of the generator's)."""
    length = int.from_bytes(blob[:8], "little")
    header = json.loads(blob[8:8 + length].decode())
    header.pop("__metadata__", None)
    base = 8 + length
    return {name: {"dtype": e["dtype"], "shape": e["shape"],
                   "begin": base + e["data_offsets"][0], "end": base + e["data_offsets"][1]}
            for name, e in header.items()}


class CompositionFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = MANIFEST.read_bytes()
        cls.manifest = json.loads(cls.raw)
        cls.cases = {c["id"]: c for c in cls.manifest["cases"]}

    def shard(self, checkpoint_dir: str, name: str) -> bytes:
        return (FIXTURES / checkpoint_dir / name).read_bytes()

    # -- frozen inputs ---------------------------------------------------------
    def test_frozen_slice2b_and_slice1_identities_are_unchanged(self):
        for rel, want in FROZEN.items():
            self.assertEqual(sha256((REPOSITORY_ROOT / rel).read_bytes()), want, rel)
        cases_dir = REPOSITORY_ROOT / "fixtures" / "native-primitives"
        listing = "".join("%s  %s\n" % (sha256(p.read_bytes()), p.relative_to(cases_dir).as_posix())
                          for p in sorted((cases_dir / "cases").glob("*.bin"), key=lambda p: p.name.encode()))
        self.assertEqual(sha256(listing.encode()), SLICE2B_CASES_LISTING)

    # -- determinism -----------------------------------------------------------
    def test_check_passes_on_the_committed_population(self):
        run = subprocess.run([sys.executable, str(GENERATOR), "--out", str(FIXTURES), "--check"],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_two_fresh_generations_are_byte_identical_to_the_committed_files(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            for out in (one, two):
                run = subprocess.run([sys.executable, str(GENERATOR), "--out", out],
                                     capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
            first = {p.relative_to(one).as_posix(): p.read_bytes() for p in Path(one).rglob("*") if p.is_file()}
            second = {p.relative_to(two).as_posix(): p.read_bytes() for p in Path(two).rglob("*") if p.is_file()}
            committed = {p.relative_to(FIXTURES).as_posix(): p.read_bytes()
                         for p in FIXTURES.rglob("*") if p.is_file()}
            self.assertEqual(first, second)
            self.assertEqual(first, committed)

    def test_check_detects_a_changed_and_an_extra_file(self):
        with tempfile.TemporaryDirectory() as out:
            subprocess.run([sys.executable, str(GENERATOR), "--out", out], check=True, capture_output=True)
            target = Path(out) / "standalone" / "acc-a-stack_a-e0-m1.bin"
            data = bytearray(target.read_bytes())
            data[-1] ^= 1
            target.write_bytes(bytes(data))
            run = subprocess.run([sys.executable, str(GENERATOR), "--out", out, "--check"],
                                 capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("MISMATCH standalone/acc-a-stack_a-e0-m1.bin", run.stdout)
            data[-1] ^= 1
            target.write_bytes(bytes(data))
            (Path(out) / "stray.bin").write_bytes(b"x")
            run = subprocess.run([sys.executable, str(GENERATOR), "--out", out, "--check"],
                                 capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("UNEXPECTED stray.bin", run.stdout)

    # -- manifest bindings -----------------------------------------------------
    def test_manifest_binds_the_generator_and_every_file(self):
        self.assertEqual(self.manifest["generator_sha256"], sha256(GENERATOR.read_bytes()))
        self.assertEqual(self.manifest["inherits"]["slice2b_generator_sha256"],
                         FROZEN["scripts/research/f020_native_primitives_fixtures_v1.py"])
        names = sorted((p.relative_to(FIXTURES).as_posix() for p in FIXTURES.rglob("*")
                        if p.is_file() and p.name != "manifest.json"), key=str.encode)
        listing = "".join("%s  %s\n" % (sha256((FIXTURES / n).read_bytes()), n) for n in names)
        self.assertEqual(self.manifest["files_listing_sha256"], sha256(listing.encode()))
        for ck in self.manifest["checkpoints"].values():
            for name, meta in ck["files"].items():
                blob = (FIXTURES / ck["dir"] / name).read_bytes()
                self.assertEqual((sha256(blob), len(blob)), (meta["sha256"], meta["bytes"]))
            shards = sorted((n for n in ck["files"] if n.endswith(".safetensors")), key=str.encode)
            ident = "".join("%s  %s\n" % (ck["files"][n]["sha256"], n) for n in shards)
            self.assertEqual(ck["source_identity"], sha256(ident.encode()))
        for case in self.manifest["cases"]:
            if "file" in case:
                blob = (FIXTURES / case["file"]).read_bytes()
                self.assertEqual(sha256(blob), case["file_sha256"], case["id"])

    def test_case_accounting(self):
        ids = [c["id"] for c in self.manifest["cases"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(self.manifest["case_count"], len(ids))
        self.assertEqual(self.manifest["case_count_by_family"], EXPECTED_FAMILIES)
        self.assertEqual(len(ids), sum(EXPECTED_FAMILIES.values()))

    # -- the oracle, re-derived by this test -------------------------------------
    def test_oracle_ranges_equal_an_independent_header_derivation(self):
        for case in self.manifest["cases"]:
            ranges = case.get("oracle", {}).get("ranges")
            if not ranges:
                continue
            comp = case["composition"]
            ck_dir = comp["checkpoint"]
            ck = self.manifest["checkpoints"][ck_dir.split("/", 1)[1]]
            (index,) = comp["index_path"]
            for c in COMPONENTS:
                name = comp["module"] + "." + c
                shard = ck["modules"][comp["module"]]["tensors"][c]["shard"]
                t = test_side_header(self.shard(ck_dir, shard))[name]
                experts = t["shape"][0]
                per = (t["end"] - t["begin"]) // experts
                self.assertEqual(per * experts, t["end"] - t["begin"])
                self.assertEqual(ranges[c], {"shard": shard, "begin": t["begin"] + index * per, "len": per},
                                 (case["id"], c))

    def test_expected_plane_bytes_are_the_checkpoint_slices_and_the_standalone_tensors(self):
        for case in self.manifest["cases"]:
            ranges = case.get("oracle", {}).get("ranges")
            if not ranges:
                continue
            blob = (FIXTURES / case["file"]).read_bytes()
            tensors = {t["name"]: t for t in case["tensors"]}
            self.assertEqual([t["name"] for t in case["tensors"]], ["x", "w", "scales", "biases"])
            for c, tname in zip(COMPONENTS, ("w", "scales", "biases")):
                r = ranges[c]
                sliced = self.shard(case["composition"]["checkpoint"], r["shard"])[r["begin"]:r["begin"] + r["len"]]
                standalone = blob[tensors[tname]["offset"]:tensors[tname]["offset"] + tensors[tname]["nbytes"]]
                self.assertEqual(sliced, standalone, (case["id"], c))
                self.assertEqual(sha256(sliced), case["oracle"]["sha256"][c])

    def test_every_component_is_distinguishable_between_experts(self):
        for ck in self.manifest["checkpoints"].values():
            for module, m in ck["modules"].items():
                for c in COMPONENTS:
                    hashes = [e[c] for e in m["expert_sha256"]]
                    self.assertEqual(len(set(hashes)), m["experts"], (module, c))

    def test_identity_records_resolution_and_orientation(self):
        for case in self.manifest["cases"]:
            ident = case.get("oracle", {}).get("identity")
            if not ident:
                continue
            m = self.manifest["checkpoints"][ident["checkpoint"]]["modules"][ident["module"]]
            self.assertEqual((ident["bits"], ident["group_size"], ident["metadata_dtype"]),
                             (m["bits"], m["group_size"], "BF16"))
            self.assertEqual(ident["logical_shape"], [m["N"], m["K"]])
            self.assertTrue(ident["transpose"])
        # 4/8 resolution comes from the configuration, not from a hard-coded width.
        config = json.loads((FIXTURES / "checkpoints/ck-b-sharded/config.json").read_text())["quantization"]
        self.assertEqual((config["bits"], config["group_size"]), (4, 64))
        modules = self.manifest["checkpoints"]["ck-b-sharded"]["modules"]
        for name, m in modules.items():
            if name in config:
                self.assertEqual((m["bits"], m["resolved_from"]), (config[name]["bits"], "override"))
            else:
                self.assertEqual((m["bits"], m["resolved_from"]), (4, "default"))
        self.assertEqual(modules["block.1.stack_d"]["bits"], 8)

    def test_companions_in_different_shards_and_offset_boundaries(self):
        q = self.manifest["checkpoints"]["ck-b-sharded"]["modules"]["block.2.stack_q"]["tensors"]
        self.assertEqual(len({q[c]["shard"] for c in COMPONENTS}), 3)
        starts = [t["data_offsets"][0] for ck in self.manifest["checkpoints"].values()
                  for m in ck["modules"].values() for t in m["tensors"].values()]
        self.assertIn(0, starts)
        self.assertGreater(sum(1 for s in starts if s > 0), 10)

    # -- refusals and mutations ------------------------------------------------
    def test_each_refusal_probe_violates_exactly_its_expected_guard(self):
        for case in self.manifest["cases"]:
            exp = case["expected"]
            if exp["outcome"] != "refuse":
                continue
            self.assertEqual(exp["violated_guards"], [exp["refusal_id"]], case["id"])
            if case["family"] == "FX-COMP-REFUSE":
                self.assertTrue(exp["refusal_id"].startswith("C-R-"))
                self.assertEqual(exp["native_calls_in_case"], {"numerical": 0, "imports": 0})
                self.assertNotIn("file", case)
            else:
                self.assertTrue(exp["refusal_id"].startswith("R-"))
                self.assertEqual(exp["b_refusal_id"], exp["refusal_id"])
                self.assertEqual(case["oracle"]["composition_guards"],
                                 {k: False for k in self.manifest["composition_refusal_order"]})

    def test_mutations_are_detectable_by_construction(self):
        for case in self.manifest["cases"]:
            if case["family"] != "FX-COMP-MUTATION":
                continue
            mut = case["composition"]["mutation"]
            base = self.cases[case["composition"]["baseline_case"]]
            detected = case["expected"]["detected_by"]
            self.assertEqual(base["expected"]["outcome"], "accept")
            self.assertTrue(detected)
            # EXACT set equality: the detection set is precisely the set of
            # mismatches the specified mutation causes, no more and no fewer.
            implied = set()
            if "ranges" in mut:
                for c in COMPONENTS:
                    if mut["ranges"][c] != base["oracle"]["ranges"][c]:
                        implied |= {"S-RANGES:" + c, "S-BYTES:" + c}
            if "identity" in mut:
                implied |= {"S-IDENTITY:" + k for k in mut["identity"]
                            if mut["identity"][k] != base["oracle"]["identity"][k]}
            if "config" in mut:
                implied.add("C-R-RESOLVE")
            self.assertEqual(implied, set(detected), case["id"])
            self.assertEqual(len(detected), len(set(detected)), case["id"])
            if "ranges" in mut:
                for c in COMPONENTS:
                    changed = mut["ranges"][c] != base["oracle"]["ranges"][c]
                    self.assertEqual(changed, "S-RANGES:" + c in detected, (case["id"], c))
                    self.assertEqual(mut["sha256"][c] != base["oracle"]["sha256"][c], changed, (case["id"], c))
                    r = mut["ranges"][c]
                    data = self.shard(base["composition"]["checkpoint"], r["shard"])[r["begin"]:r["begin"] + r["len"]]
                    self.assertEqual(sha256(data), mut["sha256"][c])
            if "identity" in mut:
                diff = sorted(k for k in mut["identity"] if mut["identity"][k] != base["oracle"]["identity"][k])
                self.assertEqual(diff, ["bits", "resolved_from"])
            if "config" in mut:
                q = json.loads((FIXTURES / mut["config"]).read_text())["quantization"]
                self.assertNotIn(base["composition"]["module"], q)
        kinds = {c["composition"]["mutation"]["kind"] for c in self.manifest["cases"]
                 if c["family"] == "FX-COMP-MUTATION"}
        self.assertEqual(kinds, {"wrong_expert_index", "wrong_plane_stride", "scales_from_other_expert",
                                 "biases_from_other_expert", "override_ignored_at_resolution",
                                 "override_ignored_in_plane"})

    def test_recipe_probe_uses_identical_descriptors_and_a_shape_consistent_other_recipe(self):
        case = self.cases["ref-recipe-mismatch"]
        comp = case["composition"]
        self.assertEqual(comp["entry"], "E-SELECT")
        self.assertEqual(comp["triple_components"], {c: comp["module"] + "." + c for c in COMPONENTS})
        m = self.manifest["checkpoints"]["ck-a-single"]["modules"][comp["module"]]
        recipe = comp["triple_spec"]
        self.assertNotEqual((recipe["bits"], recipe["group_size"]), (m["bits"], m["group_size"]))
        # packed_cols*32 == groups*group*bits holds for BOTH recipes (Slice 1 admits either)
        for bits, group in ((recipe["bits"], recipe["group_size"]), (m["bits"], m["group_size"])):
            self.assertEqual(m["packed_cols"] * 32, m["groups"] * group * bits)
        self.assertEqual(case["expected"]["violated_guards"], ["C-R-RECIPE-BINDING"])

    def test_array_census_separates_measured_handles_from_derived_workspace(self):
        for case in self.manifest["cases"]:
            if case["expected"]["outcome"] != "accept":
                continue
            census = case["expected"]["array_census"]
            roles = [h["role"] for h in census["bridge_visible_handles"]]
            self.assertEqual(roles, ["x", "w", "scales", "biases", "scales_f32", "biases_f32", "out"])
            self.assertEqual(census["measured_counter_deltas"]["imports"], 4)
            self.assertEqual(census["measured_counter_deltas"]["result_handles_created"], 3)
            fams = case["expected"]["families_0_31_2"]
            split = [f for f in fams if f["family"] == "qmm_t_splitk"]
            ws = census["source_derived_workspace"]
            self.assertEqual(len(ws), len(split), case["id"])
            m, n = case["params"]["M_eff"], case["params"]["N"]
            for w, f in zip(ws, split):
                self.assertEqual((w["dtype"], w["shape"]), ("F32", [f["split_k"], m, n]))
                self.assertFalse(w["is_weight_matrix"])
                self.assertEqual(w["accounting"], "source-derived, not measured")
        matrix = [c for c in self.manifest["cases"] if c["expected"]["outcome"] == "accept"
                  and c["expected"]["array_census"]["source_derived_workspace"]]
        self.assertEqual(len(matrix), 8)

    def test_staged_inputs_and_source_hashes_are_the_manifest_records(self):
        for case in self.manifest["cases"]:
            staged = case["expected"].get("staged_inputs")
            if staged is None:
                continue
            self.assertEqual(list(staged), ["x", "w", "scales", "biases"])
            for t in case["tensors"]:
                self.assertEqual(staged[t["name"]], {k: t[k] for k in ("dtype", "shape", "nbytes", "sha256")})
            src = case["expected"]["source_hashes"]
            self.assertEqual(src["phases"], ["before_load", "after_host_selection", "after_native_execution"])
            ck = self.manifest["checkpoints"][case["composition"]["checkpoint"].split("/", 1)[1]]
            self.assertEqual(src["shards"], {n: v["sha256"] for n, v in ck["files"].items()
                                             if n.endswith(".safetensors")})
            self.assertEqual(src["standalone"], {case["file"]: case["file_sha256"]})

    def test_sibling_checkpoint_shares_the_header_but_not_the_payload(self):
        a = (FIXTURES / "checkpoints/ck-a-single/model.safetensors").read_bytes()
        s = (FIXTURES / "checkpoints/ck-a-sibling/model.safetensors").read_bytes()
        n = int.from_bytes(a[:8], "little")
        self.assertEqual(a[:8 + n], s[:8 + n])
        self.assertNotEqual(a, s)

    def test_sequence_repeats_the_first_selection_and_input(self):
        first, last = self.cases["seq-aba-0"], self.cases["seq-aba-2"]
        middle = self.cases["seq-aba-1"]
        self.assertEqual((FIXTURES / first["file"]).read_bytes(), (FIXTURES / last["file"]).read_bytes())
        self.assertEqual(last["composition"]["sequence"]["same_output_as"], "seq-aba-0")
        self.assertNotEqual(middle["oracle"]["identity"]["bits"], first["oracle"]["identity"]["bits"])

    def test_standalone_cases_parse_under_the_frozen_exact_r1_reader(self):
        """The Slice 2B exact R1 reader accepts every standalone file as an OP-QMM case
        (layout and geometry only; no reference value is computed here)."""
        r1 = load(EXACT_R1, "f020_exact_r1_reader")
        for case in self.manifest["cases"]:
            if case["expected"]["outcome"] != "accept":
                continue
            tensors = r1.read_tensors(case, FIXTURES)
            bits, group, n, k, *_ = r1._geometry(case, tensors, "N")
            m = case["composition"]["module"]
            ck = self.manifest["checkpoints"][case["composition"]["checkpoint"].split("/", 1)[1]]
            self.assertEqual((bits, group, n, k), (ck["modules"][m]["bits"], 64, ck["modules"][m]["N"],
                                                   ck["modules"][m]["K"]))
            self.assertIn("python_exact_r1", case["references"])
            self.assertIn("rust_binary64_r1", case["references"])

    # -- generator hygiene -----------------------------------------------------
    def test_generator_is_stdlib_only_and_never_reaches_production_code(self):
        tree = ast.parse(GENERATOR.read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module)
        self.assertLessEqual(imported, STDLIB_IMPORTS)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
                {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        for forbidden in ("subprocess", "system", "popen", "ctypes", "expert_slice", "row_slice",
                          "dequantize_rows", "unpack_codes", "mlx", "numpy", "cargo"):
            self.assertNotIn(forbidden, names)
        strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        loaded = [s for s in strings if s.endswith(".py")]
        self.assertEqual(sorted(set(loaded)), ["scripts/research/f020_native_composition_fixtures_v1.py",
                                              "scripts/research/f020_native_primitives_fixtures_v1.py"])

    def test_names_are_model_neutral_and_paths_are_relative(self):
        for p in FIXTURES.rglob("*.json"):
            text = p.read_text().lower()
            for token in ("glm", "pipenetwork", "qwen", "switch_mlp", "self_attn", "lm_head", "/users/", "/volumes/"):
                self.assertNotIn(token, text, p.name)

    def test_shards_are_admissible_safetensors(self):
        for ck in self.manifest["checkpoints"].values():
            for name in ck["files"]:
                if not name.endswith(".safetensors"):
                    continue
                blob = (FIXTURES / ck["dir"] / name).read_bytes()
                n = struct.unpack("<Q", blob[:8])[0]
                self.assertEqual(blob[8:9], b"{")
                spans = sorted((t["begin"], t["end"]) for t in test_side_header(blob).values())
                cursor = 8 + n
                for begin, end in spans:
                    self.assertEqual(begin, cursor)
                    cursor = end
                self.assertEqual(cursor, len(blob))
                for t in test_side_header(blob).values():
                    count = 1
                    for d in t["shape"]:
                        count *= d
                    self.assertEqual(t["end"] - t["begin"], count * WIDTH[t["dtype"]])


if __name__ == "__main__":
    unittest.main()
