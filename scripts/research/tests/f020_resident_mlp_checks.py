"""Only new tiny synthetic reference values and harmless owned subprocesses."""

import copy
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


class Numerical(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.refs = c.Reference()
        cls.rows = {
            (p, e): simulated(cls.refs, p, "allocating", c.ORDER.index(e))
            for p in ("default", "mixed")
            for e in range(3)
        }

    def row(self, p, a, i):
        v = copy.deepcopy(self.rows[p, c.ORDER[i]])
        v.update(
            ordinal=i,
            step=int(i >= 6),
            slot_generation=list(c.SLOTS[i]) if a == "cached" else None,
        )
        return v

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
        identity = dict(binary_sha256="test-child", native=native)
        prov = {n: dict(sha256=native[n]) for n in ("libmlx", "libmlxc", "metallib")}
        prov.update(
            other_mlx_named_images=[],
            build=dict(qualify_executable_sha256="test-child"),
            mlx_commit_pinned=native["mlx_commit"],
            mlx_c_commit_pinned=native["mlx_c_commit"],
            environment=dict(MLX_ENABLE_TF32="0"),
        )
        ledger = c.expect_ledger(p, a, recipe)
        size = ledger["S"]
        work = ledger["W_total"]

        def snap(n):
            return dict(
                cache_reads=36 if n else 0,
                control_reads=0,
                cache_fills=4 if n else 0,
                cache_hits=max(0, n - 4),
                cache_evictions=2 if n else 0,
                cache_consumed=n,
                occupied=2 * size if n else 0,
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
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            outputs = []
            for i in range(9):
                row = self.row(p, a, i)
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
                intent_sha256="fresh",
                fixture=fixture,
                provenance=prov,
                allocator=dict(cache_limit=0, initial_clear=0, initial_cache=0),
                ledger=ledger,
                sequence=seq,
                final=snap(9),
                failure=None,
                row_count=9,
            )

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
            seq["replay"] = snap(6)
            (root / "occ-08.json").unlink()
            with self.assertRaisesRegex(ValueError, "population"):
                check()

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
