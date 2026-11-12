"""Physical calls and hash-only private originals are represented by isolated synthetic facts."""
import copy
from fractions import Fraction
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import f020_weighted_native_supervise as protocol
import f020_weighted_native_check as check
import f020_weighted_native_reference as ref
from f020_weighted_native_reference import r1,rational,sha,canonical

def save(p,v):
    p.write_bytes(canonical(v))


def output(words):
    return dict(dtype="F32",shape=[1,len(words)],bytes=4*len(words),f32_bits=words,sha256=sha(ref.dyadic.words(words)))


def stage_inputs(originals,profile,expert):
    source=originals.cases[profile,expert]
    g,u=([rational.rn32(x) for x in source[k][0]] for k in ("g","u"))
    z=[rational.rn32((lo+hi)/2) for lo,hi in source["h"][0]]
    down,_=r1.qmm([[r1.f32(w) for w in z]],source["down"])
    return list(map(output,(g,u,z,[rational.rn32(x) for x in down[0]])))


def occurrence(originals,profile,arm,position,ordinal,expert,w,stages):
    recipe=originals.recipes[profile];planes=recipe["planes"][expert]
    binding,size=check.resident.binding(recipe,expert)
    slot=[[0,1],[0,1],[1,1],[0,1],[1,1],[0,2],[0,3],[1,1],[0,3],[0,3],[1,2],[0,4]][ordinal] if arm=="cached" else None
    hashes=[p["sha256"] for p in planes]
    row=dict(position=position,ordinal=ordinal,weight_bits=w,expert=expert,recipe=profile,slot_generation=slot,status="weighted_after_retirement",
             binding=binding,component_sha256_before=hashes,component_sha256_after=hashes,staging_capacity=size+512,
             copies=dict(staging_components=9,staging_bytes=size,qmm_data_imports=12,qmm_metadata_widenings=6,projection_readbacks=3,
                         activation_input_imports=2,scalar_imports=2,activation_readbacks=3,down_host_reimport=1),
             cleanup=dict(live=0,double_free=0,errors=0,messages=0,freed=1,results=[1,1,0]))
    for i,k in enumerate(("gate","up","down")):
        n,dim=planes[i]["logical_shape"]
        row[k]=dict(bits=planes[i]["bits"],group_size=64,packed_weight_sha256=hashes[i][0],output=stages[[0,1,3][i]],
                    bound_gamma_n=r1.gamma_n(1,n,dim),device_facts_gpu=True,cpu_guard_checks=2,imports_before_decision=0,
                    numerical_before_decision=0,imports=4,numerical=2,active_cache_peak=[0,0,0])
    row["activation"]=dict(status=0,stats=[2,0,9,4,13,1,9,0],materializations=1,gate_clamp_bits=check.donor.clamp_bits(stages[0]["f32_bits"],"gate"),
                           up_clamp_bits=check.donor.clamp_bits(stages[1]["f32_bits"],"up"),output=stages[2],active_cache_peak=[0,0,0])
    row["down_admission"]=dict(actual_input_sha256=stages[2]["sha256"],decision="admitted",imports_before_decision=0,numerical_before_decision=0)
    return row


class SimulatedCampaign(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.originals=ref.Originals()
        cls.vectors={(p,e):stage_inputs(cls.originals,p,e) for p in ref.BOOKS for e in range(3)}

    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name).resolve()
        self.calls=0;self.children=0;self.fail_at=None;self.stop_child=None
        self.patch("host_facts",self.host)
        self.patch("source",lambda:dict(commit="a"*40,tree="b"*40,inventory_sha256="c"*64,file_count=5178))
        self.patch("links",lambda binary:["libmlx.dylib","libmlxc.dylib"])
        self.patch("installed",self.installation)
        self.patch("file_hash",self.file_hash)
        self.patch("wait_child",self.child)
        self.patch("emit_line",lambda data:setattr(self,"emitted",json.loads(data)))
        self.patch("fetch",self.fetch)
        state=self.root/"original";state.mkdir()
        prefix=self.root/"prefix";(prefix/"lib").mkdir(parents=True)
        for name in ("libmlx.dylib","libmlxc.dylib","mlx.metallib"):(prefix/"lib"/name).write_bytes(b"synthetic image")
        binary=self.root/"bin/release/qualify-weighted-mlp";binary.parent.mkdir(parents=True);binary.write_bytes(("synthetic; never execute "+protocol.binary_seal(protocol.modules())+" "+check.resident.ABI_STAMP).encode());binary.chmod(0o700)
        build=self.root/"build/receipt.json";build.parent.mkdir()
        self.cfg=self.root/"config.json";self.output=self.root/"campaign"
        self.claim=state/protocol.CLAIM;self.prior=state/protocol.old.CLAIM
        oldcfg=self.root/"original-config.json";oldout=self.root/"original-output";oldout.mkdir()
        save(oldcfg,dict(installation=str(state/"install"),output=str(oldout)))
        save(self.prior,dict(config=str(oldcfg),config_sha256=protocol.old.hashed(oldcfg)))
        self.oldresult=oldout/"result.json";save(self.oldresult,dict(status="accepted",claim_sha256=protocol.PREDECESSOR))
        self.hash_fixtures={self.prior:(self.prior.read_bytes(),protocol.PREDECESSOR),self.oldresult:(self.oldresult.read_bytes(),protocol.PREVIOUS_RESULT)}
        for n in ("install","freeze","diagnostic"):(state/n).write_text("synthetic")
        artifact=build.parent/"artifact.json"
        save(artifact,dict(reason="compiler-artifact",target=dict(kind=["bin"],name=binary.name,src_path=str(ref.ROOT/"crates/mlx-expert-mlp/src/bin/qualify-weighted-mlp.rs")),
            executable=str(binary),profile=dict(test=False,opt_level="3"),features=["weighted-native"],package_id="path+mock#mlx-expert-mlp"))
        save(build,dict(commit="a"*40,tree="b"*40,binary_sha256=protocol.old.hashed(binary),prefix=str(prefix),
                        artifact=str(artifact),artifact_sha256=protocol.old.hashed(artifact),verifier_modules=protocol.modules(),
                        reference=protocol.REFERENCE,accounting_abi_stamp=check.resident.ABI_STAMP,linkage=["libmlx.dylib","libmlxc.dylib"]))
        self.config=dict(repo=str(ref.ROOT),output=str(self.output),prefix=str(prefix),build=str(build),binary=str(binary),
                         installation=str(state/"install"),diagnostic_receipt=str(state/"diagnostic"),freeze=str(state/"freeze"))
        save(self.cfg,self.config);self.grant()

    def patch(self,key,value):
        obj=mock.patch.object(protocol,key,value);obj.start();self.addCleanup(obj.stop)

    def host(self):
        self.calls+=1
        return dict(protocol.HOST,os="wrong") if self.calls==self.fail_at else dict(protocol.HOST)

    def installation(self,c):
        native={k:sha(b"synthetic image") for k in ("libmlx","libmlxc","metallib")}
        files={}
        for n in ("libmlx.dylib","libmlxc.dylib"):
            path=str(Path(self.config["prefix"])/"lib"/n)
            files[n]=dict(lexical=path,canonical=path,sha256=native[n.split(".")[0]],mock_metadata="private marker")
        return dict(native,install_sha256=protocol.old.INSTALL,mlx_commit=protocol.old.PINS["mlx"],mlx_c_commit=protocol.old.PINS["mlx-c"],
                    static_runtime_sha256=protocol.old.runtime.RUNTIME_SHA256,static_inspection=dict(files=files))

    def file_hash(self,path):
        raw=path.read_bytes()
        if path in self.hash_fixtures and self.hash_fixtures[path][0]==raw:return self.hash_fixtures[path][1]
        return sha(raw)

    def grant(self):
        config=protocol.configuration(self.config)
        full=protocol.description(config,protocol.identity(config))
        _,self.envelope=protocol.binding(full)
        self.issue(self.envelope)
        self.calls=0

    def issue(self,envelope):
        self.markdown=b"approved synthetic control\n```weighted-mlp-grant\n"+protocol.old.compact_line(envelope)+b"```\n"
        self.config["operator"]=dict(commit="1"*40,path="Prompts/RUST-ENGINE/Mac-Studio-M1-Ultra/099__test__prompt.md",sha256=sha(self.markdown))
        save(self.cfg,self.config)

    def fetch(self,commit,name):
        return (sha(self.markdown)+"  "+Path(self.config["operator"]["path"]).name+"\n").encode() if name.endswith(".sha256") else self.markdown

    def child(self,cmd,env,directory,deadline,limit):
        self.assertEqual(limit,300);self.assertLessEqual(deadline-time.monotonic(),900)
        self.assertEqual(set(env),{"HOME","PATH","MLX_C_PREFIX","DYLD_LIBRARY_PATH","MLX_ENABLE_TF32","PYTHONDONTWRITEBYTECODE"})
        self.children+=1
        cap=protocol.doc(directory/"intent.json");p,a=cap["profile"],cap["arm"];ident=cap["identity"]
        pid=os.getppid();save(directory/"started.json",dict(pid=pid))
        (directory/"stdout.log").touch();(directory/"stderr.log").touch()
        obs=dict(images=protocol.expected_images(ident,self.config),binary=self.config["binary"],parent=os.getpid(),reference=protocol.REFERENCE,
                 abi=check.resident.ABI_STAMP,seal=ident["seal"],rustc="rustc 1.95.0 (59807616e 2026-04-14)",profile="release",mlx_commit=protocol.old.PINS["mlx"],
                 mlx_c_commit=protocol.old.PINS["mlx-c"],prefix=self.config["prefix"])
        admission=protocol.verify_child(directory/"intent.json",obs,protocol.modules(),emit=False)
        if self.stop_child==self.children:
            save(directory/"completed.json",dict(pid=pid,exit=1,reaped=True,timeout=False))
            raise ValueError("simulated child failure")
        self.make_arm(directory/"out",p,a,admission)
        save(directory/"completed.json",dict(pid=pid,exit=0,reaped=True,timeout=False))

    def make_arm(self,out,p,a,admission):
        out.mkdir()
        l=check.ledger(ref.ROOT,p,a,self.originals.recipes[p]);guards=[["initial",0]];steps=[];ordinal=0;size=0
        ids=self.originals.artifact["profiles"][p]["identity"]
        for i,plan in enumerate(ref.ROUTE):
            observed=[]
            for e,w in plan:
                row=occurrence(self.originals,p,a,i,ordinal,e,w,self.vectors[p,e]);data=canonical(row)
                (out/f"occ-{ordinal:02}.json").write_bytes(data);size+=len(data);ordinal+=1;guards.append(["retired",0])
                observed.append((e,row["down"]["output"]["f32_bits"]))
            guards.extend([["finish",0],["committed",0]])
            data=ref.dyadic.words(ref.local_bits(plan,observed));(out/f"weighted-{i}.f32").write_bytes(data);size+=len(data)
            snap=check.snapshot(i,a,l);counts=[8*ordinal,12*ordinal]
            steps.append(dict(position=i,request=f"weighted-v1.{ids['book']}.{i}.{ids['plans'][i]}",token=0,input_reads=i+1,counts=counts,
                snapshot=snap,peak=l["W_total"]+[1028,1544,1548,1552,1556][i],active=0,sha256=sha(data)))
            if i==0:replay=dict(same_commit=True,lost_delivery=True,position=1,input_reads=1,counts=counts,snapshot=snap,guard_count=4)
        save(out/"report.json",dict(schema="weighted-native-arm-v1",admission=admission,profile=p,arm=a,book=ids["book"],row_count=12,
            version="0.31.2",allocator=dict(previous_limit=0,cache_limit=0,initial_cache=0,initial_clear=0),failure=None,
            initial_counts=[0,0],steps=steps,replay=replay,final=snap,ledger=l,standing=l["W_total"],guards=guards,
            payload_before_report=size,harness=check.harness(l["W_total"]+1556)))

    def test_complete_source_only_population_and_eleven_admissions(self):
        protocol.launch(self.cfg)
        result=protocol.doc(self.output/"result.json")
        self.assertEqual(self.children,4);self.assertEqual(self.calls,11)
        self.assertEqual(result["coverage"]["WEIGHTED_LOCAL_BITS_V1"],2560)
        self.assertEqual(result["coverage"]["WEIGHTED_SOURCE_ENCLOSURE_V1"],2560)
        self.assertEqual(result["coverage"]["stage_pairs"],96);self.assertEqual(result["coverage"]["final_pairs"],10)
        self.assertEqual(result["claim_sha256"],protocol.old.hashed(self.claim))
        for n,h in result["evidence"].items():self.assertEqual(protocol.old.hashed(self.output/n),h)
        out=os.environ.get("WEIGHTED_CONTROL_EVIDENCE")
        if out:
            marker=dict(kind="synthetic external observations; original-source mathematical controls",coverage=result["coverage"],live_admissions=self.calls,
                gates=[protocol.doc(self.output/f"{i}-{p}-{a}/gates.json") for i,(p,a) in enumerate(ref.ARMS)])
            with Path(out).open("xb") as f:f.write(canonical(marker))
        with self.assertRaisesRegex(ValueError,"occupied"):protocol.launch(self.cfg)

    def test_postgrading_drift_preserves_completed_claim_without_accept(self):
        self.fail_at=11
        with self.assertRaisesRegex(ValueError,"host facts"):protocol.launch(self.cfg)
        self.assertTrue(self.claim.is_file());self.assertFalse((self.output/"result.json").exists());self.assertEqual(self.children,4)
        self.assertTrue((self.output/"3-mixed-cached/gates.json").is_file());self.assertTrue((self.output/"failure.json").is_file())

    def test_grant_protocol_and_immutable_predecessors(self):
        original=copy.deepcopy(self.envelope);v=copy.deepcopy(original);v["schema"]=protocol.old.DIGEST_SCHEMA
        with self.assertRaises(ValueError):protocol.validate(v)
        for changed in (self.markdown+self.markdown,self.markdown.replace(b"weighted-mlp-grant",b"resident-mlp-grant"),b"```text\n"+self.markdown,self.markdown.replace(b'"children":4',b'"children":true')):
            with self.assertRaises(ValueError):protocol.parse_fence(changed)
        for f in [self.prior,self.oldresult]:
            data=f.read_bytes();f.write_bytes(data+b" ")
            with self.assertRaises(ValueError):protocol.admit(self.config)
            f.write_bytes(data)
        previous=self.config["installation"];new=self.root/"other";new.mkdir();shutil.copy(previous,new/"install")
        shutil.copy(self.prior,new/protocol.old.CLAIM);self.config["installation"]=str(new/"install")
        with self.assertRaises(ValueError):protocol.admit(self.config)
        self.assertFalse(self.claim.exists())

    def test_private_field_changes_and_source_build_identity_refusals(self):
        with mock.patch.object(protocol,"installed",side_effect=lambda c:self.changed_native(c)):
            with self.assertRaisesRegex(ValueError,"complete private description"):protocol.admit(self.config)
        path=Path(self.config["build"]);orig=protocol.doc(path)
        for key in ["commit","tree","prefix","binary_sha256","reference","verifier_modules","accounting_abi_stamp","artifact_sha256","linkage"]:
            save(path,dict(orig,**{key:"mismatch"}))
            with self.assertRaises(ValueError,msg=key):protocol.admit(self.config)
        save(path,orig)
        with mock.patch.object(protocol.sys.modules["f020_weighted_native_rational"],"__file__",str(self.cfg)):
            with self.assertRaisesRegex(ValueError,"module origin"):protocol.modules()
        self.assertFalse(self.claim.exists())

    def changed_native(self,c):
        n=self.installation(c);n["static_inspection"]["files"]["libmlx.dylib"]["mock_metadata"]="changed private field";return n

    def test_fresh_durable_preparation_creates_no_claim_or_output(self):
        self.config.pop("operator");save(self.cfg,self.config);dest=self.root/"private.json"
        protocol.prepare(self.cfg,dest);raw=dest.read_bytes()
        self.assertEqual(self.emitted["description"]["sha256"],sha(raw));self.assertEqual(dest.stat().st_mode&0o777,0o600)
        self.assertEqual(self.emitted["description"]["bytes"],len(raw));self.assertIn(str(self.root).encode(),raw)
        self.assertNotIn(str(self.root).encode(),canonical(self.emitted));self.assertEqual(self.children,0)
        with self.assertRaises(ValueError):protocol.prepare(self.cfg,dest)
        self.assertFalse(self.claim.exists());self.assertFalse(self.output.exists())

    def test_first_child_failure_stops_and_spends(self):
        self.stop_child=1
        with self.assertRaisesRegex(ValueError,"child failure"):protocol.launch(self.cfg)
        self.assertEqual(self.children,1);self.assertTrue(self.claim.exists());self.assertFalse((self.output/"result.json").exists())
        self.config["output"]=str(self.root/"renamed");save(self.cfg,self.config)
        with self.assertRaisesRegex(ValueError,"occupied"):protocol.launch(self.cfg)

    def test_later_child_failure_stops_and_spends(self):
        self.stop_child=3
        with self.assertRaisesRegex(ValueError,"child failure"):protocol.launch(self.cfg)
        self.assertEqual(self.children,3);self.assertTrue(self.claim.exists());self.assertFalse((self.output/"result.json").exists())

    def test_preclaim_failure_and_result_race(self):
        self.fail_at=1
        with self.assertRaises(ValueError):protocol.launch(self.cfg)
        self.assertFalse(self.claim.exists());self.assertFalse(self.output.exists())
        self.fail_at=None;original=protocol.exclusive
        def raced(p,v):
            if p.name=="result.json":p.write_text("existing")
            return original(p,v)
        with mock.patch.object(protocol,"exclusive",raced):
            with self.assertRaises(FileExistsError):protocol.launch(self.cfg)
        self.assertEqual((self.output/"result.json").read_text(),"existing");self.assertTrue(self.claim.exists())

    def test_misbound_missing_or_tampered_records_refuse(self):
        p,a=ref.ARMS[1];i=protocol.identity(self.config)
        admission=protocol.receipt(i,p,a,"0"*64,protocol.expected_images(i,self.config));out=self.root/"test-arm"
        self.make_arm(out,p,a,admission)
        f=out/"occ-00.json";raw=f.read_bytes();row=protocol.doc(f)
        mutations=[("ordinal",True),("expert",2),("weight_bits",0),("slot_generation",[1,3]),("position",1),("recipe","mixed"),("binding","0"*64)]
        for key,value in mutations:
            save(f,dict(row,**{key:value}))
            with self.assertRaises(ValueError,msg=key):check.arm_output(out,p,a,i,admission,self.originals)
        for key in ["gate","activation","down","cleanup","copies"]:
            v=copy.deepcopy(row)
            if key=="cleanup":v[key]["live"]=1
            elif key=="copies":v[key]["qmm_data_imports"]=0
            else:v[key]["output"]["f32_bits"][0]^=1
            save(f,v)
            with self.assertRaises(ValueError,msg=key):check.arm_output(out,p,a,i,admission,self.originals)
        f.write_bytes(raw.replace(b'{"',b'{"ordinal":9,"',1))
        with self.assertRaises(ValueError):check.arm_output(out,p,a,i,admission,self.originals)
        f.unlink()
        with self.assertRaises(FileNotFoundError):check.arm_output(out,p,a,i,admission,self.originals)

    def test_numeric_primitive_refusal_with_self_consistent_stage_hash(self):
        p,a=ref.ARMS[0];ident=protocol.identity(self.config)
        cap=protocol.receipt(ident,p,a,"0"*64,protocol.expected_images(ident,self.config))
        out=self.root/"numeric-arm";self.make_arm(out,p,a,cap)
        f=out/"occ-00.json";row=protocol.doc(f)
        words=list(row["gate"]["output"]["f32_bits"]);words[0]=0x41000000
        row["gate"]["output"]=output(words)
        row["activation"]["gate_clamp_bits"]=check.donor.clamp_bits(words,"gate")
        save(f,row)
        with self.assertRaisesRegex(ValueError,"gate numerical"):
            check.arm_output(out,p,a,ident,cap,self.originals)

    def test_configuration_and_reference_identity_drift(self):
        before=copy.deepcopy(self.config)
        self.config["repo"]=str(self.root)
        with self.assertRaisesRegex(ValueError,"working source"):protocol.admit(self.config)
        self.config=before
        with mock.patch.object(protocol.ref,"FILE",self.cfg):
            with self.assertRaisesRegex(ValueError,"reference freeze"):protocol.admit(self.config)
        path=Path(self.config["binary"]);data=path.read_bytes();path.write_bytes(data+b"changed")
        with self.assertRaisesRegex(ValueError,"build source"):protocol.admit(self.config)
        self.assertFalse(self.claim.exists())

    def test_parent_and_child_live_admissions_refuse_private_drift(self):
        for pos in (2,3):
            with self.subTest(live_position=pos):
                self.fail_at=pos
                with self.assertRaisesRegex(ValueError,"host facts"):protocol.launch(self.cfg)
                self.assertTrue(self.claim.exists());self.assertFalse((self.output/"result.json").exists())
                if pos==2:
                    # Each synthetic campaign uses its own installation and spent claim.
                    self.doCleanups();self.setUp()

    def test_isolated_loader_verifies_every_helper_before_project_code(self):
        import subprocess
        script=Path(protocol.f020_weighted_native_bootstrap.__file__).read_text()
        prefix=script.split('if __name__ == "__main__":')[0]
        d=self.root/"modules";d.mkdir();marker=d/"unexpected"
        first=d/"f020_first.py";first.write_text("from pathlib import Path\nPath("+repr(str(marker))+").touch()")
        last=d/"f020_last.py";last.write_text("answer=7")
        args=["/usr/bin/python3","-I","-S","-B","-c",prefix+"\nverified_modules(Path(sys.argv[1]),json.loads(sys.argv[2]))",str(d)]
        env={"HOME":str(self.root),"PATH":"/usr/bin:/bin:/usr/sbin:/sbin"}
        good=[("f020_first",sha(first.read_bytes())),("f020_last",sha(last.read_bytes()))]
        bad=[good[0],("f020_last","0"*64)]
        def run(bindings,e):
            return subprocess.run(args+[json.dumps(bindings)],env=e,timeout=15,capture_output=True).returncode
        self.assertNotEqual(run(bad,env),0);self.assertFalse(marker.exists())
        self.assertNotEqual(run(good,dict(env,PYTHONPATH="synthetic")),0);self.assertFalse(marker.exists())
        self.assertEqual(run(good,env),0);self.assertTrue(marker.exists())

    def test_wait_timeout_kills_and_reaps_only_owned_cpu_child(self):
        arm=self.root/"wait";arm.mkdir()
        with self.assertRaisesRegex(ValueError,"timed out"):
            protocol.old.wait_child([sys.executable,"-I","-S","-B","-c","import time;time.sleep(30)"],{"PATH":"/usr/bin:/bin"},arm,time.monotonic()+3,0.2)
        completed=protocol.doc(arm/"completed.json")
        self.assertTrue(completed["timeout"] and completed["reaped"]);self.assertLess(completed["exit"],0)


if __name__=="__main__":
    unittest.main()
