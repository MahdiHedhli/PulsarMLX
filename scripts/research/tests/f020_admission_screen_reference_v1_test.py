import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import f020_admission_screen_reference_v1 as ref


class Reference(unittest.TestCase):
    def setUp(self):
        self.base=ref.parse(ref.read_fixture("template.json"))

    def run_case(self,calls,policy="TwoHit"):
        return ref.simulate(ref.json_bytes(dict(self.base,calls=calls)),policy)

    def test_exact_disjoint_categories_and_transient_epochs(self):
        report=self.run_case([[0,0],[0,0],[0,0]])
        self.assertEqual([e["category"] for e in report["events"]],["M","U_T","M","U_R","R","R"])
        self.assertEqual([e["kind"] for e in report["events"]][:2],["Transient"]*2)
        self.assertEqual(report["metrics"]["read_avoidance_ratio"],[4,6])
        self.assertEqual(report["metrics"]["persistent_hit_ratio"],[2,6])
        self.assertEqual(report["state"]["history"],[])

    def test_completed_waves_protection_and_no_future_credit(self):
        for policy in ref.POLICIES:
            short=self.run_case([[0,1],[2,0]],policy)
            long=self.run_case([[0,1],[2,0],[2,1,0]],policy)
            self.assertEqual(short["events"],long["events"][:4])
        self.assertEqual([(e["slot"],e["generation"]) for e in short["events"] if e["expert"]==0],[(0,1),(0,1)])
        a=self.run_case([[0,1],[2,0]],"AdmitAll")
        self.assertEqual([e["slot"] for e in a["events"]],[0,1,1,0])
        b=self.run_case([[0,1,2,0,2]])
        self.assertEqual([e["wave"] for e in b["events"]],[1,1,2,2,2])
        self.assertEqual(b["state"]["history"],[1,2])

    def test_source_bound_catalog_cannot_alias(self):
        crossed=copy.deepcopy(self.base);crossed["class"]["metadata"]="a"*64
        for invalid in (crossed,dict(self.base,provenance_kind="authentic"),dict(self.base,extra=0),dict(self.base,calls=[[True]])):
            with self.assertRaises(ValueError):ref.parse(ref.json_bytes(invalid))
        for b in (b'{"schema":0,"schema":0}',b'{"x":NaN}',b'[]',b' '*((8<<20)+1)):
            with self.assertRaises(ValueError):ref.parse(b)
        with self.assertRaises(ValueError):ref.simulate(ref.json_bytes(self.base),"LFU")

    def test_observed_report_requires_every_occurrence_and_exact_identity(self):
        raw=ref.json_bytes(self.base);expected=ref.simulate(raw,"TwoHit")
        size=sum(self.base["class"]["components"])
        ledger=dict(modeled_transient_payload_bound=2*size,modeled_persistent_payload_bound=2*size,
                    catalog_bytes=32*len(self.base["catalog"]),parsed_input_bytes=452,history_capacity_bytes=128,
                    state_and_tickets_bytes=320,event_capacity_bytes=144,scratch_capacity_bytes=16384,report_capacity_bytes=ref.LIMIT)
        ledger["logical_total"]=sum(ledger.values())
        report=dict(expected,schema="pulsarmlx.admission-screen.report/1",provenance_kind="synthetic",policy="TwoHit",
                    source=self.base["class"],catalog=[e["binding"] for e in self.base["catalog"]],ledger=ledger)
        self.assertEqual(ref.verify_report(raw,"TwoHit",ref.json_bytes(report)),report)
        for key,change in [("events",report["events"][:-1]),("events",list(reversed(report["events"]))),
                           ("catalog",list(reversed(report["catalog"]))),("policy","AdmitAll"),
                           ("ledger",dict(ledger,logical_total=1))]:
            with self.assertRaises(ValueError):ref.verify_report(raw,"TwoHit",ref.json_bytes(dict(report,**{key:change})))
        with self.assertRaises(ValueError):ref.verify_report(raw,"TwoHit",b" "*(ref.LIMIT+1))

    def test_fixed_exhaustive_and_named_journals(self):
        expected=ref.golden()
        self.assertEqual(ref.json_bytes(expected)+b"\n",ref.read_fixture("expected.json"))
        self.assertEqual(expected["exhaustive"]["policy_runs"],4368)
        for name,want in [("win",(10,8)),("loss",(1,2)),("tie",(2,2))]:
            out=expected["case_reports"][name]
            self.assertEqual(tuple(out[p]["metrics"]["materializations"] for p in ref.POLICIES),want)
        fifo=expected["case_reports"]["fifo65"]["TwoHit"]["state"]
        self.assertEqual(fifo["counts"]["history_evictions"],2)
        self.assertEqual(fifo["slots"][0]["expert"],64)
        self.assertEqual(fifo["history"],list(range(2,64))+[0])


if __name__=="__main__":
    unittest.main()
