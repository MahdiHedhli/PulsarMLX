"""Independent transport accounting and admission of original staged occurrence rows."""
import struct

import f020_admission_screen_reference_v1 as model
import f020_weighted_native_check as occurrence
import f020_weighted_native_reference as ref
from f020_resident_mlp_check import checked_sum
from f020_weighted_native_check import equal, harness, PEAK, ROLES, HOST, NATIVE, resident
from f020_weighted_native_reference import require, sha

ARMS = tuple((p, mode) for p in ("default", "mixed") for mode in ("Serial", "Overlap"))
TRANSPORT = 1 << 20
ROW = 128 << 10
def ledger(repo,profile,arm,recipe):
    size=resident.binding(recipe,0)[1]
    m=resident.metadata_terms(repo,profile)["M"]
    cache=2*size+m+(1<<20)+(64<<10)
    require((profile,arm) in ARMS, "staged profile and mode")
    path_bytes=len(str(repo/"fixtures/expert-mlp-composition/inputs").encode())
    def align(n):return (n+7)//8*8
    # Original Darwin arm64 rustc ABI. Vec growth starts at the length of the domain tag.
    book_struct=align(16+3*32+9*4)+24+48+16+8
    enc=used=len(b"weighted-book-v1\0")
    chunks=[4,len(profile),4,len(b"binary32-rne-mul-then-add-v1"),32,32,32]+[4]*10
    for plan in ref.ROUTE:
        chunks.extend([4,len(b"weighted-plan-v1\0")+4+8*len(plan)])
    for n in chunks:
        used+=n
        if used>enc:enc=max(2*enc,used)
    book=book_struct+enc+64+len("weighted-route-v1.")+64+64+5*(40+64)+12*8
    population=align(16+3*24+12+32+27*32+27*16)+len(recipe["name"])+2*64
    terms=[["route_book_and_encoding",book],["population",population],["staging_tuple_with_descriptors",65536],

           ["activation_path",2*path_bytes],["input_reader_and_pending_copy",1024],["readback_and_activation",32768],
           ["accumulator",512],["pending_demand_descriptors_and_ledger",32768+3*44],["retained_records",12*(32768+40)],
           ["live_record_tree_and_serialization",192<<10]]
    qmm=[]
    for plane in recipe["planes"][0]:
        n,k=plane["logical_shape"];packed=n*k*plane["bits"]//8;meta=4*n*(k//64)
        qmm.append(dict(packed=packed,metadata_raw=meta,metadata_f32=2*meta,input=4*k,output=4*n,bytes=packed+3*meta+4*(k+n)))
    native=dict(qmm=qmm,activation=1800,temporary_headroom=4<<20,bound=(4<<20)+max(p["bytes"] for p in qmm),envelope=NATIVE,cache_limit=0)
    host=sum(v for _,v in terms);require(host<=HOST and book<=65536,"host working capacity")
    capacities = [[r["len"] for r in plane["ranges"]] for plane in recipe["planes"][0]]
    names = max(len(n.encode()) for n in [recipe["name"], "model.safetensors"]+[v["module"] for v in recipe["planes"][0]])
    names_bound = 65536 + 96*(names+32)
    # Rust022 Darwin arm64 completion/ticket layout and event ABI, under the frozen toolchain.
    fixed = 84608
    events = 2048*72
    pipeline = dict(tuple_bytes=size, metadata_bytes=m, cache_bytes=cache, staging_bytes=2*size,
                    control_bytes=2<<20, stack_bytes=2<<20, total=checked_sum(cache,2*size,4<<20),
                    component_capacities=capacities,names_and_plans=names_bound,channels_and_fixed=fixed,
                    events_bytes=events,live_report_limit=1<<20,control_required=checked_sum(names_bound,fixed,events,1<<20))
    transport = [["retained",5*(ROW+24)+8],["live_tree",256<<10],["bookkeeping",64<<10]]
    transport_bound=checked_sum(*(v for _,v in transport))
    require(transport_bound<=TRANSPORT and pipeline["control_required"]<=2<<20,"capacity proof")
    return dict(pipeline=pipeline, W_pipeline=pipeline["total"], H_transport=TRANSPORT,transport_row_bytes=ROW,transport_slots=5,
                transport_bound=transport_bound,transport_parts=transport,S=size,M=m,W_cache=cache,H_weighted=HOST,N_native=NATIVE,W_total=checked_sum(pipeline["total"],HOST,TRANSPORT,NATIVE),host_bound=host,
                parts=terms,saved_payload_ceiling=12*32768,prospective_native=native)



def schedule(profile, recipe):
    """Derive demand tickets and resident generations from independent AdmitAll prefixes."""
    template = model.parse(model.read_fixture("template.json"))
    planes = recipe["planes"][0]
    layout = dict(template["class"],content=recipe["content"],metadata=recipe["metadata"],
                  bits=[v["bits"] for v in planes],components=[r["len"] for v in planes for r in v["ranges"]])
    bindings = [resident.binding(recipe,e)[0] for e in range(3)]
    template.update({"class":layout,"catalog":[dict(expert=e, domain=model.domain(layout), binding=b) for e,b in enumerate(bindings)]})
    calls=[]; steps=[]; generations=[0,0]; issued=0
    for i, plan in enumerate(ref.ROUTE):
        calls.append([e for e,_ in plan])
        result=model.simulate(model.json_bytes(dict(template,calls=calls)),"AdmitAll")
        events=[e for e in result["events"] if e["call"]==i]
        tickets=[]
        for wave,serial in enumerate(dict.fromkeys(e["wave"] for e in events)):
            misses=[e["expert"] for e in events if e["wave"]==serial and e["category"]=="M"]
            if misses: issued+=1
            for bank,_ in enumerate(misses):generations[bank]+=1
            for phase in ("submit","returned","validated","installed"):
                for bank,expert in enumerate(misses):
                    tickets.append(dict(phase=phase,invocation=i+1,wave=wave,bank=bank,generation=generations[bank],
                                        expert=expert,binding=list(bytes.fromhex(bindings[expert]))))
        counts=result["state"]["counts"]; metrics=result["metrics"];fills=metrics["materializations"]
        activity=dict(spawned=i+1,joined=i+1,requests=issued,completions=issued,cancelled_jobs=0,verified_roles=3*fills,
                      verified_components=9*fills,verified_bytes=metrics["issued_bytes"],copy_operations=9*fills,copied_bytes=metrics["issued_bytes"],
                      attempted_reads=9*fills,requested_bytes=metrics["issued_bytes"],discarded_issued_bytes=0,
                      request_high_water=1,completion_high_water=1,outstanding=False,banks_home=True)
        slots=[None if v is None else [v["expert"],v["generation"],v["recency"]] for v in result["state"]["slots"]]
        steps.append(dict(tickets=tickets,residents=slots,activity=activity,hits=metrics["read_avoidance_hits"],fills=fills,
                          evictions=counts["persistent_evictions"],consumed=counts["occurrences"]))
    return steps

def transport(i,mode,book,request,step):
    return dict(schema="staged-weighted-transport/1",position=i,mode=mode,book=book,request=request,
                reader_distinct=True,**{k:step[k] for k in ("tickets","activity","residents")})

def snapshot(i,arm,l,step):
    return dict(cache_reads=step["activity"]["attempted_reads"],mode=arm,activity=step["activity"],transport_records=i+1,
                occupied=l["S"]*sum(v is not None for v in step["residents"]),quarantined=False,
                dispatches=i+1,weighted=step["consumed"],records=step["consumed"],pending=False,output=False,working_bytes=l["W_total"],
                **{k:step[k] for k in ("hits","fills","evictions","consumed")})
def arm_output(root,profile,arm,identity,admission,originals,observe=None):
    require((profile,arm) in ARMS,"staged cached transport mapping")
    def read(name,limit):return ref.bounded(root/name,limit)
    raw=read("report.json",128<<10);report=ref.strict(raw)
    equal(sorted(report),sorted("schema admission profile arm book allocator version initial_counts steps replay row_count final ledger standing guards failure payload_before_report harness".split()),"arm report schema")
    equal([report[k] for k in ("schema","admission","profile","arm","book","version","row_count","failure")],
          ["staged-weighted-native-arm-v1",admission,profile,arm,ref.BOOKS[profile],identity["version"],12,None],"arm authority")
    equal(sorted(report["allocator"]),sorted("previous_limit initial_cache cache_limit initial_clear".split()),"allocator shape")
    require(type(report["allocator"]["previous_limit"]) is int and report["allocator"]["previous_limit"]>=0,"previous cache limit")
    equal([report["allocator"][k] for k in ("initial_cache","initial_clear","cache_limit")],[0]*3,"allocator initialization")
    recipe=originals.recipes[profile];l=ledger(ref.ROOT,profile,arm,recipe)
    equal(report["ledger"],l,"weighted ledger")
    equal(report["standing"],l["W_total"],"single charge")
    equal(report["harness"],harness(l["W_total"]+PEAK[-1]),"outer harness")
    require(len(report["steps"])==5,"weighted step count")
    equal(report["initial_counts"],[0,0],"initial native work")
    count=[0,0];ordinal=0;payload=0;stage_vectors=[];final_words=[];gates=[]
    names={"report.json"}
    planned=schedule(profile,recipe)
    ids=originals.artifact["profiles"][profile]["identity"]
    for i,plan in enumerate(ref.ROUTE):
        request=f"weighted-v1.{ids['book']}.{i}.{ids['plans'][i]}"
        name=f"transport-{i}.json";names.add(name);data=read(name,ROW);payload+=len(data)
        equal(ref.strict(data),transport(i,arm,ids["book"],request,planned[i]),"staged transport identity/ledger")
        downs=[]
        for expert,weight in plan:
            name=f"occ-{ordinal:02}.json";names.add(name)
            if observe:observe(dict(stage="expert",ordinal=ordinal,position=i,started=True))
            data=read(name,32768);payload+=len(data);row=ref.strict(data)
            stage_vectors.append(occurrence.check_occurrence(row,profile,"cached",i,ordinal,expert,weight,originals))
            if observe:observe(dict(stage="expert",ordinal=ordinal,position=i,passed=True,sha256=sha(data),counts=[64,64,64,128,128]))
            downs.append((expert,row["down"]["output"]["f32_bits"]))
            # Copied::retire synchronizes once explicitly and NativeContext::drop
            # synchronizes once more. Both calls increment the same FFI counter.
            count[0] += sum(row[role]["numerical"] for role in ROLES) + 2
            count[1] += sum(row[role]["imports"] for role in ROLES)
            ordinal+=1
        name=f"weighted-{i}.f32";names.add(name);data=read(name,512);payload+=len(data)
        words=list(struct.unpack("<128I",data))
        fixed=originals.artifact["profiles"][profile]["endpoints"][i]
        if observe:observe(dict(stage="weighted",position=i,started=True))
        expected=ref.weighted_gates(plan,downs,words,fixed)
        if observe:observe(dict(stage="weighted",position=i,passed=True,local=128,enclosure=128,expected_sha256=sha(ref.dyadic.words(expected))))
        gates.append(dict(position=i,expert_predicates=len(plan),local_expected=expected,source_interval_sha256=sha(ref.canonical(fixed)),coordinates=128))
        final_words.append(data)
        ids=originals.artifact["profiles"][profile]["identity"]
        snap=snapshot(i,arm,l,planned[i])
        equal(report["steps"][i],dict(position=i,request=f"weighted-v1.{ids['book']}.{i}.{ids['plans'][i]}",token=0,input_reads=i+1,
            counts=count,snapshot=snap,peak=l["W_total"]+PEAK[i],active=0,sha256=sha(data)),"ordered commit trace")
        if i==0:
            equal(report["replay"],dict(same_commit=True,lost_delivery=True,position=1,input_reads=1,counts=count,snapshot=snap,guard_count=4),"post-commit replay")
    equal(report["final"],snapshot(4,arm,l,planned[4]),"final cache")
    guards=report["guards"];phases=["initial"]
    for p in ref.ROUTE:phases+=["retired"]*len(p)+["finish","committed"]
    equal([p for p,w in guards],phases,"guard stages")
    word=guards[0][1]
    require(type(word) is int and 0<=word<1<<64 and not word & ((3<<22)|(1<<24)|3|0x9f00) and all(type(w) is int and w==word for _,w in guards),"FPCR stability")
    equal(report["payload_before_report"],payload,"arm payload")
    require(payload+len(raw)<=2<<20 and set(p.name for p in root.iterdir())==names,"closed arm files/size")
    return stage_vectors,final_words,gates


def compare(pop):
    equal(list(pop),list(ARMS),"complete ordered arms")
    for profile in ref.BOOKS:
        a,c=(pop[profile,arm] for arm in ("Serial","Overlap"))
        require(a[:2]==c[:2],"STAGED_SERIAL_OVERLAP_PARITY")
    return dict(occurrences=48,projections=144,activations=48,stage_pairs=96,final_pairs=10,weighted_vectors=20,
                WEIGHTED_LOCAL_BITS_V1=2560,WEIGHTED_SOURCE_ENCLOSURE_V1=2560)
