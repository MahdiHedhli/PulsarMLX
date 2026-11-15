"""Independent checks of the staged policy qualification wire formats. No native calls."""
import argparse
import itertools
import json
import os
import struct
from pathlib import Path

import f020_staged_policy_reference as fixed
import f020_staged_weighted_check as staged
import f020_weighted_native_check as occurrence
import f020_weighted_native_reference as ref
from f020_weighted_native_check import equal
from f020_weighted_native_reference import require, sha

ARMS = tuple(itertools.product(fixed.PROFILES, fixed.MODES, fixed.POLICIES))
EXACT = tuple(itertools.product(fixed.PROFILES, fixed.MODES))
ARM_LIMIT = 2 << 20
REPORT_LIMIT = 128 << 10
OUTCOMES = 'owner invocation epoch wave bank generation expert binding role verified primary_phase outcome'
PREPARATION = ('policy role binding original_stamps lengths alignment page_size map slots live released '
               'kernel_close_observed minimum_reservation policy_control')
SLOT = 'open_attempted fresh_owned original_stamp fresh_stamp matched setter configured'
TRANSFER = ('schema setup components ledger combined_reservation policy_control_required coalescing_overread '
            'physical_bytes cache_bypass_observed syscalls physical_memory performance published effects '
            'logical_attempts logical_requested attempted requested completed logical_delivered copies copied '
            'candidate_overread attempted_overread completed_overread edge_attempts')
WINDOW_LEDGER = ('logical_bytes candidate_bytes largest_request minimum_backing backing_bytes head_slack '
                 'tail_slack usable_bytes control_required control_reserved additional_reservation')
READER_LEDGER = ('policy page_size max_occurrences role_capacity role_record_bytes receipt_bookkeeping '
                 'receipt_bytes scratch_backing_bytes base_control_bytes policy_control_bytes transport_bytes total')
COMMON = 'schema profile arm policy book steps replay ledger standing final row_count policy_journals payload_before_report'
NATIVE = COMMON + ' admission allocator version initial_counts guards failure harness'
HOST = COMMON + ' ordinal'


def strict(raw, limit=ARM_LIMIT):
    """Decode the finite integer/UTF-8 protocol without format or type coercions."""
    require(type(raw) is bytes and 0 < len(raw) <= limit, 'record length')

    def integer(token):
        require(token != '-0' and len(token) <= 20, 'noncanonical or oversized integer')
        value = int(token)
        require(-(1 << 63) <= value < 1 << 64, 'protocol integer overflow')
        return value

    def invalid(_):
        raise ValueError('fractional, exponential or nonfinite JSON number')

    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=ref.dyadic.unique,
                          parse_int=integer, parse_float=invalid, parse_constant=invalid)
    except RecursionError as exc:
        raise ValueError('record nesting') from exc


def keys(value, names):
    require(type(value) is dict and set(value) == set(names.split()), 'closed keys: ' + names)


def uint(value, maximum=(1 << 64) - 1):
    require(type(value) is int and 0 <= value <= maximum, 'unsigned integer range')
    return value


def vector(value, length):
    require(type(value) is list and len(value) == length, 'vector length')
    return value


def byte_stamp(value):
    for n in vector(value, 32):
        uint(n, 255)


def supported_page(value):
    require(type(value) is int and value in (4096, 16384), 'unsupported page size')
    return value


def closed_directory(root, expected):
    require(root.is_absolute() and root.resolve(strict=True) == root and root.is_dir(), 'evidence directory')
    remaining = set(expected)
    for path in root.iterdir():
        require(path.name in remaining and not path.is_symlink(), 'unexpected directory entry')
        remaining.remove(path.name)
    require(not remaining, 'incomplete evidence directory')


def role_identity(row, ticket, role, position):
    keys(row, OUTCOMES)
    reported = ('invocation', 'wave', 'bank', 'generation', 'expert', 'binding')
    equal([row[k] for k in reported], [ticket[k] for k in reported], 'crossed role/ticket')
    equal([row['role'], row['epoch']], [fixed.ROLES[role], 2 * position + 1], 'role epoch')
    require(uint(row['owner']) > 0, 'owner identity')


def role_shape(row):
    outcome = row['outcome']
    keys(outcome, 'kind receipt retired_live retired_released kernel_close_observed')
    receipt = outcome['receipt']
    keys(receipt, TRANSFER)
    keys(receipt['setup'], PREPARATION)
    keys(receipt['ledger'], WINDOW_LEDGER)
    for value in receipt['ledger'].values():
        uint(value)
    uint(receipt['policy_control_required'])


def policy_journal(raw, tickets, layout, profile, policy, page, backing, position):
    """Join authenticated transport submits to precisely the verified per-role records."""
    rows = strict(raw, fixed.JOURNAL_SLOT)
    misses = [ticket for ticket in tickets if ticket['phase'] == 'submit']
    vector(rows, 3 * len(misses))
    require(len(rows) <= 9 and fixed.compact(rows) == raw, 'bounded direct journal encoding')
    owners, components, setters = set(), [], 0
    for index, row in enumerate(rows):
        ticket, role = misses[index // 3], index % 3
        role_identity(row, ticket, role, position)
        role_shape(row)
        geometry = layout[ticket['expert'], role]
        owners.add(fixed.check_role(row, ticket, role, geometry, profile, policy, page, backing, position))
        receipt = row['outcome']['receipt']
        check_transfer_progress(receipt, geometry['components'])
        components.extend(receipt['components'])
        setters += sum(slot is not None and slot['setter'] is not None for slot in receipt['setup']['slots'])
    return owners, components, setters


def check_transfer_progress(receipt, expected_components):
    """Audit base Progress after a returned error, including any unobserved partial read."""
    keys(receipt, TRANSFER)
    equal(receipt['schema'], 'pulsarmlx.fixed-descriptor-transfer/1', 'transfer schema')
    equal(receipt['components'], expected_components, 'sealed transfer geometry')
    components = vector(expected_components, 3)
    effects = vector(receipt['effects'], 3)
    attempts = uint(receipt['attempted'], 3)
    logical = uint(receipt['logical_attempts'], 3)
    require(attempts <= logical <= attempts + 1, 'logical callback versus raw attempt')
    observed, copies, known = [], [], []
    for i, (effect, component) in enumerate(zip(effects, components)):
        keys(effect, 'attempted returned_bytes copied')
        attempted = i < attempts
        returned = effect['returned_bytes']
        equal(effect['attempted'], attempted, 'attempt prefix')
        copied = 0
        if returned is not None:
            require(attempted, 'return without raw attempt')
            equal(returned, component['bytes'], 'completed exact-at read')
            copied = component['logical_bytes'] if component['route'] != 'buffered-edge-exact' else 0
            known.append(component)
        elif attempted:
            # The last read_exact_at error may have written an unknown prefix.
            require(i + 1 == logical == attempts, 'unknown transfer followed by observed work')
        equal(effect['copied'], copied, 'completed bounce')
        if attempted:
            observed.append(component)
        if copied:
            copies.append(copied)
    def overread(rows):
        return sum(c['bytes'] - c['logical_bytes'] for c in rows)
    expected = dict(logical_requested=sum(c['logical_bytes'] for c in components[:logical]),
                    requested=sum(c['bytes'] for c in observed), completed=sum(c['bytes'] for c in known),
                    logical_delivered=sum(c['logical_bytes'] for c in known), copies=len(copies), copied=sum(copies),
                    candidate_overread=overread(components), attempted_overread=overread(observed),
                    completed_overread=overread(known), edge_attempts=sum(c['route']=='buffered-edge-exact' for c in observed),
                    coalescing_overread=0, physical_bytes=None, cache_bypass_observed=None, syscalls=None,
                    physical_memory=None, performance=None)
    equal({k:receipt[k] for k in expected}, expected, 'observed transfer progress')
    require(type(receipt['published']) is bool and (not receipt['published'] or len(known) == 3), 'publication after reads')
    return dict(known_bytes=expected['completed'], unknown_components=len(observed) - len(known))


def check_setup_failure(row, ticket, role, geometry, policy, page, position, *, observed_slots=None):
    """Validate retained effects from a failed prepare, including the last open slot."""
    role_identity(row, ticket, role, position)
    require(row['verified'] is False and type(row['primary_phase']) is str and row['primary_phase'], 'failed role')
    outcome = row['outcome']
    keys(outcome, 'kind setup')
    equal(outcome['kind'], 'setup_failure', 'setup failure kind')
    setup = outcome['setup']
    keys(setup, PREPARATION)
    largest = max(c['bytes'] for c in geometry['components'])
    equal([setup[k] for k in ('policy', 'role', 'binding', 'original_stamps', 'lengths', 'alignment',
                              'minimum_reservation', 'policy_control', 'live', 'kernel_close_observed')],
          [policy, fixed.ROLES[role], geometry['binding'], geometry['stamps'], geometry['lengths'], page,
           largest + page - 1 + 131072, 65536, 0, None], 'failed prepare identity and released ownership')
    if setup['page_size'] is not None:
        uint(setup['page_size'])
    mapped = vector(setup['map'], 3)
    used = next((i for i, entry in enumerate(mapped) if entry is None), 3)
    equal(mapped, geometry['mapping'][:used] + [None] * (3 - used), 'mapping prefix')
    if used:
        equal(setup['page_size'], page, 'descriptor work requires eligible page')
    slots = vector(setup['slots'], 3)
    if observed_slots is not None:
        equal(slots, observed_slots, 'retained independently observed slot effects')
    present = next((i for i, entry in enumerate(slots) if entry is None), 3)
    require(all(v is None for v in slots[present:]) and present <= len(set(mapped[:used])), 'observed slot prefix')
    owned = setters = 0
    for i, entry in enumerate(slots[:present]):
        keys(entry, SLOT)
        for k in ('open_attempted', 'fresh_owned', 'configured'):
            require(type(entry[k]) is bool, 'setup progress boolean')
        for k in ('original_stamp', 'fresh_stamp'):
            if entry[k] is not None:
                byte_stamp(entry[k])
        original, fresh = entry['original_stamp'], entry['fresh_stamp']
        require(not entry['open_attempted'] or original is not None, 'opened before original stamp')
        require(not entry['fresh_owned'] or entry['open_attempted'], 'fresh ownership without open')
        require(fresh is None or entry['fresh_owned'], 'fresh stamp without ownership')
        matched = entry['matched']
        require(matched is None or (type(matched) is bool and fresh is not None), 'identity observation')
        require(matched is not True or original == fresh, 'matched stamps')
        call = entry['setter']
        if call is not None:
            keys(call, 'command number argument returned errno')
            expected = geometry['stamps'][geometry['mapping'].index(i)]
            equal([matched, original, fresh, call['command'], call['number'], call['argument']],
                  [True, expected, expected, 'F_NOCACHE', 48, fixed.POLICIES.index(policy)], 'pre-set witness')
            require(type(call['returned']) is int and -(1 << 31) <= call['returned'] < 1 << 31, 'setter return')
            if call['errno'] is not None:
                require(call['returned'] < 0 and 0 < uint(call['errno']) < 1 << 31, 'setter errno')
            setters += 1
        equal(entry['configured'], call is not None and call['returned'] == 0, 'setter progress')
        if i + 1 < present or any(x is not None and x > i for x in mapped):
            require(entry['configured'], 'missing prior setter success')
        owned += int(entry['fresh_owned'])
    equal(setup['released'], owned, 'all observed owned descriptors released')
    return dict(owned=owned, setters=setters, released=owned, kernel_close_observed=None)


def check_unknown_progress(failure, *, completed_phases, ffi_counts):
    """Check the child failure marker against observed phases and counters; missing I/O stays unknown."""
    keys(failure, 'status completed_phases ffi_counts reason unobserved_effects')
    equal([failure['status'], failure['unobserved_effects'], failure['completed_phases'], failure['ffi_counts']],
          ['failed', 'unknown', completed_phases, ffi_counts], 'failure observations')
    phases = ('verified_child', 'initial_guard', 'abi', 'error_handler', 'default_gpu',
              'verified_version_and_empty_cache', 'weighted_setup')
    require(type(completed_phases) is list and 1 <= len(completed_phases) <= len(phases), 'phase count')
    equal(completed_phases, list(phases[:len(completed_phases)]), 'ordered failure phases')
    for n in vector(ffi_counts, 2):
        uint(n)
    require(type(failure['reason']) is str and 0 < len(failure['reason']) <= 512, 'bounded failure')


def check_replay(replay, snapshot, counts, policy_sha256):
    equal(replay, dict(same_commit=True, lost_delivery=True, position=1, input_reads=1, counts=counts,
                       snapshot=snapshot, guard_count=4, policy_sha256=policy_sha256), 'native replay without work')


def host_tensor(words):
    raw = ref.dyadic.words(words)
    return dict(dtype='F32', shape=[1, len(words)], bytes=len(raw), sha256=sha(raw), f32_bits=words)


def host_occurrence(row, recipe, patterns, profile, position, ordinal, expert, weight):
    """Derive the deliberately synthetic Driver records and lane data from the frozen recipe."""
    binding, size = fixed.resident.binding(recipe, expert)
    capacity = uint(row['staging_capacity'])
    require(size <= capacity <= 65536, 'tuple staging capacity')
    planes = recipe['planes'][expert]
    hashes = [p['sha256'] for p in planes]
    zeros = [0] * 64
    pattern = patterns[expert]
    outputs = [host_tensor(zeros), host_tensor(zeros), host_tensor(pattern * (128 // len(pattern)))]
    stages = {}
    for i, (role, plane) in enumerate(zip(fixed.ROLES, planes)):
        n, k = plane['logical_shape']
        stages[role] = dict(bits=plane['bits'], group_size=64, packed_weight_sha256=hashes[i][0],
                            output=outputs[i], bound_gamma_n=occurrence.r1.gamma_n(1, n, k),
                            device_facts_gpu=True, cpu_guard_checks=2, imports_before_decision=0,
                            numerical_before_decision=0, imports=4, numerical=1, active_cache_peak=[0, 0, 0])
    expected = dict(ordinal=ordinal, position=position, weight_bits=weight, status='weighted_after_retirement',
                    expert=expert, recipe=profile, slot_generation=list(occurrence.SLOTS[ordinal]), binding=binding,
                    component_sha256_before=hashes, component_sha256_after=hashes, staging_capacity=capacity,
                    cleanup=dict(live=0, freed=1, double_free=0, errors=0, messages=0, results=[1, 1, 0]),
                    copies=dict(staging_components=9, staging_bytes=size, qmm_data_imports=12, qmm_metadata_widenings=6,
                                projection_readbacks=3, activation_input_imports=2, scalar_imports=2,
                                activation_readbacks=3, down_host_reimport=1),
                    activation=dict(status=0, stats=[2, 0, 9, 4, 13, 1, 9, 0], materializations=1,
                                    gate_clamp_bits=zeros, up_clamp_bits=zeros, output=host_tensor(zeros),
                                    active_cache_peak=[0, 0, 0]),
                    down_admission=dict(actual_input_sha256=outputs[0]['sha256'], decision='admitted',
                                        imports_before_decision=0, numerical_before_decision=0), **stages)
    equal(row, expected, 'synthetic occurrence and retirement')
    return [ref.dyadic.words(row[role]['output']['f32_bits']) for role in ('gate', 'up', 'activation', 'down')]


def validate_guards(guards):
    phases = ['initial']
    for plan in ref.ROUTE:
        phases.extend(['retired'] * len(plan) + ['finish', 'committed'])
    vector(guards, len(phases))
    for entry in guards:
        vector(entry, 2)
    equal([p for p, _ in guards], phases, 'guard stages')
    word = uint(guards[0][1])
    require(not word & ((3 << 22) | (1 << 24) | 3 | 0x9f00), 'guard FPCR')
    equal([w for _, w in guards], [word] * len(phases), 'FPCR stability')


def check_ledger(ledger, profile, mode, policy, page, backing, recipe):
    legacy = staged.ledger(fixed.ROOT, profile, mode, recipe)
    if policy is None:
        equal(ledger, legacy, 'exact ledger')
        return legacy['W_total']
    reader = ledger['policy']
    keys(reader, READER_LEDGER)
    for key, value in reader.items():
        if key != 'policy':
            uint(value)
    standing = fixed.check_ledger(ledger, legacy, policy, page, backing)
    # Unchanged Darwin arm64 Rust026 receipt layout under the frozen compiler ABI.
    # FixedReader is 152 bytes (ledger, slice, Vec and discarded counters), PolicyLedger is 96.
    equal([reader['role_record_bytes'], reader['receipt_bookkeeping']], [1248, 152 + 96 + 2 * 1248 + 2048],
          'fixed reader accounting ABI')
    require(reader['receipt_bytes'] + ledger['H_policy_journal'] <= 2073600, 'combined staged receipts')
    return standing


def arm_files(with_policy):
    names = {'report.json'}
    for i in range(5):
        names.update((f'weighted-{i}.f32', f'transport-{i}.json'))
        if with_policy:
            names.add(f'policy-{i}.json')
    names.update(f'occ-{i:02}.json' for i in range(12))
    return names


def hex_digest(value, length=64):
    require(type(value) is str and len(value) == length and all(c in '0123456789abcdef' for c in value), 'digest encoding')
    return value


def arm_output(root, profile, mode, policy, identity, admission, originals, observe=None):
    """Grade only original child files against a separately authenticated startup and source enclosure."""
    require((profile, mode, policy) in ARMS, 'native arm identity')
    keys(admission, 'schema run ordinal profile arm policy page_size closure_sha256 input_sha256 reference intent_sha256 source tree binary_sha256 build_sha256 images')
    page_text = identity['host']['page']
    require(page_text in ('4096', '16384'), 'bound Studio page')
    page = supported_page(int(page_text))
    equal([admission[k] for k in ('schema', 'ordinal', 'profile', 'arm', 'policy', 'page_size')],
          ['staged-policy-startup/1', ARMS.index((profile, mode, policy)), profile, mode, policy, page], 'native startup')
    for key in ('run', 'closure_sha256', 'input_sha256', 'reference', 'intent_sha256', 'binary_sha256', 'build_sha256'):
        hex_digest(admission[key])
    for key in ('source', 'tree'):
        hex_digest(admission[key], 40)
    equal(admission['closure_sha256'], identity['input_sha256'], 'native closure identity')
    # The supervisor rederives this receipt from the exclusive live claim, images and original intent bytes.
    equal([admission[k] for k in ('source', 'tree', 'binary_sha256', 'build_sha256', 'reference', 'run', 'input_sha256', 'page_size')],
          [identity[k] for k in ('commit', 'tree', 'binary_sha256', 'build_sha256', 'reference', 'run', 'input_sha256', 'page_size')],
          'native provenance')
    matrix, golden, recipes = fixed.frozen_inputs()
    equal(recipes[profile], originals.recipes[profile], 'native original versus fixture recipe')
    summary = check_files(Path(root), profile, mode, policy, page, matrix, golden, recipes[profile],
                          native=(identity, admission, originals), observe=observe)
    common = ('run', 'source', 'tree', 'page_size', 'closure_sha256', 'input_sha256', 'reference',
              'binary_sha256', 'build_sha256', 'images')
    summary['provenance'] = sha(ref.canonical({k: admission[k] for k in common}))
    return summary


def check_files(root, profile, mode, policy, page, matrix, golden, recipe, *, native=None, patterns=None, observe=None):
    with_policy = policy is not None
    closed_directory(root, arm_files(with_policy))
    size = 0

    def read(name, cap):
        nonlocal size
        raw = ref.bounded(root / name, cap)
        size += len(raw)
        require(size <= ARM_LIMIT, 'arm output envelope')
        return raw

    raw = read('report.json', REPORT_LIMIT)
    report_bytes = len(raw)
    report = strict(raw, REPORT_LIMIT)
    keys(report, NATIVE if native else HOST)
    expected_schema = 'staged-policy-native-arm/1' if native else 'staged-policy-host-adapter/1'
    equal([report[k] for k in ('schema', 'profile', 'arm', 'policy', 'book', 'row_count')],
          [expected_schema, profile, mode, policy, ref.BOOKS[profile], 12], 'execution scope and arm')
    if native:
        identity, admission, originals = native
        equal([report[k] for k in ('admission', 'version', 'initial_counts', 'failure')],
              [admission, identity['version'], [0, 0], None], 'admitted native report')
        keys(report['allocator'], 'previous_limit initial_cache cache_limit initial_clear')
        uint(report['allocator']['previous_limit'])
        equal([report['allocator'][k] for k in ('initial_cache', 'cache_limit', 'initial_clear')], [0, 0, 0], 'empty cache')
        validate_guards(report['guards'])
    else:
        ordinal = ARMS.index((profile, mode, policy)) if with_policy else EXACT.index((profile, mode))
        equal(report['ordinal'], ordinal, 'host arm ordinal')
    if with_policy:
        schedule, layout, backing = fixed.schedule_and_geometry(matrix, profile, recipe, page, policy)
    else:
        schedule, layout, backing = staged.schedule(profile, recipe), {}, 0
    standing = check_ledger(report['ledger'], profile, mode, policy, page, backing, recipe)
    equal(report['standing'], standing, 'standing reservation')
    if native:
        equal(report['harness'], occurrence.harness(standing + occurrence.PEAK[-1]), 'outer harness')
    vector(report['steps'], 5)
    vector(report['policy_journals'], 5 if with_policy else 0)
    stage_hashes, final_hashes, gate_hashes, journal_hashes, owners, components = [], [], [], [], set(), []
    ord_count, setter_count, journal_size = 0, 0, 0
    counts = [0, 0]
    # Stage digests identify fixed-size, ordered vectors; only these commitments survive the arm.
    for pos, plan in enumerate(ref.ROUTE):
        expected = schedule[pos]
        book = ref.BOOKS[profile]
        request = f"weighted-v1.{book}.{pos}.{golden['plan_sha256'][pos]}"
        transport = strict(read(f'transport-{pos}.json', staged.ROW), staged.ROW)
        equal(transport, staged.transport(pos, mode, book, request, expected), 'ticket, activity and resident schedule')
        journal_hash = None
        if with_policy:
            journal = read(f'policy-{pos}.json', fixed.JOURNAL_SLOT)
            journal_hash = sha(journal)
            journal_size += len(journal)
            journal_hashes.append(journal_hash)
            equal(report['policy_journals'][pos], dict(bytes=len(journal), sha256=journal_hash), 'direct journal metadata')
            ids, additions, setters = policy_journal(journal, transport['tickets'], layout, profile, policy, page, backing, pos)
            owners.update(ids)
            components.extend(additions)
            setter_count += setters
            equal(fixed.totals(components), matrix['cumulative_by_page'][str(page)][profile][pos], 'observed route byte totals')
            equal(setter_count, matrix['cumulative']['setters'][pos], 'observed cumulative setter count')
        downs = []
        for expert, weight in plan:
            if observe:
                observe(dict(stage='expert', ordinal=ord_count, position=pos, started=True))
            data = read(f'occ-{ord_count:02}.json', fixed.ROLE_LIMIT)
            row = strict(data, fixed.ROLE_LIMIT)
            if native:
                stats = vector(row['activation']['stats'], 8)
                for value in stats:
                    uint(value)
                vectors = occurrence.check_occurrence(row, profile, 'cached', pos, ord_count, expert, weight, originals)
                counts[0] += sum(row[k]['numerical'] for k in fixed.ROLES) + 2
                counts[1] += sum(row[k]['imports'] for k in fixed.ROLES)
                if observe:
                    observe(dict(stage='expert', ordinal=ord_count, position=pos, passed=True, sha256=sha(data), counts=[64, 64, 64, 128, 128]))
            else:
                vectors = host_occurrence(row, recipe, patterns, profile, pos, ord_count, expert, weight)
            stage_hashes.extend(sha(v) for v in vectors)
            downs.append((expert, row['down']['output']['f32_bits']))
            ord_count += 1
        raw_vector = read(f'weighted-{pos}.f32', 512)
        require(len(raw_vector) == 512, '128 binary32 lanes')
        words = list(struct.unpack('<128I', raw_vector))
        final_hash = sha(raw_vector)
        final_hashes.append(final_hash)
        if native:
            if observe:
                observe(dict(stage='weighted', position=pos, started=True))
            endpoints = originals.artifact['profiles'][profile]['endpoints'][pos]
            predicted = ref.weighted_gates(plan, downs, words, endpoints)
            digest = sha(ref.dyadic.words(predicted))
            gate_hashes.append([digest, sha(ref.canonical(endpoints))])
            if observe:
                observe(dict(stage='weighted', position=pos, passed=True, local=128, enclosure=128, expected_sha256=digest))
        else:
            equal(dict(bits=words, sha256=final_hash), golden['profiles'][profile]['outputs'][pos], 'synthetic weighted lanes')
            equal(words, ref.local_bits(plan, downs), 'weighted result versus actual host occurrence words')
        snap = staged.snapshot(pos, mode, report['ledger'], expected)
        if with_policy:
            snap['policy_verified_discards'] = dict(roles=0, bytes=0)
        step = dict(position=pos, request=request, token=0, input_reads=pos + 1, snapshot=snap,
                    peak=standing + occurrence.PEAK[pos], active=0, sha256=final_hash)
        if native:
            step['counts'] = counts
        equal(report['steps'][pos], step, 'committed step')
        if pos == 0:
            if native:
                check_replay(report['replay'], snap, counts, journal_hash)
            else:
                equal(report['replay'], dict(same_commit=True, lost_delivery=True, position=1, input_reads=1,
                                             snapshot=snap, policy_sha256=journal_hash, driver_retirements=1), 'host replay')
    equal(report['final'], snap, 'final snapshot')
    equal(report['payload_before_report'], size - report_bytes, 'payload census')
    require(journal_size <= 5 * 1024 + 18 * (fixed.ROLE_LIMIT + 4096), 'finite journal disk charge')
    require(size <= 1850880, 'finite success output envelope')
    equal([len(owners), ord_count, len(stage_hashes), len(final_hashes)], [int(with_policy), 12, 48, 5], 'finite arm population')
    return dict(schema=expected_schema, profile=profile, arm=mode, policy=policy,
                stages_sha256=sha(ref.canonical(stage_hashes)), finals_sha256=sha(ref.canonical(final_hashes)),
                gates_sha256=sha(ref.canonical(gate_hashes)) if native else None,
                journals_sha256=sha(ref.canonical(journal_hashes)), occurrences=ord_count, vectors=len(final_hashes))


def compare(pop):
    """Compare compact commitments after all eight native arms pass their individual gates."""
    equal(list(pop), list(ARMS), 'complete ordered policy arm population')
    for arm, desc in pop.items():
        keys(desc, 'schema profile arm policy stages_sha256 finals_sha256 gates_sha256 journals_sha256 occurrences vectors provenance')
        equal([desc['schema'], desc['profile'], desc['arm'], desc['policy'], desc['occurrences'], desc['vectors']],
              ['staged-policy-native-arm/1', *arm, 12, 5], 'native arm result')
        for key in ('stages_sha256', 'finals_sha256', 'gates_sha256', 'journals_sha256', 'provenance'):
            hex_digest(desc[key])
    require(len({row['provenance'] for row in pop.values()}) == 1, 'crossed native campaign')
    for profile in fixed.PROFILES:
        rows = [row for (p, _, _), row in pop.items() if p == profile]
        comparisons = [(row['stages_sha256'], row['finals_sha256'], row['gates_sha256']) for row in rows]
        require(len(set(comparisons)) == 1, 'serial/overlap and policy numerical parity')
    return dict(occurrences=96, projections=288, activations=96, stage_pairs=288, final_pairs=30, weighted_vectors=40,
                WEIGHTED_LOCAL_BITS_V1=5120, WEIGHTED_SOURCE_ENCLOSURE_V1=5120)


def verify_host(root, page=None):
    """Verify 4 exact controls and 8 policy arms exported by the real adapter and synthetic Driver."""
    root = Path(root)
    page = supported_page(os.sysconf('SC_PAGE_SIZE') if page is None else page)
    ids = [(p, m, None) for p, m in EXACT] + list(ARMS)
    names = [f"{p}-{m}-{policy or 'Exact'}" for p, m, policy in ids]
    closed_directory(root, names)
    matrix, golden, recipes = fixed.frozen_inputs()
    source = strict(ref.bounded(fixed.ROOT / 'fixtures/weighted-expert-mlp/routes.json', 1 << 20), 1 << 20)
    by_profile = {}
    for (profile, mode, policy), name in zip(ids, names):
        result = check_files(root / name, profile, mode, policy, page, matrix, golden, recipes[profile],
                             patterns=source['patterns'][profile])
        outputs = [result['stages_sha256'], result['finals_sha256']]
        equal(outputs, by_profile.setdefault(profile, outputs), 'host exact/serial/overlap/policy parity')
    return dict(schema='staged-policy-host-adapter-check/1', exact_arms=len(EXACT), fixed_arms=len(ARMS), page=page,
                occurrences=len(ids) * 12, weighted_vectors=len(ids) * 5, profile_digests=by_profile)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', type=Path, required=True, help='absolute directory of original host adapter exports')
    args = parser.parse_args()
    print(json.dumps(verify_host(args.host.absolute()), sort_keys=True))
