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
import f020_staged_weighted_supervise as protocol
import f020_staged_weighted_check as check
import f020_weighted_native_check as original_checks
import f020_weighted_native_reference as ref
from f020_weighted_native_reference import r1,rational,sha,canonical

# Reuse the independent, source-derived row author, without importing its test case.
from f020_weighted_native_protocol_test import save, stage_inputs, occurrence, output

REAL_WAIT = protocol.wait_child

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
        binary=self.root/"bin/release/qualify-staged-weighted-mlp";binary.parent.mkdir(parents=True);binary.write_bytes(("synthetic; never execute "+protocol.binary_seal(protocol.modules())+" "+original_checks.resident.ABI_STAMP).encode());binary.chmod(0o700)
        build=self.root/"build/receipt.json";build.parent.mkdir()
        self.cfg=self.root/"config.json";self.output=self.root/"campaign"
        self.claim=state/protocol.CLAIM;self.prior=state/protocol.old.CLAIM
        oldcfg=self.root/"original-config.json";oldout=self.root/"original-output";oldout.mkdir()
        save(oldcfg,dict(installation=str(state/"install"),output=str(oldout)))
        save(self.prior,dict(config=str(oldcfg),config_sha256=protocol.old.hashed(oldcfg)))
        self.oldresult=oldout/"result.json";save(self.oldresult,dict(status="accepted",claim_sha256=protocol.PREDECESSOR))
        self.hash_fixtures={self.prior:(self.prior.read_bytes(),protocol.PREDECESSOR),self.oldresult:(self.oldresult.read_bytes(),protocol.PREVIOUS_RESULT)}
        self.m3claim=state/protocol.M3_CLAIM;m3cfg=self.root/"m3-config.json";m3out=self.root/"m3-output";m3out.mkdir()
        save(m3cfg,dict(installation=str(state/"install"),output=str(m3out)))
        save(self.m3claim,dict(config=str(m3cfg),config_sha256=protocol.old.hashed(m3cfg)))
        self.m3result=m3out/"result.json";save(self.m3result,dict(status="accepted",claim_sha256=protocol.M3_SPENT))
        self.hash_fixtures.update({self.m3claim:(self.m3claim.read_bytes(),protocol.M3_SPENT),self.m3result:(self.m3result.read_bytes(),protocol.M3_RESULT)})
        for n in ("install","freeze","diagnostic"):(state/n).write_text("synthetic")
        artifact=build.parent/"artifact.json"
        save(artifact,dict(reason="compiler-artifact",target=dict(kind=["bin"],name=binary.name,src_path=str(ref.ROOT/"crates/mlx-expert-mlp/src/bin/qualify-staged-weighted-mlp.rs")),
            executable=str(binary),profile=dict(test=False,opt_level="3"),features=["staged-weighted-native"],package_id="path+"+(ref.ROOT/"crates/mlx-expert-mlp").as_uri()+"#0.1.0"))
        save(build,dict(commit="a"*40,tree="b"*40,binary_sha256=protocol.old.hashed(binary),prefix=str(prefix),
                        artifact=str(artifact),artifact_sha256=protocol.old.hashed(artifact),verifier_modules=protocol.modules(),
                        compiled_source_sha256=sha(canonical(protocol.compiled_sources())),reference=protocol.REFERENCE,accounting_abi_stamp=original_checks.resident.ABI_STAMP,linkage=["libmlx.dylib","libmlxc.dylib"]))
        self.config=dict(private_description=str(self.root/"original-description.json"),repo=str(ref.ROOT),output=str(self.output),prefix=str(prefix),build=str(build),binary=str(binary),
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
        data,self.envelope=protocol.binding(full)
        private=Path(config["private_description"]);private.write_bytes(data);private.chmod(0o600)
        self.issue(self.envelope)
        self.calls=0

    def issue(self,envelope):
        self.markdown=b"approved synthetic control\n```staged-weighted-mlp-grant\n"+protocol.old.compact_line(envelope)+b"```\n"
        self.config["operator"]=dict(commit="1"*40,path="Prompts/RUST-ENGINE/Mac-Studio-M1-Ultra/099__test__prompt.md",sha256=sha(self.markdown))
        save(self.cfg,self.config)

    def fetch(self,commit,name):
        return (sha(self.markdown)+"  "+Path(self.config["operator"]["path"]).name+"\n").encode() if name.endswith(".sha256") else self.markdown

    def child(self,cmd,env,directory,deadline,limit):
        self.assertEqual(limit,300);self.assertLessEqual(deadline-time.monotonic(),900)
        self.assertEqual(set(env),{"HOME","PATH","MLX_C_PREFIX","DYLD_LIBRARY_PATH","MLX_ENABLE_TF32","PYTHONDONTWRITEBYTECODE"})
        self.children+=1
        cap=protocol.doc(directory/"staged-intent.json");p,a=cap["profile"],cap["arm"];ident=cap["identity"]
        pid=os.getppid();save(directory/"started.json",dict(pid=pid))
        (directory/"stdout.log").touch();(directory/"stderr.log").touch()
        obs=dict(images=protocol.expected_images(ident,self.config),binary=self.config["binary"],parent=os.getpid(),reference=protocol.REFERENCE,
                 abi=original_checks.resident.ABI_STAMP,seal=ident["seal"],rustc="rustc 1.95.0 (59807616e 2026-04-14)",profile="release",mlx_commit=protocol.old.PINS["mlx"],
                 mlx_c_commit=protocol.old.PINS["mlx-c"],prefix=self.config["prefix"])
        admission=protocol.verify_child(directory/"staged-intent.json",obs,protocol.modules(),emit=False)
        if self.stop_child==self.children:
            save(directory/"completed.json",dict(pid=pid,exit=1,reaped=True,timeout=False,group_gone=True,signal_error=None))
            raise ValueError("simulated child failure")
        self.make_arm(directory/"out",p,a,admission)
        save(directory/"completed.json",dict(pid=pid,exit=0,reaped=True,timeout=False,group_gone=True,signal_error=None))

    def make_arm(self,out,p,a,admission):
        out.mkdir()
        l=check.ledger(ref.ROOT,p,a,self.originals.recipes[p]);guards=[["initial",0]];steps=[];ordinal=0;size=0
        planned=check.schedule(p,self.originals.recipes[p])
        ids=self.originals.artifact["profiles"][p]["identity"]
        for i,plan in enumerate(ref.ROUTE):
            observed=[]
            for e,w in plan:
                row=occurrence(self.originals,p,"cached",i,ordinal,e,w,self.vectors[p,e]);data=canonical(row)
                (out/f"occ-{ordinal:02}.json").write_bytes(data);size+=len(data);ordinal+=1;guards.append(["retired",0])
                observed.append((e,row["down"]["output"]["f32_bits"]))
            guards.extend([["finish",0],["committed",0]])
            data=ref.dyadic.words(ref.local_bits(plan,observed));(out/f"weighted-{i}.f32").write_bytes(data);size+=len(data)
            tr=check.transport(i,a,ids["book"],f"weighted-v1.{ids['book']}.{i}.{ids['plans'][i]}",planned[i])
            data_tr=canonical(tr);(out/f"transport-{i}.json").write_bytes(data_tr);size+=len(data_tr)
            snap=check.snapshot(i,a,l,planned[i]);counts=[8*ordinal,12*ordinal]
            steps.append(dict(position=i,request=f"weighted-v1.{ids['book']}.{i}.{ids['plans'][i]}",token=0,input_reads=i+1,counts=counts,
                snapshot=snap,peak=l["W_total"]+[1028,1544,1548,1552,1556][i],active=0,sha256=sha(data)))
            if i==0:replay=dict(same_commit=True,lost_delivery=True,position=1,input_reads=1,counts=counts,snapshot=snap,guard_count=4)
        save(out/"report.json",dict(schema="staged-weighted-native-arm-v1",admission=admission,profile=p,arm=a,book=ids["book"],row_count=12,
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
        out=os.environ.get("STAGED_PROTOCOL_EXPORT")
        if out:
            marker=dict(kind="synthetic external observations; original-source mathematical controls",coverage=result["coverage"],live_admissions=self.calls,
                gates=[protocol.doc(self.output/f"{i}-{p}-{a}/gates.json") for i,(p,a) in enumerate(check.ARMS)])
            with (Path(out)/("mock-coverage-"+sys.version.split()[0]+".json")).open("xb") as f:f.write(canonical(marker))
        with self.assertRaisesRegex(ValueError,"occupied"):protocol.launch(self.cfg)

    def test_postgrading_drift_preserves_completed_claim_without_accept(self):
        self.fail_at=11
        with self.assertRaisesRegex(ValueError,"host facts"):protocol.launch(self.cfg)
        self.assertTrue(self.claim.is_file());self.assertFalse((self.output/"result.json").exists());self.assertEqual(self.children,4)
        self.assertTrue((self.output/"3-mixed-Overlap/gates.json").is_file());self.assertTrue((self.output/"failure.json").is_file())

    def test_grant_protocol_and_immutable_predecessors(self):
        original=copy.deepcopy(self.envelope);v=copy.deepcopy(original);v["schema"]=protocol.old.DIGEST_SCHEMA
        with self.assertRaises(ValueError):protocol.validate(v)
        for changed in (self.markdown+self.markdown,self.markdown.replace(b"staged-weighted-mlp-grant",b"resident-mlp-grant"),b"```text\n"+self.markdown,self.markdown.replace(b'"children":4',b'"children":true')):
            with self.assertRaises(ValueError):protocol.parse_fence(changed)
        for f in [self.prior,self.oldresult,self.m3claim,self.m3result]:
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
        for key in ["commit","tree","prefix","binary_sha256","reference","compiled_source_sha256","verifier_modules","accounting_abi_stamp","artifact_sha256","linkage"]:
            save(path,dict(orig,**{key:"mismatch"}))
            with self.assertRaises(ValueError,msg=key):protocol.admit(self.config)
        save(path,orig)
        with mock.patch.object(protocol.sys.modules["f020_weighted_native_rational"],"__file__",str(self.cfg)):
            with self.assertRaisesRegex(ValueError,"module origin"):protocol.modules()
        self.assertFalse(self.claim.exists())

    def changed_native(self,c):
        n=self.installation(c);n["static_inspection"]["files"]["libmlx.dylib"]["mock_metadata"]="changed private field";return n

    def test_fresh_durable_preparation_creates_no_claim_or_output(self):
        self.config.pop("operator");dest=Path(self.config["private_description"]);dest.unlink();save(self.cfg,self.config)
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
        p,a=check.ARMS[1];i=protocol.identity(self.config)
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
        p,a=check.ARMS[0];ident=protocol.identity(self.config)
        cap=protocol.receipt(ident,p,a,"0"*64,protocol.expected_images(ident,self.config))
        out=self.root/"numeric-arm";self.make_arm(out,p,a,cap)
        f=out/"occ-00.json";row=protocol.doc(f)
        words=list(row["gate"]["output"]["f32_bits"]);words[0]=0x41000000
        row["gate"]["output"]=output(words)
        row["activation"]["gate_clamp_bits"]=original_checks.donor.clamp_bits(words,"gate")
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
        script=Path(protocol.f020_staged_weighted_bootstrap.__file__).read_text()
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


    def test_transport_mutations_and_extra_file(self):
        profile,mode=check.ARMS[0];ident=protocol.identity(self.config)
        receipt=protocol.receipt(ident,profile,mode,"0"*64,protocol.expected_images(ident,self.config))
        out=self.root/"staged-arm";self.make_arm(out,profile,mode,receipt)
        def grade():check.arm_output(out,profile,mode,ident,receipt,self.originals)
        f=out/"transport-0.json";row=protocol.doc(f)
        for field in ("copied_bytes","requested_bytes","attempted_reads","joined"):
            changed=copy.deepcopy(row);changed["activity"][field]-=1;save(f,changed)
            with self.assertRaisesRegex(ValueError,"transport"):grade()
        for field in ("generation","wave","invocation","expert"):
            changed=copy.deepcopy(row);changed["tickets"][0][field]+=1;save(f,changed)
            with self.assertRaisesRegex(ValueError,"transport"):grade()
        save(f,dict(row,mode="Overlap"))
        with self.assertRaisesRegex(ValueError,"transport"):grade()
        save(f,row);(out/"unexpected").touch()
        with self.assertRaisesRegex(ValueError,"closed arm"):grade()

    def test_independent_coordinate_refusals(self):
        p="default";i=0;route=ref.ROUTE[i];down=[(0,self.vectors[p,0][3]["f32_bits"])]
        words=ref.local_bits(route,down);fixed=copy.deepcopy(self.originals.artifact["profiles"][p]["endpoints"][i])
        wrong=words.copy();wrong[13]^=1
        with self.assertRaisesRegex(ValueError,"WEIGHTED_LOCAL_BITS_V1"):ref.weighted_gates(route,down,wrong,fixed)
        fixed[13]=[0x40000000,0x40000000]
        with self.assertRaisesRegex(ValueError,"WEIGHTED_SOURCE_ENCLOSURE_V1"):ref.weighted_gates(route,down,words,fixed)

    def test_original_description_bytes_and_occupied_output(self):
        f=Path(self.config["private_description"]);b=f.read_bytes()
        f.write_bytes(b+b" ")
        with self.assertRaisesRegex(ValueError,"description bytes"):protocol.launch(self.cfg)
        self.assertFalse(self.claim.exists());f.write_bytes(b);f.chmod(0o644)
        with self.assertRaisesRegex(ValueError,"custody"):protocol.launch(self.cfg)
        f.chmod(0o600);self.output.mkdir()
        with self.assertRaisesRegex(ValueError,"occupied"):protocol.launch(self.cfg)
        self.assertFalse(self.claim.exists())

    def test_malformed_startup_keeps_claim(self):
        def malformed(cmd,env,directory,deadline,limit):
            self.children+=1
            cap=protocol.doc(directory/"staged-intent.json")
            protocol.verify_child(directory/"staged-intent.json",dict(parent=os.getpid(),images={}),protocol.modules(),emit=False)
        with mock.patch.object(protocol,"wait_child",malformed),self.assertRaises(ValueError):
            protocol.launch(self.cfg)
        self.assertEqual(self.children,1);self.assertTrue(self.claim.exists())
        self.assertFalse((self.output/"grading-intent.json").exists())

    def test_owned_cleanup_observations(self):
        import subprocess
        for kind in ("timeout","signal","unreaped","exit"):
            directory=self.root/kind;directory.mkdir()
            child=mock.Mock(pid=115);child.poll.return_value=None
            child.wait.side_effect=[1,1] if kind=="exit" else [subprocess.TimeoutExpired("mock",300),
                subprocess.TimeoutExpired("mock",5) if kind=="unreaped" else -9]
            signal_failure=PermissionError("mock signal refused") if kind=="signal" else None
            # The fake process group disappears only for the purpose of group lookup.
            with mock.patch.object(protocol,"spawn_child",return_value=child),mock.patch.object(protocol.os,"killpg",side_effect=signal_failure) as kill, mock.patch.object(protocol,"group_gone",return_value=True):
                with self.assertRaisesRegex(ValueError,"failed"):REAL_WAIT(["mock"],{},directory,time.monotonic()+300,300)
            kill.assert_called_once_with(115,protocol.signal.SIGKILL)
            d=protocol.doc(directory/"completed.json");self.assertEqual(d["reaped"],kind!="unreaped")
            self.assertEqual(d["timeout"],kind!="exit");self.assertEqual(d["signal_error"] is not None,kind=="signal")
            self.assertTrue(all(0<=c.kwargs["timeout"]<=300 for c in child.wait.call_args_list))

    def test_integer_and_source_bounds(self):
        with self.assertRaisesRegex(ValueError,"overflow"):check.checked_sum((1<<64)-1,1)
        for path,b in zip(protocol.SEAMS,protocol.expected_seams()):
            self.assertEqual((ref.ROOT/path).read_bytes(),b)
        with self.assertRaisesRegex(ValueError,"bounded regular file"):protocol.old.raw(Path(self.config["private_description"]),1)

    def test_closed_imports_and_bound_envelope_families(self):
        fake=self.root/"forged.py";fake.write_text("def checked_sum(*v):return 0")
        ns={"__name__":"f020_resident_mlp_check"};exec(compile(fake.read_bytes(),str(fake),"exec"),ns)
        with mock.patch.object(check,"checked_sum",ns["checked_sum"]),self.assertRaisesRegex(ValueError,"helper origin"):
            protocol.modules()
        for key in ("schema","source","description","reference","config_binding","arms","budget","binary_sha256","build_sha256"):
            changed=copy.deepcopy(self.envelope)
            if key=="arms":changed[key]=list(reversed(changed[key]))
            elif key=="description":changed[key]["sha256"]="0"*64
            elif key=="source":changed[key]["tree"]="0"*40
            elif key=="budget":changed[key]["retries"]=1
            else:changed[key]="0"*64
            self.issue(changed)
            with self.assertRaises(ValueError,msg=key):protocol.launch(self.cfg)
            self.assertFalse(self.claim.exists())

    def test_unresolved_mock_child_stops_before_grading(self):
        import subprocess
        child=mock.Mock(pid=915);child.poll.return_value=None
        child.wait.side_effect=subprocess.TimeoutExpired("mock",5)
        with mock.patch.object(protocol,"wait_child",REAL_WAIT),mock.patch.object(protocol,"spawn_child",return_value=child) as starts, mock.patch.object(protocol.os,"killpg",side_effect=PermissionError("mock")),mock.patch.object(protocol,"group_gone",return_value=True):
            with self.assertRaisesRegex(ValueError,"cleanup uncertain"):protocol.launch(self.cfg)
        self.assertTrue(self.claim.exists());self.assertEqual(starts.call_count,1)
        self.assertFalse((self.output/"grading-intent.json").exists())
        row=protocol.doc(self.output/"0-default-Serial"/"completed.json")
        self.assertFalse(row["reaped"]);self.assertEqual(row["signal_error"],"PermissionError")

    def test_protocol_size_boundaries_refuse_before_claim(self):
        with self.assertRaisesRegex(ValueError,"intent size"):
            protocol.intent_record(self.cfg,self.claim,"0"*64,{"excess":"a"*65536},1,"default","Serial")
        full=protocol.description(self.config,protocol.identity(self.config))
        full["identity"]["excess"]="b"*(1<<20)
        with self.assertRaisesRegex(ValueError,"exceeds"):protocol.binding(full)
        for name,bound in (("intent",65536),("row",32768),("transport",128<<10),("log",8<<20)):
            f=self.root/("oversized-"+name)
            with f.open("wb") as stream:stream.truncate(bound+1)
            with self.assertRaisesRegex(ValueError,"bounded regular file"):protocol.old.raw(f,bound)
        self.assertFalse(self.claim.exists())
