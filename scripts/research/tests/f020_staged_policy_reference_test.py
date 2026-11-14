"""Independent controls for the scheduling, geometry and host evidence checker."""
import copy
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import f020_staged_policy_reference as ref


class StagedPolicyReference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix, cls.golden, cls.recipes = ref.frozen_inputs()

    def test_preregistered_geometry_and_reload(self):
        for page in (4096, 16384):
            for profile, recipe in self.recipes.items():
                for policy in ref.POLICIES:
                    with self.subTest(page=page, profile=profile, policy=policy):
                        steps, _, backing = ref.schedule_and_geometry(self.matrix, profile, recipe, page, policy)
                        self.assertEqual(backing, 49151 if page == 16384 else {"default":12287,"mixed":16383}[profile])
                        self.assertEqual([s["activity"]["requests"] for s in steps], [1,2,3,4,6])
                        self.assertEqual(steps[-1]["residents"], [[1,4,12],[2,2,11]])

    def test_hand_checked_edge_and_window(self):
        ranges = [{"begin":4090,"len":8,"shard":"s"}, {"begin":8192,"len":7,"shard":"s"}]
        rows = ref.windows.routes(ranges, {"s":8199}, 4096, "NoCacheRequested")
        self.assertEqual([r["route"] for r in rows], ["nocache-requested-aligned-window","buffered-edge-exact"])
        self.assertEqual(ref.totals(rows), [15,8199,8184,1,1,8])

    def test_reject_guessed_descriptor_count_and_wrong_miss(self):
        for field in ("descriptors", "warm_hit", "bytes"):
            matrix = copy.deepcopy(self.matrix)
            if field == "descriptors":
                matrix["cumulative"]["fresh_opens"][0] = 1
            elif field == "warm_hit":
                matrix["miss_tickets"][1][0][3] = 0
            else:
                matrix["cumulative_by_page"]["16384"]["default"][4][1] += 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                ref.schedule_and_geometry(matrix, "default", self.recipes["default"], 16384, "BufferedRequested")

    def test_reject_corrupt_evidence(self):
        # The qualification runner supplies the genuine host exports separately per build.
        folder = os.environ.get("STAGED_POLICY_EXPORT")
        if not folder:
            self.skipTest("Darwin fixed-policy exports required")
        profile, mode, policy = "default", "Serial", "NoCacheRequested"
        report = ref.read_json(Path(folder).resolve(strict=True) / f"positive-{profile}-{mode}-{policy}.json", ref.ARM_LIMIT)
        page = os.sysconf("SC_PAGE_SIZE")
        steps, layout, backing = ref.schedule_and_geometry(self.matrix, profile, self.recipes[profile], page, policy)
        ticket = steps[0]["tickets"][0]
        row = ref.strict(report["role_json"][0])[0]
        def check(r):
            return ref.check_role(r, ticket, 0, layout[0,0], profile, policy, page, backing, 0)
        self.assertGreater(check(row), 0)
        for name in ("crossed", "wrong-role", "retirement", "setter", "stamp", "overread", "partial", "scratch", "physical"):
            bad = copy.deepcopy(row)
            r = bad["outcome"]["receipt"]
            if name == "crossed":
                bad["generation"] += 1
            elif name == "wrong-role":
                bad["role"] = "up"
            elif name == "retirement":
                bad["outcome"]["retired_released"] = 0
            elif name == "setter":
                r["setup"]["slots"][0]["setter"]["argument"] ^= 1
            elif name == "stamp":
                r["setup"]["slots"][0]["fresh_stamp"][0] ^= 1
            elif name == "overread":
                r["completed_overread"] += 1
            elif name == "partial":
                r["effects"][0]["returned_bytes"] = None
            elif name == "scratch":
                r["ledger"]["backing_bytes"] -= 1
            else:
                r["physical_bytes"] = 0
            with self.subTest(name=name), self.assertRaises(ValueError):
                check(bad)


if __name__ == "__main__":
    unittest.main()
