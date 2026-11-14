use super::*;
use crate::test_support::{fixture, Fixture};
use serde_json::{json, Value};
use std::{fs, io::Write, path::PathBuf};
fn emit(label: &str, value: Value) {
    if let Some(root) = std::env::var_os("WINDOW_CAPTURE_DIR") {
        let mut f = fs::OpenOptions::new()
            .append(true)
            .create(true)
            .open(PathBuf::from(root).join("policy-controls.jsonl"))
            .unwrap();
        writeln!(f, "{}", json!([label, value])).unwrap();
    }
}
fn owned() -> Fixture {
    fixture(128, 64, 3, false, 0, true)
}
fn parts(plan: &ExpertPlan, role: ExpertRole) -> [Vec<u8>; 3] {
    let all = plan.load().unwrap();
    std::array::from_fn(|i| all.bytes(role.index(), i).unwrap().to_vec())
}
fn dst<'a>(p: &'a mut [Vec<u8>; 3], h: [String; 3]) -> PlaneDestination<'a> {
    let [w, s, b] = p;
    PlaneDestination::new(w, s, b, h)
}
fn hashes(p: &[Vec<u8>; 3]) -> [String; 3] {
    p.each_ref().map(|v| digest(v))
}
fn three_shards(f: &Fixture) {
    let path = f.root.join("model.safetensors");
    let bytes = fs::read(path).unwrap();
    let end = 8 + u64::from_le_bytes(bytes[..8].try_into().unwrap()) as usize;
    let hdr: Value = serde_json::from_slice(&bytes[8..end]).unwrap();
    let mut map = serde_json::Map::new();
    for (name, row) in hdr.as_object().unwrap() {
        let offsets = &row["data_offsets"];
        let a = offsets[0].as_u64().unwrap() as usize;
        let b = offsets[1].as_u64().unwrap() as usize;
        let mut r = row.clone();
        r["data_offsets"] = json!([0, b - a]);
        let h = serde_json::to_vec(&json!({name:r})).unwrap();
        let shard = format!("{name}.safetensors");
        let mut out = fs::File::create(f.root.join(&shard)).unwrap();
        out.write_all(&(h.len() as u64).to_le_bytes()).unwrap();
        out.write_all(&h).unwrap();
        out.write_all(&bytes[end + a..end + b]).unwrap();
        map.insert(name.clone(), json!(shard));
    }
    fs::write(
        f.root.join("model.safetensors.index.json"),
        serde_json::to_vec(&json!({"metadata":{"total_size":bytes.len()-end},"weight_map":map}))
            .unwrap(),
    )
    .unwrap();
}

#[test]
fn platform_page_and_short_preparation_budget_refuse_before_open() {
    let f = owned();
    let src = BoundedSource::open(&f.root).unwrap();
    let plan = src.plan(f.request.clone()).unwrap();
    for a in [4096, 16384] {
        let wp = WindowPlan::new(&plan, ExpertRole::Gate, a).unwrap();
        let min = PreparedPolicy::minimum_budget(&wp);
        for (page, budget, reason) in [
            (Err("UNSUPPORTED_PLATFORM"), min, "UNSUPPORTED_PLATFORM"),
            (Ok(65536), min, "PAGE_ALIGNMENT"),
            (
                Ok(if a == 4096 { 16384 } else { 4096 }),
                min,
                "PAGE_ALIGNMENT",
            ),
            (Ok(a), min - 1, "POLICY_BUDGET"),
        ] {
            let f = PreparedPolicy::prepare_with(
                &wp,
                Policy::NoCacheRequested,
                budget,
                page,
                |_, _, _, _| panic!("unexpected open"),
            )
            .err()
            .unwrap();
            assert_eq!(f.cause.detail, reason);
            assert_eq!((f.setup.live, f.setup.released), (0, 0));
            assert!(f.setup.slots.iter().all(Option::is_none));
            emit("mock-admission", json!([reason, f.setup]));
        }
    }
    assert_eq!(src.payload_read_calls(), 0);
}

#[cfg(target_os = "macos")]
#[test]
fn three_shard_setup_preserves_failed_positions_and_releases_ownership() {
    let f = owned();
    three_shards(&f);
    let src = BoundedSource::open(&f.root).unwrap();
    let plan = src.plan(f.request.clone()).unwrap();
    let wp = WindowPlan::new(&plan, ExpertRole::Gate, platform::page_size().unwrap()).unwrap();
    let budget = PreparedPolicy::minimum_budget(&wp);
    for stop in 0..=3 {
        let mut i = 0;
        let res = PreparedPolicy::prepare_with(
            &wp,
            Policy::NoCacheRequested,
            budget,
            Ok(wp.a),
            |root, name, file, policy| {
                let pos = i;
                i += 1;
                if pos == stop {
                    // Simulated platform result only for the specified position. Earlier slots are real.
                    return Err(SetupFailure {
                        reason: "POLICY_SETTER",
                        observation: Setup {
                            open_attempted: true,
                            fresh_owned: true,
                            matched: Some(true),
                            setter: Some(platform::Setter {
                                command: "mock-F_NOCACHE",
                                number: -1,
                                argument: 1,
                                returned: -1,
                                errno: Some(4),
                            }),
                            ..Setup::default()
                        },
                    });
                }
                FixedDescriptor::open(root, name, file, policy)
            },
        );
        let obs = if stop < 3 {
            let e = res.err().unwrap();
            assert_eq!(e.cause.detail, "POLICY_SETTER");
            assert_eq!(i, stop + 1);
            e.setup
        } else {
            let p = res.unwrap();
            assert_eq!(p.setup.map, [Some(0), Some(1), Some(2)]);
            p.retire()
        };
        assert_eq!(obs.live, 0);
        assert_eq!(obs.released, i);
        assert_eq!(src.payload_read_calls(), 0);
        emit("three-shard-setup", json!([stop, obs]));
    }
}

#[cfg(target_os = "macos")]
#[test]
fn policy_failures_preserve_completed_reads_and_setup() {
    let f = owned();
    let src = BoundedSource::open(&f.root).unwrap();
    let plan = src.plan(f.request.clone()).unwrap();
    let role = ExpertRole::Gate;
    let original = parts(&plan, role);
    let wp = WindowPlan::new(&plan, role, platform::page_size().unwrap()).unwrap();
    let budget = PreparedPolicy::minimum_budget(&wp);
    let mut s = Scratch::new(&wp, budget).unwrap();
    let mut p = PreparedPolicy::prepare(&wp, Policy::NoCacheRequested, budget).unwrap();
    emit("setup", json!(p.setup));
    for fail in 0..3 {
        for partial in [true, false] {
            let mut i = 0;
            let mut buf = original.each_ref().map(|v| vec![0x4c; v.len()]);
            let mut h = hashes(&original);
            if !partial {
                h[fail] = "0".repeat(64);
            }
            let f = p
                .read_with(&mut s, dst(&mut buf, h), budget, |route, b, at| {
                    let pos = i;
                    i += 1;
                    if partial && pos == fail {
                        b[..2].fill(0xee);
                        return Err(io::ErrorKind::UnexpectedEof.into());
                    }
                    match route {
                        Source::Fresh(v) => v.read_exact_at(b, at),
                        Source::Original(v) => v.file.read_exact_at(b, at),
                    }
                })
                .err()
                .unwrap();
            assert_eq!(f.cause.phase, if partial { "READ" } else { "CONTENT" });
            let r = f.receipt;
            let done = fail + usize::from(!partial);
            assert!(!r.published);
            assert_eq!(r.progress.logical_attempts, (fail + 1) as u64);
            assert_eq!(r.progress.attempted, r.progress.logical_attempts);
            assert_eq!(
                r.progress.completed,
                r.components[..done].iter().map(|v| v.bytes).sum::<u64>()
            );
            assert_eq!(
                r.progress.copied,
                r.components[..done]
                    .iter()
                    .filter(|v| v.route != Route::OriginalEdge)
                    .map(|v| v.logical_bytes)
                    .sum::<u64>()
            );
            assert_eq!(
                r.progress.effects[fail].returned_bytes,
                if partial {
                    None
                } else {
                    Some(r.components[fail].bytes)
                }
            );
            assert_eq!(r.setup.live, 1);
            emit(
                "payload-fault",
                json!([fail, partial, r, r.encoded_bytes()]),
            );
        }
    }
    p.setup.map[0] = None;
    let mut b = original.clone();
    let failure = p
        .read_with(
            &mut s,
            dst(&mut b, hashes(&original)),
            budget,
            |_, _, _| panic!(),
        )
        .err()
        .unwrap();
    assert_eq!(failure.cause.detail, "SOURCE_MAP");
    assert_eq!(
        (
            failure.receipt.progress.logical_attempts,
            failure.receipt.progress.attempted
        ),
        (1, 0)
    );
    emit("mapping", json!(failure.receipt));
    p.setup.map[0] = Some(0);
    let writer = fs::OpenOptions::new()
        .write(true)
        .open(f.root.join("model.safetensors"))
        .unwrap();
    let fail = p
        .read_with(
            &mut s,
            dst(&mut b, hashes(&original)),
            budget,
            |route, buf, at| {
                match route {
                    Source::Fresh(v) => v.read_exact_at(buf, at)?,
                    Source::Original(h) => h.file.read_exact_at(buf, at)?,
                };
                writer.set_len(9)
            },
        )
        .err()
        .unwrap();
    assert_eq!(fail.cause.phase, "MUTATION");
    assert_eq!(fail.receipt.progress.attempted, 1);
    assert!(fail.receipt.progress.completed > 0);
    assert!(p.files[0].as_ref().unwrap().check().is_err());
    emit("stamp-change", json!(fail.receipt));
    let fail = PreparedPolicy::prepare(&wp, Policy::BufferedRequested, budget)
        .err()
        .unwrap();
    assert_eq!(fail.cause.phase, "MUTATION");
    assert_eq!(fail.setup.live, 0);
    emit("retire", json!(p.retire()));
}

#[cfg(target_os = "macos")]
#[test]
fn page_routing_retained_roots_canaries_and_scratch_reuse() {
    let page = platform::page_size().unwrap();
    for padded in [false, true] {
        let parent = owned();
        let mut f = fixture(256, 128, 3, false, 0, true);
        let long = "割当".repeat(36);
        let root = parent.root.join(&long);
        fs::rename(&f.root, &root).unwrap();
        f.root = root;
        if padded {
            let path = f.root.join("model.safetensors");
            let old = fs::read(&path).unwrap();
            let first = 8 + u64::from_le_bytes(old[..8].try_into().unwrap()) as usize;
            let mut new = old[..first].to_vec();
            new[..8].copy_from_slice(&(page - 8).to_le_bytes());
            new.resize(page as usize, b' ');
            new.extend_from_slice(&old[first..]);
            fs::write(path, new).unwrap();
        }
        let src = BoundedSource::open(&f.root).unwrap();
        let mut req = f.request.clone();
        let a = src.plan(req.clone()).unwrap();
        req.expert = 2;
        let b = src.plan(req).unwrap();
        let wa = WindowPlan::new(&a, ExpertRole::Gate, page).unwrap();
        let wb = WindowPlan::new(&b, ExpertRole::Down, page).unwrap();
        let original = [parts(&a, ExpertRole::Gate), parts(&b, ExpertRole::Down)];
        let cap = PreparedPolicy::minimum_budget(&wa).max(PreparedPolicy::minimum_budget(&wb));
        let mut scratch =
            Scratch::new(if wa.minimum >= wb.minimum { &wa } else { &wb }, cap).unwrap();
        let ptr = scratch.storage.as_ptr();
        let pa = PreparedPolicy::prepare(&wa, Policy::BufferedRequested, cap).unwrap();
        let pb = PreparedPolicy::prepare(&wb, Policy::NoCacheRequested, cap).unwrap();
        emit("setup", json!(pa.setup));
        emit("setup", json!(pb.setup));
        let original_path = f.root.clone();
        let moved = parent.root.join("moved");
        fs::rename(&f.root, &moved).unwrap();
        f.root = moved;
        fs::create_dir(&original_path).unwrap();
        fs::write(original_path.join("model.safetensors"), b"decoy").unwrap();
        let mut edge = false;
        let mut prefix = false;
        let mut already_aligned = false;
        let mut sibling = false;
        for (which, p) in [(0, &pa), (1, &pb), (0, &pa)] {
            let reference = &original[which];
            let mut out = reference.each_ref().map(|b| vec![0xb2; b.len() + 2]);
            let [w, s, b] = &mut out;
            fn inside(v: &mut [u8]) -> &mut [u8] {
                let end = v.len() - 1;
                &mut v[1..end]
            }
            let d = PlaneDestination::new(inside(w), inside(s), inside(b), hashes(reference));
            scratch.storage.fill(0x6b);
            let mut i = 0;
            let (filled, r) = p
                .read_with(&mut scratch, d, cap, |source, bytes, at| {
                    let window = p.window.windows[i];
                    assert_eq!((at, bytes.len() as u64), (window.begin, window.bytes));
                    match source {
                        Source::Fresh(f) => {
                            assert_eq!(window.kind, Kind::Window);
                            assert_eq!(
                                (
                                    at % page,
                                    bytes.len() as u64 % page,
                                    bytes.as_ptr() as usize % page as usize
                                ),
                                (0, 0, 0)
                            );
                            f.read_exact_at(bytes, at)?;
                            prefix |= at == 0 && window.logical_begin > 8;
                            already_aligned |=
                                window.logical_begin == at && window.logical_bytes == window.bytes;
                            sibling |= bytes[(window.delta + window.logical_bytes) as usize..]
                                .iter()
                                .any(|v| *v != reference[i][0]);
                        }
                        Source::Original(h) => {
                            assert_eq!(window.kind, Kind::Edge);
                            assert!(std::ptr::eq(h, p.window.held[i]));
                            h.file.read_exact_at(bytes, at)?;
                            edge = true;
                        }
                    }
                    i += 1;
                    Ok(())
                })
                .unwrap()
                .into_parts();
            assert_eq!(filled.into_receipt().actual_sha256, hashes(reference));
            assert_eq!(scratch.storage.as_ptr(), ptr);
            for (v, expected) in out.iter().zip(reference) {
                assert_eq!(v[0], 0xb2);
                assert_eq!(*v.last().unwrap(), 0xb2);
                assert_eq!(&v[1..v.len() - 1], expected);
            }
            let head = r.ledger.head_slack as usize;
            let end = head + r.ledger.largest_request as usize;
            assert!(scratch.storage[..head]
                .iter()
                .chain(&scratch.storage[end..])
                .all(|&v| v == 0x6b));
            emit(
                "layout-transfer",
                json!([padded, which, r, r.encoded_bytes()]),
            );
        }
        if padded {
            assert!(already_aligned);
        } else {
            assert!(prefix);
        }
        assert!(edge && sibling);
        for fault in [
            "short",
            "large",
            "empty",
            "hash",
            "scratch-small",
            "retained-underbudget",
            "budget",
        ] {
            let mut buf = original[0].clone();
            let mut h = hashes(&buf);
            match fault {
                "short" => {
                    buf[2].pop();
                }
                "large" => buf[2].push(0),
                "empty" => buf[2].clear(),
                "hash" => h[2] = "G".repeat(64),
                _ => (),
            }
            let mut owned_scratch = Scratch::new(&wa, cap).unwrap();
            let base = wa.minimum + CONTROL + POLICY_CONTROL;
            if fault == "scratch-small" {
                owned_scratch.storage = vec![0; 1].into_boxed_slice();
            }
            if fault == "retained-underbudget" {
                owned_scratch.storage = vec![0; (wa.minimum + 1) as usize].into_boxed_slice();
            }
            let before = src.payload_read_calls();
            let original_input = buf.clone();
            let e = pa
                .read_with(
                    &mut owned_scratch,
                    dst(&mut buf, h),
                    base - u64::from(fault == "budget"),
                    |_, _, _| panic!(),
                )
                .err()
                .unwrap();
            assert_eq!(before, src.payload_read_calls());
            assert_eq!(buf, original_input);
            assert!(!e.receipt.published);
            assert_eq!(e.receipt.setup.live, 1);
            emit(
                "post-setup-refusal",
                json!([fault, e.cause.phase, e.receipt]),
            );
        }
        emit("retire", json!(pa.retire()));
        emit("retire", json!(pb.retire()));
        let mut excess = src.plan(f.request.clone()).unwrap();
        excess.record.planes[0].module = "測".repeat(7000);
        assert!(WindowPlan::new(&excess, ExpertRole::Gate, page).is_err());
        drop(f);
    }
}
