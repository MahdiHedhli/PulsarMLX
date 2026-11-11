"""Only new tiny synthetic reference values and harmless owned subprocesses."""

import copy
import ast
import base64
import subprocess
import shutil
from functools import lru_cache
from contextlib import ExitStack
from unittest.mock import patch
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import f020_resident_mlp_check as c
import f020_resident_mlp_supervise as s


def tensor(values):
    words = [struct.unpack("<I", struct.pack("<f", float(v)))[0] for v in values]
    data = struct.pack("<" + "I" * len(words), *words)
    return dict(
        dtype="F32",
        shape=[1, len(words)],
        bytes=len(data),
        sha256=c.sha(data),
        f32_bits=words,
    )


def simulated(refs, p, a, i):
    expert = c.ORDER[i]
    recipe = refs.recipes[p]
    ref = refs.cases[p, expert]
    h = tensor([(lo + hi) / 2 for lo, hi in ref["h"][0]])
    actual = c.donor.decoded_output(h, [1, 64])
    local, _ = c.r1.qmm(actual, ref["down"])
    data = [tensor(ref["g"][0]), tensor(ref["u"][0]), tensor(local[0])]
    binding, size = c.binding(recipe, expert)
    planes = recipe["planes"][expert]
    hashes = [v["sha256"] for v in planes]
    stages = {
        role: dict(
            bits=pl["bits"],
            group_size=64,
            packed_weight_sha256=pl["sha256"][0],
            output=value,
            bound_gamma_n=c.r1.gamma_n(1, *pl["logical_shape"]),
            device_facts_gpu=True,
            cpu_guard_checks=2,
            imports_before_decision=0,
            numerical_before_decision=0,
            imports=4,
            numerical=3,
            active_cache_peak=[1, 0, 21],
        )
        for role, pl, value in zip(c.ROLES, planes, data)
    }
    return dict(
        **stages,
        ordinal=i,
        step=int(i >= 6),
        expert=expert,
        recipe=p,
        slot_generation=list(c.SLOTS[i]) if a == "cached" else None,
        binding=binding,
        component_sha256_before=hashes,
        component_sha256_after=hashes,
        staging_capacity=size + 900,
        copies=dict(
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
        cleanup=dict(
            live=0, freed=25, double_free=0, errors=0, messages=0, results=[9, 9, 0]
        ),
        activation=dict(
            status=0,
            stats=[2, 0, 9, 4, 13, 1, 9, 0],
            materializations=1,
            gate_clamp_bits=c.donor.clamp_bits(data[0]["f32_bits"], "gate"),
            up_clamp_bits=c.donor.clamp_bits(data[1]["f32_bits"], "up"),
            output=h,
            active_cache_peak=[1, 0, 4],
        ),
        down_admission=dict(
            actual_input_sha256=h["sha256"],
            decision="admitted",
            imports_before_decision=0,
            numerical_before_decision=0,
        ),
    )


@lru_cache(maxsize=1)
def synthetic_population():
    refs = c.Reference()
    return refs, {
        (p, e): simulated(refs, p, "allocating", c.ORDER.index(e))
        for p in ("default", "mixed")
        for e in range(3)
    }


class SyntheticRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.refs, cls.rows = synthetic_population()

    def row(self, p, a, i):
        v = copy.deepcopy(self.rows[p, c.ORDER[i]])
        v.update(
            ordinal=i,
            step=int(i >= 6),
            slot_generation=list(c.SLOTS[i]) if a == "cached" else None,
        )
        return v


def synthetic_report(root, p, a, identity, intent, refs, row_for):
    recipe = refs.recipes[p]
    native = identity["native"]
    prov = {n: dict(sha256=native[n]) for n in ("libmlx", "libmlxc", "metallib")}
    prov.update(
        other_mlx_named_images=[],
        build=dict(qualify_executable_sha256=identity["binary_sha256"]),
        mlx_commit_pinned=native["mlx_commit"],
        mlx_c_commit_pinned=native["mlx_c_commit"],
        environment=dict(MLX_ENABLE_TF32="0"),
    )
    ledger = c.expect_ledger(p, a, recipe)
    size = ledger["S"]
    work = ledger["W_total"]

    def snap(n):
        return dict(
            cache_reads=36 if n and a == "cached" else 0,
            control_reads=9 * n if a == "allocating" else 0,
            cache_fills=4 if n and a == "cached" else 0,
            cache_hits=max(0, n - 4) if a == "cached" else 0,
            cache_evictions=2 if n and a == "cached" else 0,
            cache_consumed=n if a == "cached" else 0,
            occupied=2 * size if n and a == "cached" else 0,
            dispatches={0: 0, 6: 1, 9: 2}[n],
            mlp_calls=n,
            records=n,
            qmm_imports=n * 12,
            projections=n * 3,
            activations=n,
            quarantined=False,
            working_bytes=work,
        )

    fixture = dict(
        profile=p,
        checkpoint=recipe["name"],
        content=recipe["content"],
        metadata=recipe["metadata"],
        shard_sha256=recipe["files"]["shard"],
        input_sha256=c.fixtures.INPUT,
        view_sha256=c.VIEW_SHA,
    )
    outputs = []
    for i in range(9):
        row = row_for(p, a, i)
        (root / f"occ-{i:02}.json").write_text(json.dumps(row))
        words = row["down"]["output"]["f32_bits"]
        outputs.append(struct.pack("<128I", *words))
    seq = dict(
        before=snap(0),
        first=snap(6),
        replay=snap(6),
        final=snap(9),
        activation_reads=[1, 1, 2],
        positions=[1, 1, 2],
        delivery_failed=True,
        replay_same_commit=True,
        active_reservation=0,
        peak_reservation=work + 512 + 3072 + 1536 + 8,
        output_sha256=[c.sha(b"".join(x)) for x in (outputs[:6], outputs[6:])],
    )
    report = dict(
        schema="resident-mlp-v1",
        arm=a,
        profile=p,
        identity=identity,
        intent_sha256=intent,
        fixture=fixture,
        provenance=prov,
        allocator=dict(cache_limit=0, initial_clear=0, initial_cache=0),
        ledger=ledger,
        sequence=seq,
        final=snap(9),
        failure=None,
        row_count=9,
    )

    return report


class Numerical(SyntheticRows):
    def test_six_original_references_and_complete_ordered_population(self):
        arms = {}
        for p, a in c.ARMS:
            arms[p, a] = [
                c.row_check(self.row(p, a, i), p, a, i, self.refs) for i in range(9)
            ]
        c.compare(arms)
        del arms["mixed", "cached"]
        with self.assertRaises(ValueError):
            c.compare(arms)

    def test_complete_report_and_fresh_custody(self):
        p, a = "mixed", "cached"
        recipe = self.refs.recipes[p]
        native = {
            n: "test-" + n
            for n in ("libmlx", "libmlxc", "metallib", "mlx_commit", "mlx_c_commit")
        }
        identity = dict(
            binary_sha256="test-child",
            native=native,
            accounting=c.accounting_proof(c.fixtures.ROOT, c.ABI_STAMP),
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            report = synthetic_report(
                root, p, a, identity, "fresh", self.refs, self.row
            )
            seq = report["sequence"]

            def check():
                (root / "report.json").write_text(json.dumps(report))
                return c.admit_arm(root, p, a, identity, self.refs, "fresh")

            self.assertEqual(len(check()), 9)
            report["identity"] = {**identity, "binary_sha256": "historical-child"}
            with self.assertRaisesRegex(ValueError, "custody"):
                check()
            report["identity"] = identity
            seq["replay"]["qmm_imports"] += 1
            with self.assertRaisesRegex(ValueError, "sequence"):
                check()
            seq["replay"] = copy.deepcopy(seq["first"])
            (root / "occ-08.json").unlink()
            with self.assertRaisesRegex(ValueError, "population"):
                check()

    def test_relocated_report_stale_equal_length_root_and_tampered_ledger(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp).resolve()
            roots = [parent / n for n in ("é-東", "ù-京")]
            for dest in roots:
                shutil.copytree(c.fixtures.VIEW, dest / "fixtures/resident-expert-mlp")
            p, a = "default", "allocating"
            native = {
                n: "synthetic-" + n
                for n in ("libmlx", "libmlxc", "metallib", "mlx_commit", "mlx_c_commit")
            }
            ident = dict(
                native=native,
                binary_sha256="test-child",
                accounting=c.accounting_proof(roots[0], c.ABI_STAMP),
            )
            out = parent / "out"
            out.mkdir()
            with (
                patch.object(c.fixtures, "ROOT", roots[0]),
                patch.object(
                    c.fixtures, "VIEW", roots[0] / "fixtures/resident-expert-mlp"
                ),
            ):
                report = synthetic_report(out, p, a, ident, "test", self.refs, self.row)

                def observe():
                    (out / "report.json").write_bytes(s.canonical(report))
                    return c.admit_arm(out, p, a, ident, self.refs, "test")

                self.assertEqual(len(observe()), 9)
                report["ledger"]["M"] += 1
                with self.assertRaisesRegex(ValueError, "reservation"):
                    observe()
                report["ledger"]["M"] -= 1
                with (
                    patch.object(c.fixtures, "ROOT", roots[1]),
                    self.assertRaisesRegex(ValueError, "root and accounting proof"),
                ):
                    observe()
                ident["accounting"]["checker_sha256"] = "wrong-proof"
                with self.assertRaisesRegex(ValueError, "root and accounting proof"):
                    observe()

    def test_binding_matches_real_cache_plan(self):
        self.assertEqual(
            [c.binding(self.refs.recipes[p], 0)[0] for p in ("default", "mixed")],
            [
                "e7eecd09be2260bfb1217dc8e6cc47e779afb8ceebf5375e68384f0e1cb6f5e6",
                "b6bb1f3351934a930861a7cae1359775f682710e084719451ad93516f5b39cfd",
            ],
        )

    def test_wrong_identity_guards_coverage_and_ownership(self):
        for field, new in [
            (("expert",), 1),
            (("step",), 1),
            (("ordinal",), 1),
            (("recipe",), "mixed"),
            (("slot_generation",), [0, 1]),
            (("binding",), "0" * 64),
            (("gate", "bits"), 8),
            (("down", "packed_weight_sha256"), "0" * 64),
            (("gate", "bound_gamma_n"), 99),
            (("gate", "extra_budget"), 1),
            (("gate", "imports_before_decision"), 1),
            (("activation", "materializations"), 0),
            (("down_admission", "decision"), "refused"),
            (("down_admission", "actual_input_sha256"), "0" * 64),
            (("gate", "output", "sha256"), "0" * 64),
            (("cleanup", "errors"), 1),
            (("cleanup", "live"), 1),
            (("cleanup", "results"), [9, 8, 0]),
            (("activation", "active_cache_peak"), [0, 0, c.NATIVE + 1]),
            (("end_to_end_reference",), "candidate hidden"),
        ]:
            with self.subTest(field=field):
                row = self.row("default", "allocating", 0)
                cur = row
                for k in field[:-1]:
                    cur = cur[k]
                cur[field[-1]] = new
                with self.assertRaises(ValueError):
                    c.row_check(row, "default", "allocating", 0, self.refs)

    def test_corrupted_values_with_recomputed_hashes_and_clamps(self):
        for role, n in (("gate", 64), ("up", 64), ("activation", 64), ("down", 128)):
            row = self.row("mixed", "cached", 0)
            row[role]["output"] = tensor([15] * n)
            if role in ("gate", "up"):
                row["activation"][role + "_clamp_bits"] = c.donor.clamp_bits(
                    row[role]["output"]["f32_bits"], role
                )
            if role == "activation":
                row["down_admission"]["actual_input_sha256"] = row[role]["output"][
                    "sha256"
                ]
            with self.assertRaisesRegex(ValueError, "numerical"):
                c.row_check(row, "mixed", "cached", 0, self.refs)
        row = self.row("mixed", "cached", 0)
        row["down"]["output"] = tensor([float("nan")] * 128)
        with self.assertRaises(ValueError):
            c.row_check(row, "mixed", "cached", 0, self.refs)

    def test_parity_requires_matching_bytes_per_stage(self):
        arms = {key: [(b"a", b"b", b"c", b"d")] * 9 for key in c.ARMS}
        arms["mixed", "cached"][8] = (b"a", b"B", b"c", b"d")
        with self.assertRaises(ValueError):
            c.compare(arms)


class Supervisor(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.cfg = self.root / "config.json"
        s.exclusive(self.cfg, {"fixture": "test"})
        self.claim = self.root / s.CLAIM

    def run_fake(self, output, mode="success", final=True):
        def run(intent, directory, deadline):
            code = {
                "success": "pass",
                "fail": "raise SystemExit(7)",
                "timeout": "import time;time.sleep(30)",
            }[mode]
            s.wait_child(
                [sys.executable, "-I", "-S", "-c", code],
                {},
                directory,
                deadline,
                0.05 if mode == "timeout" else 3,
            )

        def grade():
            if not final:
                raise ValueError("final binding drift")
            return {"test_only": True}

        s.sequence(self.cfg, {}, {"test_only": True}, output, self.claim, run, grade)

    def test_serial_intents_completions_and_no_new_output_refund(self):
        out = self.root / "run"
        self.run_fake(out)
        for i, (p, a) in enumerate(c.ARMS):
            d = out / f"{i}-{p}-{a}"
            self.assertEqual(s.doc(d / "intent.json")["arm"], a)
            self.assertEqual(
                s.doc(d / "completed.json"),
                dict(
                    pid=s.doc(d / "started.json")["pid"],
                    exit=0,
                    reaped=True,
                    timeout=False,
                ),
            )
        self.assertTrue((out / "result.json").exists())
        with self.assertRaises(FileExistsError):
            self.run_fake(self.root / "elsewhere")

    def test_nonzero_exit_preserved_and_no_next_arm(self):
        out = self.root / "run"
        with self.assertRaises(ValueError):
            self.run_fake(out, "fail")
        done = s.doc(out / "0-default-allocating/completed.json")
        self.assertEqual(done["exit"], 7)
        self.assertTrue(done["reaped"])
        self.assertFalse((out / "1-default-cached").exists())

    def test_timeout_terminates_and_reaps(self):
        out = self.root / "run"
        with self.assertRaises(ValueError):
            self.run_fake(out, "timeout")
        done = s.doc(out / "0-default-allocating/completed.json")
        self.assertEqual(done["exit"], -9)
        self.assertTrue(done["reaped"] and done["timeout"])
        with self.assertRaises(ChildProcessError):
            os.waitpid(done["pid"], os.WNOHANG)

    def test_final_refusal_preserves_grading_claim(self):
        out = self.root / "run"
        with self.assertRaisesRegex(ValueError, "final binding"):
            self.run_fake(out, final=False)
        self.assertTrue((out / "grading-intent.json").exists())
        self.assertFalse((out / "result.json").exists())

    def test_output_escape_and_symlink_refused(self):
        sub = self.root / "sub"
        sub.mkdir()
        link = self.root / "link"
        link.symlink_to(sub)
        with self.assertRaises(ValueError):
            s.path(link / "out", False)
        receipt = sub / "install"
        s.exclusive(receipt, {})
        config = dict(
            installation=str(receipt),
            output=str(sub / "bad"),
            prefix=str(sub),
            freeze=str(receipt),
            diagnostic_receipt=str(receipt),
            build=str(receipt),
            binary=str(receipt),
        )
        with self.assertRaises(ValueError):
            s.locations(config)

    def test_local_or_old_work_order_rejected(self):
        with self.assertRaises(ValueError):
            s.operator(
                dict(
                    commit="0" * 40,
                    path="Prompts/RUST-ENGINE/MacBook-Pro-M2-Max/016__prompt.md",
                    sha256="0" * 64,
                )
            )
        with self.assertRaises(ValueError):
            s.wait_child([], {}, self.root, time.monotonic() - 1, 300)


class ProductionAdmission(SyntheticRows):
    """Only host/build/Git/inspection observations and physical processes are synthetic."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.temp = Path(tmp.name).resolve()
        self.prefix = self.temp / "prefix"
        self.libs = self.prefix / "lib"
        self.libs.mkdir(parents=True)
        self.runtime = self.libs / "libjaccl.dylib"
        for name in ("libmlx.dylib", "libmlxc.dylib", "libjaccl.dylib", "mlx.metallib"):
            (self.libs / name).write_bytes(("synthetic:" + name).encode())
        self.install = self.temp / "history/install.json"
        self.install.parent.mkdir()
        self.freeze = self.install.parent / "freeze.json"
        self.diag = self.install.parent / "diagnostic.json"
        self.real_hash = s.hashed
        s.exclusive(
            self.install,
            dict(
                source_pins=s.PINS,
                extra_runtime_library_sha256=s.runtime.RUNTIME_SHA256,
            ),
        )
        s.exclusive(
            self.freeze,
            dict(
                native_build_receipt=str(self.install),
                native_libraries={
                    n: s.hashed(self.libs / n)
                    for n in ("libmlx.dylib", "libmlxc.dylib", "mlx.metallib")
                },
            ),
        )
        s.exclusive(
            self.diag,
            dict(
                native_prefix=str(self.prefix), native_build_receipt=str(self.install)
            ),
        )
        pins = {
            self.install: s.INSTALL,
            self.freeze: s.FREEZE,
            self.diag: "d867b245b6be75e62cf352ba5c73cf376a2b2b3fa9b66943e8beb062c3d8f920",
        }
        self.originals = {p: (p.read_bytes(), h) for p, h in pins.items()}
        self.imports = {
            "libmlx.dylib": ["@rpath/libjaccl.dylib", "/usr/lib/libSystem.B.dylib"],
            "libmlxc.dylib": ["@rpath/libmlx.dylib"],
            "libjaccl.dylib": ["/usr/lib/libSystem.B.dylib"],
        }
        self.binary = self.temp / "target/release/qualify-resident-mlp"
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(
            b"synthetic inert Mach-O substitute\n" + c.ABI_STAMP.encode()
        )
        self.binary.chmod(0o700)
        self.build = self.temp / "build/receipt.json"
        self.build.parent.mkdir()
        artifact = self.build.parent / "artifact.json"
        self.src = dict(
            commit="1" * 40, tree="2" * 40, inventory_sha256="3" * 64, file_count=5150
        )
        s.exclusive(
            artifact,
            dict(
                reason="compiler-artifact",
                target=dict(
                    kind=["bin"],
                    name=self.binary.name,
                    src_path=str(
                        s.ROOT / "crates/mlx-expert-mlp/src/bin/qualify-resident-mlp.rs"
                    ),
                ),
                profile=dict(opt_level="3", test=False),
                package_id="synthetic-mlx-expert-mlp",
                executable=str(self.binary),
                features=["resident-native"],
            ),
        )
        s.exclusive(
            self.build,
            dict(
                commit=self.src["commit"],
                tree=self.src["tree"],
                binary_sha256=s.hashed(self.binary),
                prefix=str(self.prefix),
                artifact=str(artifact),
                artifact_sha256=s.hashed(artifact),
                linkage=self.inspection("-L", self.binary).splitlines()[1:],
                accounting_abi_stamp=c.ABI_STAMP,
                verifier_modules=s.verifier_modules(),
            ),
        )
        self.output = self.temp / "output"
        self.claim = self.install.parent / s.CLAIM
        self.config = dict(
            repo=str(s.ROOT),
            prefix=str(self.prefix),
            binary=str(self.binary),
            build=str(self.build),
            installation=str(self.install),
            freeze=str(self.freeze),
            diagnostic_receipt=str(self.diag),
            output=str(self.output),
        )
        self.cfg = self.temp / "config.json"
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(s, "hashed", side_effect=self.file_digest))
        stack.enter_context(
            patch.object(
                s.runtime,
                "file_hash",
                side_effect=lambda p: (
                    s.runtime.RUNTIME_SHA256
                    if p.read_bytes() == b"synthetic:libjaccl.dylib"
                    else self.real_hash(p)
                ),
            )
        )
        stack.enter_context(
            patch.object(s.runtime, "inspect_image", side_effect=self.inspection)
        )
        stack.enter_context(patch.object(s, "cmd", side_effect=self.external))
        stack.enter_context(
            patch.object(s, "source", side_effect=lambda: self.src.copy())
        )
        # GitHub-hosted host tests still model the future physical observations.
        stack.enter_context(patch.dict(os.environ, {}, clear=False))
        for key in ("GITHUB_ACTIONS", "DEVELOPER_DIR", "TOOLCHAINS", "OTOOL"):
            os.environ.pop(key, None)
        self.identity = s.physical_identity(self.config)
        grant = s.grant_for(self.config, self.identity)
        self.markdown = (
            "Synthetic work order\n```resident-mlp-grant\n"
            + json.dumps(grant, separators=(",", ":"))
            + "\n```\n"
        ).encode()
        self.spec = dict(
            commit="4" * 40,
            path="Prompts/TEST/Mac-Studio-M1-Ultra/test__prompt.md",
            sha256=c.sha(self.markdown),
        )
        self.config["operator"] = self.spec
        s.exclusive(self.cfg, self.config)

    def file_digest(self, p):
        if p in self.originals and p.read_bytes() == self.originals[p][0]:
            return self.originals[p][1]
        return self.real_hash(p)

    def inspection(self, flag, image):
        name = image.name
        imports = (
            ["@rpath/libmlxc.dylib", "@rpath/libmlx.dylib"]
            if image == self.binary
            else ["@rpath/" + name, *self.imports[name]]
        )
        if flag == "-L":
            return (
                str(image)
                + ":\n"
                + "".join(
                    "\t" + v + " (compatibility version 1.0.0, current version 1.0.0)\n"
                    for v in imports
                )
            )
        commands = (
            [("LC_ID_DYLIB", imports[0])]
            + [("LC_LOAD_DYLIB", v) for v in imports[1:]]
            + [("LC_RPATH", "@loader_path")]
        )
        out = str(image) + ":\n"
        for i, (cmd, value) in enumerate(commands):
            offset = 12 if cmd == "LC_RPATH" else 24
            size = (offset + len(value.encode()) + 8) // 8 * 8
            out += (
                f"Load command {i}\n cmd {cmd}\n cmdsize {size}\n "
                + ("path" if offset == 12 else "name")
                + f" {value} (offset {offset})\n"
            )
        return out

    def external(self, *args):
        if args[0] == "/usr/sbin/sysctl":
            return {
                "hw.model": b"Mac13,2",
                "machdep.cpu.brand_string": b"Apple M1 Ultra",
                "hw.memsize": b"137438953472",
                "hw.pagesize": b"16384",
            }[args[-1]]
        if args[0] == "/usr/bin/sw_vers":
            return b"26.0" if args[1] == "-productVersion" else b"25A354"
        if Path(args[0]).name == "gh":
            name = args[-1].split("/contents/")[1].split("?")[0]
            raw = (
                self.markdown
                if name == self.spec["path"]
                else (
                    self.spec["sha256"] + "  " + Path(self.spec["path"]).name + "\n"
                ).encode()
            )
            return json.dumps(
                dict(path=name, size=len(raw), content=base64.b64encode(raw).decode())
            ).encode()
        if args[:2] == ("/usr/bin/git", "rev-parse"):
            return self.src["tree" if "tree" in args[-1] else "commit"].encode()
        raise AssertionError(args)

    def synthetic_child(self, command, env, armdir, deadline, limit):
        self.assertEqual(env, s.child_environment(self.prefix))
        self.assertEqual(limit, 300)
        intent = Path(command[-1])
        v = s.doc(intent)
        pid = os.getppid()
        s.exclusive(armdir / "started.json", dict(pid=pid))
        s.verify_child(intent)
        out = armdir / "out"
        out.mkdir()
        report = synthetic_report(
            out,
            v["profile"],
            v["arm"],
            v["identity"],
            s.hashed(intent),
            self.refs,
            self.row,
        )
        s.exclusive(out / "report.json", report)
        s.exclusive(
            armdir / "completed.json", dict(pid=pid, exit=0, reaped=True, timeout=False)
        )

    def test_pinned_original_refusal_and_current_production_acceptance(self):
        base = "e6b64faddc9342754ebb5ec34f4b7e0afc4e6e56"
        data = subprocess.check_output(
            ["git", "show", base + ":scripts/research/f020_resident_mlp_supervise.py"],
            cwd=s.ROOT,
        )
        self.assertEqual(
            c.sha(data),
            "2f142f288ecada3cd8e61e28c313dfb4cd7daf101ff450f455f3bb50c2fcde92",
        )
        fn = next(
            x
            for x in ast.parse(data).body
            if isinstance(x, ast.FunctionDef) and x.name == "installed"
        )
        ns = dict(s.__dict__)
        exec(
            compile(
                ast.Module(body=[fn], type_ignores=[]), "<Rust016 installed>", "exec"
            ),
            ns,
        )
        with self.assertRaisesRegex(ValueError, "retained external runtime"):
            ns["installed"](self.config)
        self.assertFalse(self.claim.exists())
        self.assertEqual(s.admit(self.config), self.identity)
        record = self.identity["native"]["static_inspection"]
        self.assertFalse(record["loaded_runtime_image_observed"])
        self.assertEqual(
            record["files"]["libjaccl.dylib"]["canonical"], str(self.runtime)
        )
        self.assertEqual(
            sum(
                e["classification"] == "retained_extra_runtime" for e in record["edges"]
            ),
            1,
        )

    def test_fixed_alias_reobservation_and_drift(self):
        target = self.temp / "external/libjaccl.dylib"
        target.parent.mkdir()
        self.runtime.rename(target)
        self.runtime.symlink_to(target)
        self.imports["libmlxc.dylib"].extend([str(target), "@rpath/libjaccl.dylib"])
        static = s.installed(self.config)["static_inspection"]
        entry = static["files"]["libjaccl.dylib"]
        self.assertEqual(entry["canonical"], str(target))
        self.assertEqual(len(entry["symlinks"]), 1)
        self.assertEqual(
            sum(
                e["classification"] == "retained_extra_runtime" for e in static["edges"]
            ),
            3,
        )

        def changed(flag, image):
            text = self.inspection(flag, image)
            if flag == "-l" and image.name == "libjaccl.dylib":
                moved = self.temp / "new-target"
                moved.write_bytes(target.read_bytes())
                self.runtime.unlink()
                self.runtime.symlink_to(moved)
            return text

        with (
            patch.object(s.runtime, "inspect_image", side_effect=changed),
            self.assertRaisesRegex(ValueError, "drift"),
        ):
            s.installed(self.config)

    def test_no_claim_for_own_id_unknown_dependency_or_bad_runtime(self):
        old = self.imports["libmlx.dylib"]
        for imports in [[], ["@rpath/unknown.dylib"], ["@loader_path/libjaccl.dylib"]]:
            self.imports["libmlx.dylib"] = imports
            with self.assertRaises(ValueError):
                s.launch(self.cfg)
            self.assertFalse(self.claim.exists())
            self.assertFalse(self.output.exists())
        self.imports["libmlx.dylib"] = old
        self.runtime.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "runtime bytes"):
            s.launch(self.cfg)
        self.runtime.unlink()
        with self.assertRaises(FileNotFoundError):
            s.launch(self.cfg)
        self.runtime.mkdir()
        with self.assertRaisesRegex(ValueError, "regular file"):
            s.launch(self.cfg)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.claim.exists())

    def test_preclaim_build_operator_helper_and_abi_mismatches(self):
        original = s.doc(self.build)
        for field, value in [
            ("accounting_abi_stamp", "another ABI"),
            ("verifier_modules", {}),
            ("tree", "stale"),
            ("binary_sha256", "stale"),
        ]:
            self.build.write_bytes(s.canonical({**original, field: value}))
            with self.assertRaises(ValueError):
                s.launch(self.cfg)
            self.assertFalse(self.claim.exists())
        self.build.write_bytes(s.canonical(original))
        self.config["operator"]["sha256"] = "0" * 64
        self.cfg.write_bytes(s.canonical(self.config))
        with self.assertRaises(ValueError):
            s.launch(self.cfg)
        self.assertFalse(self.output.exists())
        with (
            patch.dict(os.environ, {"DYLD_LIBRARY_PATH": str(self.libs)}),
            self.assertRaisesRegex(ValueError, "inspector overrides"),
        ):
            s.physical_identity(self.config)
        with (
            patch.object(s.runtime, "inspect_image", return_value="truncated"),
            self.assertRaises(ValueError),
        ):
            s.installed(self.config)
        with self.assertRaisesRegex(ValueError, "overflow"):
            c.checked_sum((1 << 64) - 1, 1)

    def test_typed_inspection_refuses_truncated_command_and_fixed_system_override(self):
        def truncated(flag, image):
            listing = self.inspection(flag, image)
            if flag == "-l":
                return listing.replace("cmdsize 48", "cmdsize 8").replace(
                    "(offset 24)", "(offset 4096)"
                )
            return listing

        with (
            patch.object(s.runtime, "inspect_image", side_effect=truncated),
            self.assertRaisesRegex(ValueError, "malformed|truncated"),
        ):
            s.installed(self.config)
        (self.libs / "libSystem.B.dylib").write_bytes(b"synthetic competing leaf")
        with self.assertRaisesRegex(ValueError, "competing"):
            s.installed(self.config)

    def test_after_first_child_drift_preserves_spent_claim(self):
        def first(*args):
            self.synthetic_child(*args)
            self.runtime.write_bytes(b"changed")

        with (
            patch.object(s, "wait_child", side_effect=first) as starts,
            self.assertRaises(ValueError),
        ):
            s.launch(self.cfg)
        self.assertEqual(starts.call_count, 1)
        self.assertTrue(self.claim.is_file())
        self.assertFalse((self.output / "result.json").exists())
        self.assertFalse((self.output / "1-default-cached/started.json").exists())
        with self.assertRaisesRegex(ValueError, "existing physical claim"):
            s.launch(self.cfg)

    def test_sole_grade_and_final_source_drift(self):
        grading_observations = []

        def git_observation():
            if (self.output / "grading-intent.json").exists():
                grading_observations.append(True)
                if len(grading_observations) == 2:
                    self.runtime.write_bytes(b"changed")
            return self.src.copy()

        with (
            patch.object(s, "wait_child", side_effect=self.synthetic_child),
            patch.object(s, "source", side_effect=git_observation),
            self.assertRaisesRegex(ValueError, "runtime bytes"),
        ):
            s.launch(self.cfg)
        self.assertEqual(len(grading_observations), 2)
        self.assertTrue(self.claim.exists())
        self.assertTrue((self.output / "grading-intent.json").exists())
        self.assertFalse((self.output / "result.json").exists())
        self.assertEqual(len(list(self.output.glob("*/completed.json"))), 4)

    def test_production_verify_child_final_admission_and_inspect(self):
        with patch.object(s, "wait_child", side_effect=self.synthetic_child) as starts:
            s.launch(self.cfg)
        self.assertEqual(starts.call_count, 4)
        s.inspect(self.cfg)
        self.assertEqual(s.doc(self.output / "result.json")["identity"], self.identity)


if __name__ == "__main__":
    unittest.main(verbosity=2)
