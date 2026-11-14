"""Check fixed-policy host evidence against the frozen route, file geometry and dyadic fixture."""
import argparse
import hashlib
import itertools
import json
import os
import struct
from pathlib import Path

import f020_read_policy_reference as windows
import f020_staged_weighted_check as staged
import f020_weighted_mlp_reference as dyadic
from f020_weighted_native_check import equal, resident
from f020_weighted_native_reference import bounded, require, sha, strict

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "docs/research/f020/m4c-staged-policy-host/matrix.json"
VIEW = ROOT / "fixtures/resident-expert-mlp"
ROLES = ("gate", "up", "down")
PROFILES = ("default", "mixed")
MODES = ("Serial", "Overlap")
POLICIES = ("BufferedRequested", "NoCacheRequested")
ARM_LIMIT = 2 << 20
ROLE_LIMIT = 32768
JOURNAL_SLOT = 9 * (ROLE_LIMIT + 4096) + 1024


def compact(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False).encode()


def read_json(path, limit):
    return strict(bounded(path, limit))


def fields(value, names):
    return {key: value[key] for key in names.split()}


def shard_stamp(path):
    st = path.stat()
    mt, mn = divmod(st.st_mtime_ns, 10**9)
    ct, cn = divmod(st.st_ctime_ns, 10**9)
    raw = struct.pack("<QQQqqqq", st.st_dev, st.st_ino, st.st_size, mt, mn, ct, cn)
    return hashlib.sha256(b"buffered-window-descriptor/1" + raw).digest()


def plan_bytes(recipe, expert):
    """Serialize the admitted plan from the indexed fixture in the declared field order."""
    root = VIEW / recipe["name"]
    payload = bounded(root / "model.safetensors", 1 << 20)
    metadata = sum((root / n).stat().st_size for n in ("config.json", "model.safetensors.index.json"))
    metadata += 8 + int.from_bytes(payload[:8], "little")
    planes = []
    for role, p in zip(ROLES, recipe["planes"][expert]):
        planes.append(dict(role=role, module=p["module"], expert=expert, bits=p["bits"],
                           group_size=p["group_size"], resolved_from="override" if p["bits"] == 8 else "default",
                           metadata_dtype="BF16", logical_shape=p["logical_shape"],
                           ranges=[fields(r, "tensor shard begin len") for r in p["ranges"]]))
    request = dict(modules=[p["module"] for p in planes], expert=expert, experts=3, d=128, h=64,
                   bits=[p["bits"] for p in planes], group_size=64)
    return compact(dict(schema="pulsarmlx.bounded-expert-plan/1", checkpoint=recipe["name"],
                        metadata_snapshot_sha256=recipe["metadata"], metadata_bytes_read=metadata,
                        request=request, planes=planes,
                        selected_bytes=sum(r["len"] for p in planes for r in p["ranges"]),
                        identity_scope="metadata snapshot and selected ranges only; no whole-checkpoint payload identity"))


def geometry(recipe, expert, role, policy, page):
    plane = recipe["planes"][expert][role]
    paths = [VIEW / recipe["name"] / r["shard"] for r in plane["ranges"]]
    # Setup deduplicates held file objects. The fixture has one object per admitted shard name.
    shards = list(dict.fromkeys(paths))
    lengths = {p.name: p.stat().st_size for p in shards}
    routes = windows.routes(plane["ranges"], lengths, page, policy)
    stamps = [shard_stamp(p) for p in paths]
    binding = hashlib.sha256(b"pulsarmlx.buffered-window-plan/1" + plan_bytes(recipe, expert)
                             + bytes([role]) + struct.pack("<Q", page) + b"".join(stamps)).digest()
    return dict(components=routes, stamps=[list(s) for s in stamps], binding=list(binding),
                lengths=[lengths[p.name] for p in paths], mapping=[shards.index(p) for p in paths],
                descriptors=len(shards))


def totals(components):
    logical = sum(c["logical_bytes"] for c in components)
    requested = sum(c["bytes"] for c in components)
    bounced = [c for c in components if c["route"] != "buffered-edge-exact"]
    return [logical, requested, requested - logical, len(components) - len(bounced),
            len(bounced), sum(c["logical_bytes"] for c in bounced)]


def frozen_inputs():
    matrix = read_json(MATRIX, 1 << 20)
    for name, digest in matrix["fixture_sha256"].items():
        equal(sha(bounded(ROOT / name, 1 << 20)), digest, name)
    equal([matrix["profiles"], matrix["modes"], matrix["fixed_policies"]],
          [list(PROFILES), list(MODES), list(POLICIES)], "arm population")
    routes = read_json(ROOT / "fixtures/weighted-expert-mlp/routes.json", 1 << 20)
    equal(routes["routes"], matrix["expert_weight_bits"], "frozen ordered terms")
    golden = dyadic.report(routes)
    equal(golden, read_json(ROOT / "fixtures/weighted-expert-mlp/expected.json", 1 << 20), "dyadic fixture")
    recipes = read_json(VIEW / "manifest.json", 1 << 20)["recipes"]
    return matrix, golden, recipes


def schedule_and_geometry(matrix, profile, recipe, page, policy):
    schedule = staged.schedule(profile, recipe)
    layout = {(e, i): geometry(recipe, e, i, policy, page) for e in range(3) for i in range(3)}
    largest = max(w["bytes"] for g in layout.values() for w in g["components"])
    count = matrix["cumulative"]
    all_components = []
    descriptors = 0
    for i, s in enumerate(schedule):
        tickets = [t for t in s["tickets"] if t["phase"] == "submit"]
        equal([[t[k] for k in matrix["miss_ticket_fields"]] for t in tickets], matrix["miss_tickets"][i], "miss schedule")
        equal([s[k] for k in ("fills", "hits", "evictions", "consumed")],
              [count[k][i] for k in ("fills", "hits", "evictions", "occurrences")], "cache counts")
        equal(s["residents"], matrix["residents"][i], "resident slots")
        for t in tickets:
            for role in range(3):
                g = layout[t["expert"], role]
                all_components.extend(g["components"])
                descriptors += g["descriptors"]
        equal(totals(all_components), matrix["cumulative_by_page"][str(page)][profile][i], "frozen byte totals")
        equal(descriptors, count["fresh_opens"][i], "distinct role descriptor count")
    return schedule, layout, largest + page - 1


def check_role(row, stamp, role, g, profile, policy, page, backing, position):
    label = f"{profile}/{policy} position {position} expert {stamp['expert']} {ROLES[role]}"
    identity = fields(stamp, "invocation wave bank generation expert binding")
    equal(fields(row, "invocation wave bank generation expert binding"), identity, label + " ticket binding")
    equal([row["role"], row["epoch"], row["verified"], row["primary_phase"]],
          [ROLES[role], 2 * position + 1, True, None], label + " verified")
    require(type(row["owner"]) is int and row["owner"] > 0, "owner identity")
    outcome = row["outcome"]
    equal([outcome["kind"], outcome["retired_live"], outcome["retired_released"], outcome["kernel_close_observed"]],
          ["transfer", 0, g["descriptors"], None], label + " descriptor release")
    r = outcome["receipt"]
    require(len(compact(r)) <= ROLE_LIMIT and len(compact(row)) <= ROLE_LIMIT + 4096, label + " record bounds")
    s = r["setup"]
    equal(fields(s, "policy role binding original_stamps lengths alignment page_size map live released kernel_close_observed"),
          dict(policy=policy, role=ROLES[role], binding=g["binding"], original_stamps=g["stamps"], lengths=g["lengths"],
               alignment=page, page_size=page, map=g["mapping"], live=g["descriptors"], released=0, kernel_close_observed=None),
          label + " prepared binding")
    equal(len(s["slots"]), 3, label + " maximum descriptors")
    for slot, entry in enumerate(s["slots"]):
        if slot >= g["descriptors"]:
            equal(entry, None, label + " unused descriptor")
            continue
        digest = g["stamps"][g["mapping"].index(slot)]
        equal(entry, dict(open_attempted=True, fresh_owned=True, original_stamp=digest, fresh_stamp=digest,
                          matched=True, configured=True, setter=dict(command="F_NOCACHE", number=48,
                          argument=POLICIES.index(policy), returned=0, errno=None)), label + " Darwin setter")
    components = g["components"]
    equal(r["components"], components, label + " sealed routes")
    logical, window, extra, edges, copies, copied = totals(components)
    expected = dict(schema="pulsarmlx.fixed-descriptor-transfer/1", published=True, logical_attempts=3, attempted=3,
                    logical_requested=logical, logical_delivered=logical, requested=window, completed=window,
                    edge_attempts=edges, copies=copies, copied=copied, candidate_overread=extra, attempted_overread=extra,
                    completed_overread=extra, coalescing_overread=0, physical_bytes=None, syscalls=None,
                    cache_bypass_observed=None, performance=None, physical_memory=None)
    equal({k:r[k] for k in expected}, expected, label + " transfer accounting")
    effects = [dict(attempted=True, returned_bytes=c["bytes"],
                    copied=0 if c["route"] == "buffered-edge-exact" else c["logical_bytes"]) for c in components]
    equal(r["effects"], effects, label + " component effects")
    largest = max(c["bytes"] for c in components)
    ledger = r["ledger"]
    equal(fields(ledger, "logical_bytes candidate_bytes largest_request minimum_backing backing_bytes control_reserved additional_reservation"),
          dict(logical_bytes=logical, candidate_bytes=window, largest_request=largest, minimum_backing=largest+page-1,
               backing_bytes=backing, control_reserved=65536, additional_reservation=backing+65536), label + " retained scratch")
    require(0 <= ledger["head_slack"] < page and ledger["usable_bytes"] + ledger["head_slack"] == backing
            and ledger["usable_bytes"] == largest + ledger["tail_slack"], label + " scratch partition")
    require(0 < ledger["control_required"] <= 65536 and 0 < r["policy_control_required"] <= 65536, label + " control bounds")
    equal([s["minimum_reservation"], s["policy_control"], r["combined_reservation"]],
          [largest + page - 1 + 131072, 65536, backing + 131072], label + " combined reservation")
    return row["owner"]


def check_ledger(actual, exact, policy, page, backing):
    # Darwin arm64 Vec has three words. Five vectors and their used count live in the journal.
    weighted_charge = 5 * JOURNAL_SLOT + 5 * 24 + 8 + 8 + 1 + 2048
    equal([actual["policy_journal_slots"], actual["policy_journal_slot_bytes"], actual["H_policy_journal"]],
          [5, JOURNAL_SLOT, weighted_charge], "weighted receipt ledger")
    p = actual["policy"]
    equal(fields(p, "policy page_size max_occurrences role_capacity scratch_backing_bytes base_control_bytes policy_control_bytes transport_bytes"),
          dict(policy=policy, page_size=page, max_occurrences=3, role_capacity=9, scratch_backing_bytes=backing,
               base_control_bytes=65536, policy_control_bytes=65536, transport_bytes=backing + 131072),
          "reader working storage")
    size, fixed = p["role_record_bytes"], p["receipt_bookkeeping"]
    require(type(size) is int and 0 < size <= 2048 and 0 < fixed <= 8192, "bounded typed receipt")
    # The ledger has eleven machine-word scalars plus a one-byte selector rounded to a word.
    # FixedReader owns that ledger, one boxed slice (two words) and one Vec (three words).
    require(fixed >= (96 + 16 + 24) + 96 + 2 * size + 2048, "reader bookkeeping covers live state")
    equal(p["receipt_bytes"], 9 * size + fixed, "typed receipt capacity")
    equal(p["total"], p["receipt_bytes"] + backing + 131072, "reader charge")
    require(p["transport_bytes"] <= 33734653, "fixed transport ceiling")
    expected = dict(exact, policy=p, H_policy_journal=weighted_charge, policy_journal_slots=5,
                    policy_journal_slot_bytes=JOURNAL_SLOT, W_total=exact["W_total"] + p["total"] + weighted_charge)
    equal(actual, expected, "standing charge exactly once")
    return expected["W_total"]


def check_occurrences(rows, matrix, profile, recipe, exact):
    # Check the unchanged Driver's complete synthetic reports as well as original input commitments.
    equal(rows, exact["occurrences"], "complete policy/exact numerical occurrence parity")
    terms = [(i,e,w) for i, plan in enumerate(matrix["expert_weight_bits"]) for e,w in plan]
    equal(len(rows), len(terms), "occurrence count")
    for ordinal, (entry, (position, expert, weight)) in enumerate(zip(rows, terms)):
        row = entry["row"]
        equal([entry["position"], entry["expert"], entry["weight"]], [position, expert, weight], "ordered term")
        equal(fields(row, "position ordinal expert weight_bits recipe status binding"),
              dict(position=position, ordinal=ordinal, expert=expert, weight_bits=weight, recipe=profile,
                   status="weighted_after_retirement", binding=resident.binding(recipe, expert)[0]), "numerical binding")
        hashes = [p["sha256"] for p in recipe["planes"][expert]]
        equal([row["component_sha256_before"], row["component_sha256_after"]], [hashes, hashes], "component authority")
        equal(row["cleanup"], dict(live=0, freed=1, double_free=0, errors=0, messages=0, results=[1,1,0]),
              "synthetic retirement")
        equal(entry["bytes"], len(compact(row)), "occurrence encoded bytes")
        require(entry["bytes"] <= ROLE_LIMIT, "bounded occurrence row")


def check_arm(report, exact, matrix, golden, profile, mode, policy, recipe, page):
    equal(fields(report, "schema profile mode policy book"),
          dict(schema="staged-policy-host/1", profile=profile, mode=mode, policy=policy,
               book=golden["profiles"][profile]["book"]), "arm envelope")
    equal([len(report[k]) for k in ("steps","transport","role_json")], [5,5,5], "five positions")
    schedule, layout, backing = schedule_and_geometry(matrix, profile, recipe, page, policy)
    legacy_ledger = staged.ledger(ROOT, profile, mode, recipe)
    equal(exact["ledger"], legacy_ledger, "original exact ledger")
    standing = check_ledger(report["ledger"], legacy_ledger, policy, page, backing)
    check_occurrences(report["occurrences"], matrix, profile, recipe, exact)
    owner_ids = set()
    components, setter_count = [], 0
    events = []
    for i, (step, plan, expected) in enumerate(zip(report["steps"], matrix["expert_weight_bits"], schedule)):
        request = f"weighted-v1.{report['book']}.{i}.{golden['plan_sha256'][i]}"
        tr = staged.transport(i, mode, report["book"], request, expected)
        equal(report["transport"][i], tr, "ticket, worker, logical and installation history")
        equal(exact["transport"][i], tr, "original exact transport")
        snapshots = staged.snapshot(i, mode, legacy_ledger, expected)
        equal(exact["steps"][i]["snapshot"], snapshots, "original coordinator snapshot")
        snapshots["working_bytes"] = standing
        snapshots["policy_verified_discards"] = dict(roles=0, bytes=0)
        equal(step["snapshot"], snapshots, "fixed coordinator snapshot")
        word = golden["profiles"][profile]["outputs"][i]
        for source in (step, exact["steps"][i]):
            equal([source["bits"], source["sha256"]], [word["bits"], word["sha256"]], "128 binary32 lanes")
        equal([step["token"], step["request_id"], step["position"], step["semantic_position"], step["input_reads"],
               step["active"], step["peak"]], [0, request, i, i+1, i+1, 0, standing+matrix["cumulative"]["peak_above_standing"][i]],
              "coordinator commit")
        equal([step["projections"], step["imports"], step["activations"], step["retired"]],
              [matrix["cumulative"][key][i] for key in ("driver_projections","driver_imports","driver_activations","driver_retirements")],
              "synthetic callback totals")
        events.extend(["begin","gate","up","activation","down","retire"] * len(plan) + ["finish"])
        equal(step["events"], events, "owner callback sequence")
        equal(exact["steps"][i]["synthetic_events"], events, "original callback sequence")
        raw = report["role_json"][i].encode()
        require(len(raw) <= JOURNAL_SLOT, "bounded joined role journal")
        equal([len(raw), sha(raw)], [step["role_journal_bytes"], step["role_journal_sha256"]], "exact journal payload")
        roles = strict(raw)
        misses = [t for t in expected["tickets"] if t["phase"] == "submit"]
        equal(len(roles), 3 * len(misses), "no role work for warm hits")
        for j, ticket in enumerate(misses):
            for role in range(3):
                g = layout[ticket["expert"], role]
                record = roles[3*j+role]
                owner_ids.add(check_role(record, ticket, role, g, profile, policy, page, backing, i))
                components.extend(record["outcome"]["receipt"]["components"])
                setter_count += sum(slot is not None and slot["setter"] is not None
                                    for slot in record["outcome"]["receipt"]["setup"]["slots"])
        equal(totals(components), matrix["cumulative_by_page"][str(page)][profile][i], "observed route totals")
        equal(setter_count, matrix["cumulative"]["setters"][i], "observed setter total")
        if i == 0:
            equal(exact["replay"], dict(same_arc=True, position=1, input_reads=1, snapshot=exact["steps"][i]["snapshot"],
                  events=events), "original replay")
            equal(report["replay"], dict(same_arc=True, lost_delivery=True, replayed=True, position=1, input_reads=1,
                  events=events, snapshot=snapshots, role_journal_sha256=sha(raw)), "committed allocation replay")
    require(len(owner_ids) == 1, "single owner")
    return dict(profile=profile, mode=mode, policy=policy, page=page, occurrences=len(report["occurrences"]),
                logical_components=len(components), fresh_setters=setter_count, byte_totals=totals(components),
                standing=standing, reader=report["ledger"]["policy"], journal=report["ledger"]["H_policy_journal"])


def check_controls(rows, by_arm):
    expected = [(mode,policy,kind,pos) for mode,policy in ((MODES[0],POLICIES[0]),(MODES[1],POLICIES[1]))
                for kind,pos in (("short",0),("short",4),("double",0))]
    equal([[r[k] for k in ("mode","policy","kind","position")] for r in rows], expected, "coordinator controls")
    for row in rows:
        standing = by_arm["mixed",row["mode"],row["policy"]]["standing"]
        equal(row["active"], 0, "released coordinator budget")
        if row["kind"] == "short":
            i = row["position"]
            equal([row["standing"],row["capacity"],row["role_rows"],row["input_reads"],row["error"]],
                  [standing,standing+staged.PEAK[i]-1,i,i,"step_budget_exceeded"], "reservation before next read")
        else:
            require("partial up" in row["primary"] and "retirement failure" in row["cleanup"], "separate primary and cleanup")
            snap = row["snapshot"]
            equal([snap["quarantined"],snap["weighted"],snap["activity"]["banks_home"],snap["activity"]["joined"],
                   snap["activity"]["outstanding"]], [True,0,True,1,False], "join after foreground failure")
            equal([len(row["roles"]),len(row["roles"][0])], [1,3], "successful reads before foreground failure")


def verify(fixed_dir, exact_dir):
    matrix, golden, recipes = frozen_inputs()
    page = os.sysconf("SC_PAGE_SIZE")
    require(page in (4096,16384), "supported observed page size")
    wanted = {"controls.json"}
    result = {}
    for profile, mode, policy in itertools.product(PROFILES, MODES, POLICIES):
        name = f"positive-{profile}-{mode}-{policy}.json"
        wanted.add(name)
        report = read_json(fixed_dir / name, ARM_LIMIT)
        exact = read_json(exact_dir / f"positive-{profile}-{mode}.json", ARM_LIMIT)
        arm = check_arm(report, exact, matrix, golden, profile, mode, policy, recipes[profile], page)
        result[profile,mode,policy] = arm
    for profile in PROFILES:
        same = [row for (p,_,_),row in result.items() if p == profile]
        for row in same[1:]:
            equal([row["standing"],row["journal"],dict(row["reader"],policy=None)],
                  [same[0]["standing"],same[0]["journal"],dict(same[0]["reader"],policy=None)], "equal policy envelopes")
    check_controls(read_json(fixed_dir / "controls.json", 1 << 20), result)
    equal(sorted(p.name for p in fixed_dir.iterdir()), sorted(wanted), "closed fixed export")
    return dict(schema="staged-policy-host-check/1", exact_arms=4, fixed_arms=len(result), page=page,
                positives=list(result.values()), coordinator_controls=6)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixed", type=Path, required=True)
    parser.add_argument("--exact", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.fixed.resolve(strict=True), args.exact.resolve(strict=True)), sort_keys=True))
