"""Admission of one prospective weighted population. No native calls."""
import struct
from pathlib import Path

import f020_resident_mlp_check as resident
import f020_weighted_native_reference as ref
from f020_weighted_native_reference import require,sha
from f020_resident_mlp_check import donor,r1,memory,ROLES

SLOTS=((0,1),(0,1),(1,1),(0,1),(1,1),(0,2),(0,3),(1,1),(0,3),(0,3),(1,2),(0,4))
PEAK=(1028,1544,1548,1552,1556)
TOTAL=(1,3,6,9,12)
NATIVE=32<<20
HOST=1114112
HARNESS=2<<20


def equal(actual,expected,label):
    # Canonical JSON comparison also separates booleans, integers and decimal values.
    require(ref.canonical(actual)==ref.canonical(expected),label)


def ledger(repo,profile,arm,recipe):
    size=resident.binding(recipe,0)[1]
    m=resident.metadata_terms(repo,profile)["M"]
    cache=2*size+m+(1<<20)+(64<<10)
    allocating=arm=="allocating"
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
           ["allocating_tuple",size if allocating else 0],["allocating_metadata",m if allocating else 0],
           ["activation_path",2*path_bytes],["input_reader_and_pending_copy",1024],["readback_and_activation",32768],
           ["accumulator",512],["pending_demand_descriptors_and_ledger",32768+3*44],["retained_records",12*(32768+40)],
           ["live_record_tree_and_serialization",192<<10]]
    qmm=[]
    for plane in recipe["planes"][0]:
        n,k=plane["logical_shape"];packed=n*k*plane["bits"]//8;meta=4*n*(k//64)
        qmm.append(dict(packed=packed,metadata_raw=meta,metadata_f32=2*meta,input=4*k,output=4*n,bytes=packed+3*meta+4*(k+n)))
    native=dict(qmm=qmm,activation=1800,temporary_headroom=4<<20,bound=(4<<20)+max(p["bytes"] for p in qmm),envelope=NATIVE,cache_limit=0)
    host=sum(v for _,v in terms);require(host<=HOST and book<=65536,"host working capacity")
    return dict(S=size,M=m,W_cache=cache,H_weighted=HOST,N_native=NATIVE,W_total=cache+HOST+NATIVE,host_bound=host,
                parts=terms,saved_payload_ceiling=12*32768,prospective_native=native)


def snapshot(i,arm,ledger):
    n=TOTAL[i];cached=arm=="cached"
    return dict(cache_reads=(9,18,27,36,54)[i] if cached else 0,control_reads=0 if cached else 9*n,
                fills=(1,2,3,4,6)[i] if cached else 0,hits=(0,1,3,5,6)[i] if cached else 0,
                evictions=(0,0,1,2,4)[i] if cached else 0,consumed=n if cached else 0,
                occupied=(1 if i==0 else 2)*ledger["S"] if cached else 0,quarantined=False,
                records=n,dispatches=i+1,weighted=n,working_bytes=ledger["W_total"],pending=False,output=False)


def harness(peak):
    return dict(limit=HARNESS,admission_and_paths=128<<10,step_snapshots_and_guards=128<<10,
                report_tree_and_encoding=768<<10,verifier_and_provenance=384<<10,caller_output_clones=0,combined_bound=peak+HARNESS)


def arm_output(root,profile,arm,identity,admission,originals,observe=None):
    def read(name,limit):return ref.bounded(root/name,limit)
    raw=read("report.json",128<<10);report=ref.strict(raw)
    equal(sorted(report),sorted("schema admission profile arm book allocator version initial_counts steps replay row_count final ledger standing guards failure payload_before_report harness".split()),"arm report schema")
    equal([report[k] for k in ("schema","admission","profile","arm","book","version","row_count","failure")],
          ["weighted-native-arm-v1",admission,profile,arm,ref.BOOKS[profile],identity["version"],12,None],"arm authority")
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
    for i,plan in enumerate(ref.ROUTE):
        downs=[]
        for expert,weight in plan:
            name=f"occ-{ordinal:02}.json";names.add(name)
            if observe:observe(dict(stage="expert",ordinal=ordinal,position=i,started=True))
            data=read(name,32768);payload+=len(data);row=ref.strict(data)
            stage_vectors.append(check_occurrence(row,profile,arm,i,ordinal,expert,weight,originals))
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
        snap=snapshot(i,arm,l)
        equal(report["steps"][i],dict(position=i,request=f"weighted-v1.{ids['book']}.{i}.{ids['plans'][i]}",token=0,input_reads=i+1,
            counts=count,snapshot=snap,peak=l["W_total"]+PEAK[i],active=0,sha256=sha(data)),"ordered commit trace")
        if i==0:
            equal(report["replay"],dict(same_commit=True,lost_delivery=True,position=1,input_reads=1,counts=count,snapshot=snap,guard_count=4),"post-commit replay")
    equal(report["final"],snapshot(4,arm,l),"final cache")
    guards=report["guards"];phases=["initial"]
    for p in ref.ROUTE:phases+=["retired"]*len(p)+["finish","committed"]
    equal([p for p,w in guards],phases,"guard stages")
    word=guards[0][1]
    require(type(word) is int and 0<=word<1<<64 and not word & ((3<<22)|(1<<24)|3|0x9f00) and all(type(w) is int and w==word for _,w in guards),"FPCR stability")
    equal(report["payload_before_report"],payload,"arm payload")
    require(payload+len(raw)<=1<<20 and set(p.name for p in root.iterdir())==names,"closed arm files/size")
    return stage_vectors,final_words,gates


def compare(pop):
    equal(list(pop),list(ref.ARMS),"complete ordered arms")
    for profile in ref.BOOKS:
        a,c=(pop[profile,arm] for arm in ("allocating","cached"))
        require(a[:2]==c[:2],"ALLOCATING_CACHED_PARITY")
    return dict(occurrences=48,projections=144,activations=48,stage_pairs=96,final_pairs=10,weighted_vectors=20,
                WEIGHTED_LOCAL_BITS_V1=2560,WEIGHTED_SOURCE_ENCLOSURE_V1=2560)



def check_occurrence(row, profile, arm, position, index, expert, weight, reference):
    require(
        set(row)
        == set(
            "ordinal position weight_bits status expert recipe slot_generation binding component_sha256_before component_sha256_after staging_capacity copies cleanup gate up activation down down_admission".split()
        ),
        "closed occurrence schema",
    )
    def typed(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "device_facts_gpu":
                    require(child is True, "GPU fact")
                else:
                    typed(child)
        elif isinstance(value, list):
            for child in value:
                typed(child)
        else:
            require(value is None or type(value) in (str, int), "occurrence field type")
    typed(row)
    recipe = reference.recipes[profile]
    plan = recipe["planes"][expert]
    expected, size = resident.binding(recipe, expert)
    hashes = [p["sha256"] for p in plan]
    require(
        (row["ordinal"], row["position"], row["expert"], row["recipe"], row["weight_bits"],row["status"])
        == (index, position, expert, profile, weight,"weighted_after_retirement"),
        "occurrence identity",
    )
    require(
        "error" not in row
        and row["binding"] == expected
        and row["component_sha256_before"] == row["component_sha256_after"] == hashes,
        "selected tuple",
    )
    require(
        row["slot_generation"] == (list(SLOTS[index]) if arm == "cached" else None),
        "slot/generation",
    )
    require(
        size <= row["staging_capacity"] <= 65536
        and row["copies"]
        == dict(
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
        "copy ledger",
    )
    cleanup = row["cleanup"]
    equal(sorted(cleanup),sorted("live double_free errors messages freed results".split()),"cleanup keys")
    require(len(cleanup["results"])==3,"result census length")
    require(
        all(cleanup[k] == 0 for k in ("live", "double_free", "errors", "messages"))
        and cleanup["freed"] > 0
        and cleanup["results"][0] == cleanup["results"][1] > 0
        and cleanup["results"][2] == 0,
        "ownership retirement",
    )
    for i, role in enumerate(ROLES):
        stage = row[role]
        require(
            set(stage)
            == set(
                "bits group_size packed_weight_sha256 output bound_gamma_n device_facts_gpu cpu_guard_checks imports_before_decision numerical_before_decision imports numerical active_cache_peak".split()
            ),
            "closed projection budget",
        )
        n, k = plan[i]["logical_shape"]
        require(
            stage["bits"] == plan[i]["bits"]
            and stage["group_size"] == 64
            and stage["packed_weight_sha256"] == hashes[i][0]
            and stage["bound_gamma_n"] == r1.gamma_n(1, n, k),
            "stage recipe/gamma",
        )
        require(
            stage["device_facts_gpu"] is True
            and stage["cpu_guard_checks"] == 2
            and stage["imports_before_decision"]
            == stage["numerical_before_decision"]
            == 0
            and stage["imports"] == 4
            and stage["numerical"] > 0,
            "projection guards/imports",
        )
        memory(stage["active_cache_peak"])
    activation = row["activation"]
    require(
        activation["status"] == 0
        and activation["stats"][0] == 2
        and activation["stats"][2:] == [9, 4, 13, 1, 9, 0]
        and activation["materializations"] == 1,
        "activation ownership/materialization",
    )
    equal(sorted(activation),sorted("status stats materializations gate_clamp_bits up_clamp_bits output active_cache_peak".split()),"activation keys")
    memory(activation["active_cache_peak"])
    for stage_name in (*ROLES,"activation"):
        equal(sorted(row[stage_name]["output"]),sorted("dtype shape bytes sha256 f32_bits".split()),"tensor keys")
    obs = [
        donor.decoded_output(row[stage]["output"], [1, n])
        for stage, n in (("gate", 64), ("up", 64), ("activation", 64), ("down", 128))
    ]
    g, u, h, y = obs
    for role, v in (("gate", g), ("up", u)):
        require(
            all(abs(n) <= 16 for n in v[0])
            and activation[role + "_clamp_bits"]
            == donor.clamp_bits(row[role]["output"]["f32_bits"], role),
            "activation domain/clamps",
        )
    require(
        row["down_admission"]
        == dict(
            actual_input_sha256=activation["output"]["sha256"],
            decision="admitted",
            imports_before_decision=0,
            numerical_before_decision=0,
        ),
        "actual down input",
    )
    require(
        all(n == 0 or r1.F(1, 2**32) <= abs(n) <= 2**32 for n in h[0])
        and sum(map(abs, h[0])) <= 2**40,
        "down domain",
    )
    ref = reference.cases[profile, expert]
    local, bd = r1.qmm(h, ref["down"])
    for j in range(64):
        require(abs(g[0][j] - ref["g"][0][j]) <= ref["bg"][0][j], f"gate numerical at occurrence {index} coordinate {j}")
        require(abs(u[0][j] - ref["u"][0][j]) <= ref["bu"][0][j], f"up numerical at occurrence {index} coordinate {j}")
        require(
            r1.distance_pass(h[0][j], ref["h"][0][j], ref["bh"][0][j]),
            f"hidden numerical at occurrence {index} coordinate {j}",
        )
    for j in range(128):
        require(abs(y[0][j] - local[0][j]) <= bd[0][j], f"down-local numerical at occurrence {index} coordinate {j}")
        require(
            r1.distance_pass(
                y[0][j], ref["y"][0][j], bd[0][j] + ref["propagated"][0][j]
            ),
            f"end-to-end numerical at occurrence {index} coordinate {j}",
        )
    return tuple(
        struct.pack(
            "<" + "I" * len(row[k]["output"]["f32_bits"]), *row[k]["output"]["f32_bits"]
        )
        for k in ("gate", "up", "activation", "down")
    )
