use super::*;
use crate::test_support::{fixture, Fixture};
use serde_json::{json, Value};
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::PathBuf;
use ExpertRole::*;
use Mode::*;

const ARM: [Mode; 2] = [BufferedExact, BufferedAlignedWindow];

fn emit(name: &str, observation: Value) {
    if let Some(root) = std::env::var_os("WINDOW_CAPTURE_DIR") {
        let path = PathBuf::from(root).join(format!("{name}.jsonl"));
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
            .unwrap();
        writeln!(file, "{observation}").unwrap();
    }
}
fn shape(result: std::result::Result<Window, &str>) -> Value {
    match result {
        Ok(w) => json!([w.kind, w.begin, w.bytes, w.delta]),
        Err(err) => json!([err]),
    }
}

#[test]
fn all_integer_cases_match_frozen_independent_population() {
    let frozen: Value = serde_json::from_str(include_str!(
        "../../../../../docs/research/f020/m4c-aligned-transport/corpus.json"
    ))
    .unwrap();
    let mut hash = Sha256::new();
    let mut count = [0, 0];
    for a in [1, 2, 4, 8, 16, 4096, 16384] {
        let public = a >= 4096;
        let lengths: Vec<_> = if public {
            vec![a - 1, a, a + 1, 2 * a - 1, 2 * a, 2 * a + 1, 3 * a + 17]
        } else {
            (0..=2 * a + 1).collect()
        };
        let mut sizes = vec![0, 1, a - 1, a, a + 1, 2 * a + 1];
        sizes.sort_unstable();
        sizes.dedup();
        for l in lengths {
            let offsets: Vec<_> = if public {
                vec![0, 1, a - 1, a, a + 1, 2 * a - 1, 2 * a, 2 * a + 1]
            } else {
                (0..=l + 1).collect()
            };
            for o in offsets {
                for &n in &sizes {
                    let row = json!([a, l, o, n, shape(geometry(a, l, o, n, NATIVE))]);
                    count[public as usize] += 1;
                    hash.update(row.to_string());
                    hash.update(b"\n");
                    emit("integer", row);
                }
            }
        }
    }
    assert_eq!(count, [5489, 672]);
    assert_eq!(format!("{:x}", hash.finalize()), frozen["ordered_sha256"]);
    for row in frozen["named"].as_array().unwrap() {
        let args = &row[2];
        let arg = |i: usize| args[i].as_u64().unwrap();
        let scalar = |k: &str, r: std::result::Result<u64, &str>| match r {
            Ok(n) => json!([k, n]),
            Err(s) => json!([s]),
        };
        let result = match row[1].as_str().unwrap() {
            "geometry" => {
                shape(alignment(arg(0)).and_then(|a| geometry(a, arg(1), arg(2), arg(3), arg(4))))
            }
            "backing" => scalar("backing", backing(arg(0), arg(1), arg(2), arg(3))),
            "reservation" => scalar("reservation", reservation(arg(0), arg(1), arg(2))),
            _ => unreachable!(),
        };
        assert_eq!(result, row[3], "{row}");
        emit("named", row.clone());
    }
}

fn owned() -> Fixture {
    fixture(128, 64, 3, false, 0, true)
}
fn originals(plan: &ExpertPlan, role: ExpertRole) -> [Vec<u8>; 3] {
    let loaded = plan.load().unwrap();
    std::array::from_fn(|i| loaded.bytes(role.index(), i).unwrap().to_vec())
}
fn destination<'a>(parts: &'a mut [Vec<u8>; 3], hashes: [String; 3]) -> PlaneDestination<'a> {
    let [w, s, b] = parts;
    PlaneDestination::new(w, s, b, hashes)
}
fn parts(reference: &[Vec<u8>; 3]) -> [Vec<u8>; 3] {
    reference.each_ref().map(|r| vec![0xac; r.len()])
}
fn hashes(reference: &[Vec<u8>; 3]) -> [String; 3] {
    reference.each_ref().map(|r| digest(r))
}
fn effects(src: &BoundedSource) -> (u64, u64) {
    (src.payload_read_calls(), src.requested_payload_bytes())
}

#[test]
fn destination_hash_budget_and_control_refuse_before_io() {
    let f = owned();
    let src = BoundedSource::open(&f.root).unwrap();
    let mut plan = src.plan(f.request.clone()).unwrap();
    let reference = originals(&plan, Gate);
    for a in [0, 1, 2, 4, 8, 16, 1024, 8192, 12288, u64::MAX] {
        assert!(WindowPlan::new(&plan, Gate, a).is_err());
    }
    let w = WindowPlan::new(&plan, Gate, 4096).unwrap();
    let budget = w.minimum_reservation();
    assert!(Scratch::new(&w, budget - 1).is_err());
    assert_eq!(budget, w.minimum + CONTROL);
    for mode in ARM {
        for (name, phase) in [
            ("short", "DESTINATION"),
            ("large", "DESTINATION"),
            ("empty", "DESTINATION"),
            ("malformed", "CONTENT"),
            ("hash-capacity", "WINDOW"),
            ("budget", "WINDOW"),
            ("scratch", "WINDOW"),
        ] {
            let mut p = parts(&reference);
            let mut h = hashes(&reference);
            match name {
                "short" => {
                    p[2].pop();
                }
                "large" => p[1].push(0xac),
                "empty" => p[2].clear(),
                "malformed" => h[2].replace_range(0..1, "G"),
                "hash-capacity" => h[2].reserve_exact(CONTROL as usize),
                _ => (),
            }
            let mut scratch = Scratch::new(&w, budget).unwrap();
            if name == "scratch" {
                scratch.storage = vec![0; 3].into_boxed_slice();
            }
            let before = effects(&src);
            let input = p.clone();
            let err = w
                .read_with(
                    mode,
                    &mut scratch,
                    destination(&mut p, h),
                    budget - u64::from(name == "budget"),
                    |_, _, _| panic!("unexpected transfer"),
                )
                .err()
                .unwrap();
            assert_eq!(err.cause.phase, phase);
            assert_eq!(before, effects(&src));
            assert_eq!(input, p);
            assert_eq!(
                (
                    err.receipt.logical_attempts,
                    err.receipt.attempted,
                    err.receipt.published
                ),
                (0, 0, false)
            );
            emit("preflight", json!([name, phase, err.receipt]));
        }
    }
    plan.record.planes[0].module = "界".repeat(5000);
    assert!(WindowPlan::new(&plan, Gate, 4096).is_err());
    // Invalid geometry in the last component cannot be deferred until after the first read.
    plan.record.planes[0].module = "gate".into();
    plan.record.planes[0].ranges[2].begin = u64::MAX;
    let before = effects(&src);
    assert!(WindowPlan::new(&plan, Gate, 4096).is_err());
    assert_eq!(before, effects(&src));
}

#[test]
fn failures_at_all_positions_preserve_partial_and_completed_effects() {
    let f = owned();
    let src = BoundedSource::open(&f.root).unwrap();
    let plan = src.plan(f.request.clone()).unwrap();
    let reference = originals(&plan, Gate);
    let wp = WindowPlan::new(&plan, Gate, 4096).unwrap();
    let mut s = Scratch::new(&wp, u64::MAX).unwrap();
    for mode in ARM {
        for failed in 0..3 {
            for io_error in [true, false] {
                let before = effects(&src);
                let mut p = parts(&reference);
                let mut h = hashes(&reference);
                if !io_error {
                    h[failed] = "0".repeat(64);
                }
                let mut calls = 0;
                let err = wp
                    .read_with(
                        mode,
                        &mut s,
                        destination(&mut p, h),
                        u64::MAX,
                        |held, buf, offset| {
                            let i = calls;
                            calls += 1;
                            if i == failed && io_error {
                                buf[..2].fill(0xed);
                                return Err(io::ErrorKind::UnexpectedEof.into());
                            }
                            held.file.read_exact_at(buf, offset)
                        },
                    )
                    .err()
                    .unwrap();
                let r = err.receipt;
                assert_eq!(err.cause.phase, if io_error { "READ" } else { "CONTENT" });
                let done = failed + usize::from(!io_error);
                assert_eq!(calls, failed + 1);
                assert_eq!(r.attempted, calls as u64);
                assert!(!r.published);
                assert_eq!(
                    effects(&src),
                    (
                        before.0 + r.logical_attempts,
                        before.1 + r.logical_requested
                    )
                );
                assert_eq!(r.logical_attempts, r.attempted);
                assert_eq!(
                    r.requested,
                    r.transfers[..calls].iter().map(|w| w.bytes).sum::<u64>()
                );
                assert_eq!(
                    r.completed,
                    r.transfers[..done].iter().map(|w| w.bytes).sum::<u64>()
                );
                assert_eq!(
                    r.logical_delivered,
                    reference[..done]
                        .iter()
                        .map(|x| x.len() as u64)
                        .sum::<u64>()
                );
                assert_eq!(
                    r.copies,
                    r.transfers[..done]
                        .iter()
                        .filter(|w| w.kind == Kind::Window)
                        .count() as u64
                );
                for (i, e) in r.effects.iter().enumerate() {
                    assert_eq!(e.attempted, i < calls);
                    assert_eq!(e.returned_bytes, (i < done).then_some(r.transfers[i].bytes));
                    if i < done {
                        assert_eq!(p[i], reference[i]);
                    } else if i == failed && r.transfers[i].kind != Kind::Window {
                        assert_eq!(&p[i][..2], &[0xed; 2]);
                    } else {
                        assert!(p[i].iter().all(|&b| b == 0xac));
                    }
                }
                emit("partial", json!([failed, err.cause.phase, r]));
            }
        }
    }
}

#[test]
fn descriptor_component_role_and_window_remain_sealed() {
    let fa = owned();
    let fb = owned();
    let a = BoundedSource::open(&fa.root).unwrap();
    let b = BoundedSource::open(&fb.root).unwrap();
    assert_eq!(a.identity, b.identity);
    let p = a.plan(fa.request.clone()).unwrap();
    let other = b.plan(fb.request.clone()).unwrap();
    let alt = WindowPlan::new(&other, Gate, 4096).unwrap();
    for fault in ["descriptor", "role", "component", "raw-window"] {
        let mut wp = WindowPlan::new(&p, Gate, 4096).unwrap();
        assert_ne!(wp.binding, alt.binding);
        let mut scratch = Scratch::new(&wp, u64::MAX).unwrap();
        match fault {
            "descriptor" => wp.held[0] = alt.held[0],
            "role" => wp.role = Up,
            "component" => wp.windows.swap(0, 1),
            "raw-window" => wp.windows[0].begin += 4096,
            _ => unreachable!(),
        }
        let reference = originals(&p, wp.role);
        let mut dst = parts(&reference);
        let before = effects(&a);
        let fail = wp
            .read_with(
                BufferedAlignedWindow,
                &mut scratch,
                destination(&mut dst, hashes(&reference)),
                u64::MAX,
                |_, _, _| panic!("wrong binding reached transport"),
            )
            .err()
            .unwrap();
        assert_eq!(fail.cause.phase, "READ");
        let r = fail.receipt;
        assert_eq!(
            (r.logical_attempts, r.attempted, r.published),
            (1, 0, false)
        );
        assert_eq!(effects(&a), (before.0 + 1, before.1 + r.logical_requested));
        assert_eq!(dst, parts(&reference));
        emit("binding", json!([fault, r]));
    }
}

#[test]
fn retained_rename_corruption_and_truncation_have_distinct_outcomes() {
    for change in [
        "replaced-path",
        "corrupt-before-open",
        "truncate-before-read",
        "truncate-during-read",
    ] {
        let mut f = owned();
        let src = BoundedSource::open(&f.root).unwrap();
        let p = src.plan(f.request.clone()).unwrap();
        let original = originals(&p, Gate);
        let offset = p.record.planes[0].ranges[0].begin;
        let file = OpenOptions::new()
            .write(true)
            .open(f.root.join("model.safetensors"))
            .unwrap();
        if change == "corrupt-before-open" {
            file.write_all_at(&[0xf1], offset).unwrap();
        }
        let src = BoundedSource::open(&f.root).unwrap();
        let plan = src.plan(f.request.clone()).unwrap();
        let wp = WindowPlan::new(&plan, Gate, 4096).unwrap();
        let mut replacement = owned();
        if change == "replaced-path" {
            let old = f.root.clone();
            let moved = old.with_extension("held");
            fs::rename(&old, &moved).unwrap();
            f.root = moved;
            fs::rename(&replacement.root, &old).unwrap();
            replacement.root = old;
            let decoy = OpenOptions::new()
                .write(true)
                .open(replacement.root.join("model.safetensors"))
                .unwrap();
            decoy.write_all_at(&[0xf2], offset).unwrap();
        }
        if change == "truncate-before-read" {
            file.set_len(offset).unwrap();
        }
        let mut scratch = Scratch::new(&wp, u64::MAX).unwrap();
        let mut dst = parts(&original);
        let mut calls = 0;
        let result = wp.read_with(
            BufferedAlignedWindow,
            &mut scratch,
            destination(&mut dst, hashes(&original)),
            u64::MAX,
            |held, bytes, begin| {
                calls += 1;
                held.file.read_exact_at(bytes, begin)?;
                if change == "truncate-during-read" {
                    file.set_len(offset)?;
                }
                Ok(())
            },
        );
        if change == "replaced-path" {
            let (filled, r) = result.unwrap().into_parts();
            assert_eq!(filled.into_receipt().actual_sha256, hashes(&original));
            assert_eq!(dst, original);
            emit("mutation", json!([change, "success", r]));
        } else {
            let err = result.err().unwrap();
            let r = err.receipt;
            assert!(!r.published);
            assert_eq!(
                err.cause.phase,
                if change == "corrupt-before-open" {
                    "CONTENT"
                } else {
                    "MUTATION"
                }
            );
            assert_eq!(calls, usize::from(change != "truncate-before-read"));
            assert_eq!(r.attempted, calls as u64);
            assert_eq!(r.copies, calls as u64);
            emit("mutation", json!([change, err.cause.phase, r]));
        }
    }
}

#[test]
fn authored_layouts_verify_real_offsets_alignment_canaries_and_reuse() {
    for padded in [false, true] {
        let mut f = owned();
        // Keep an owned parent while admitting a long multibyte checkpoint basename.
        let parent = owned();
        let long = "窗口".repeat(36);
        let new = parent.root.join(&long);
        fs::rename(&f.root, &new).unwrap();
        f.root = new;
        if padded {
            let path = f.root.join("model.safetensors");
            let old = fs::read(&path).unwrap();
            let old_start = 8 + u64::from_le_bytes(old[..8].try_into().unwrap()) as usize;
            let mut next = old[..old_start].to_vec();
            next[..8].copy_from_slice(&16376u64.to_le_bytes());
            next.resize(16384, b' ');
            next.extend_from_slice(&old[old_start..]);
            fs::write(path, next).unwrap();
        }
        let src = BoundedSource::open(&f.root).unwrap();
        let p = src.plan(f.request.clone()).unwrap();
        let mut last = f.request.clone();
        last.expert = 2;
        let q = src.plan(last).unwrap();
        assert_eq!(p.record.checkpoint, long);
        let large = WindowPlan::new(&p, Gate, 16384).unwrap();
        let mut scratch = Scratch::new(&large, u64::MAX).unwrap();
        let ptr = scratch.storage.as_ptr();
        let cap = scratch.backing_bytes();
        let mut seen_prefix = false;
        let mut seen_sibling = false;
        let mut seen_exact = false;
        let mut seen_eof = false;
        let mut seen_edge = false;
        for (which, plan, role, a) in [
            ("A", &p, Gate, 16384),
            ("B", &q, Down, 4096),
            ("A", &p, Gate, 16384),
            ("exact-alignment", &p, Gate, 4096),
        ] {
            let wp = WindowPlan::new(plan, role, a).unwrap();
            let original = originals(plan, role);
            let ledger = wp.layout(&scratch);
            assert_eq!(ledger.backing_bytes, cap as u64);
            assert_eq!(ledger.head_slack + ledger.usable_bytes, cap as u64);
            assert_eq!(
                ledger.usable_bytes,
                ledger.largest_request + ledger.tail_slack
            );
            for mode in ARM {
                scratch.storage.fill(0xa5);
                let mut buffers = original.each_ref().map(|v| vec![0xeb; v.len() + 2]);
                let [w, s, b] = &mut buffers;
                fn inside(v: &mut [u8]) -> &mut [u8] {
                    let len = v.len();
                    &mut v[1..len - 1]
                }
                let dst = PlaneDestination::new(inside(w), inside(s), inside(b), hashes(&original));
                let mut observations = vec![];
                let mut i = 0;
                let (filled, receipt) = wp
                    .read_with(
                        mode,
                        &mut scratch,
                        dst,
                        cap as u64 + CONTROL,
                        |held, buf, at| {
                            let range = &plan.record.planes[role.index()].ranges[i];
                            let end = range.begin + range.len;
                            let low = range.begin / a * a;
                            let upper = end.div_ceil(a) * a;
                            let aligned = mode == BufferedAlignedWindow && upper <= held.stamp.len;
                            let (expected, n) = if aligned {
                                (low, upper - low)
                            } else {
                                (range.begin, range.len)
                            };
                            assert_eq!((at, buf.len() as u64), (expected, n));
                            if aligned {
                                assert_eq!(buf.as_ptr() as usize % a as usize, 0);
                                assert_eq!(
                                    buf.as_ptr() as usize,
                                    ptr as usize + ledger.head_slack as usize
                                );
                            }
                            held.file.read_exact_at(buf, at)?;
                            if aligned && at == 0 && range.begin > 8 {
                                seen_prefix = true;
                            }
                            if aligned
                                && at + n > end
                                && bytes_beyond_role(buf, (end - at) as usize, original[i][0])
                            {
                                seen_sibling = true;
                            }
                            seen_exact |= aligned && (at, n) == (range.begin, range.len);
                            seen_eof |= end == held.stamp.len;
                            seen_edge |= mode == BufferedAlignedWindow && upper > held.stamp.len;
                            observations.push(json!([at, n, range.begin, range.len, aligned]));
                            i += 1;
                            Ok(())
                        },
                    )
                    .unwrap()
                    .into_parts();
                let old = filled.into_receipt();
                assert_eq!(old.actual_sha256, hashes(&original));
                assert_eq!(scratch.storage.as_ptr(), ptr);
                for (buf, item) in buffers.iter().zip(&original) {
                    assert_eq!(buf[0], 0xeb);
                    assert_eq!(*buf.last().unwrap(), 0xeb);
                    assert_eq!(&buf[1..buf.len() - 1], item);
                }
                let head = ledger.head_slack as usize;
                let stop = head + ledger.largest_request as usize;
                assert!(scratch.storage[..head]
                    .iter()
                    .chain(&scratch.storage[stop..])
                    .all(|&b| b == 0xa5));
                if mode == BufferedExact {
                    assert!(scratch.storage.iter().all(|&b| b == 0xa5));
                }
                assert!(serde_json::to_vec(&receipt).unwrap().len() <= RECORD_LIMIT);
                assert!(
                    serde_json::to_vec(&old).unwrap().len() as u64 + (RECORD_LIMIT as u64)
                        < receipt.ledger.control_required
                );
                emit(
                    "layout",
                    json!([padded, which, long.len(), old.role, observations, receipt]),
                );
            }
        }
        assert!(seen_eof && seen_edge && seen_sibling);
        if padded {
            assert!(seen_exact);
        } else {
            assert!(seen_prefix);
        }
        drop(f);
    }
}
fn bytes_beyond_role(bytes: &[u8], start: usize, marker: u8) -> bool {
    bytes[start..].iter().any(|&b| b != marker)
}
