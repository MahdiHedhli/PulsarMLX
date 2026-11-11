mod residency_support;
mod support;
use mlx_expert_ranges::{residency::*, BoundedSource, ExpertRequest};
use residency_support::*;
use sha2::{Digest, Sha256};
use std::{cell::Cell, fs};

#[test]
fn both_recipes_ordered_cold_warm_and_protected_wave_reload() {
    for mixed in [false, true] {
        let (f, mut cache) = setup(mixed);
        let control = BoundedSource::open(&f.root).unwrap();
        let mut order = vec![];
        let mut locations = vec![];
        let demand = [0, 1, 0, 2, 1, 0].map(|i| cache.demand(i).unwrap());
        cache
            .consume(
                &demand,
                || false,
                |view| {
                    let expert = view.demand.key.expert;
                    let tuple = control
                        .plan(ExpertRequest {
                            expert: u64::from(expert),
                            ..f.request.clone()
                        })?
                        .load()?;
                    for (r, plane) in view.components.iter().enumerate() {
                        for (c, bytes) in plane.iter().enumerate() {
                            let expected = component(f.request.bits, expert, r, c);
                            assert_eq!(*bytes, expected);
                            assert_eq!(Some(*bytes), tuple.bytes(r, c));
                            assert_eq!(
                                view.hashes[r][c],
                                <[u8; 32]>::from(Sha256::digest(&expected))
                            );
                        }
                    }
                    order.push(expert);
                    locations.push((view.slot.0, view.generation, view.components[0][0].as_ptr()));
                    Ok(())
                },
            )
            .unwrap();
        assert_eq!(order, [0, 1, 0, 2, 1, 0]);
        assert_eq!(locations[0], locations[2]);
        assert_eq!(locations[1], locations[4]);
        assert_eq!(
            locations.iter().map(|l| l.0).collect::<Vec<_>>(),
            [0, 1, 0, 0, 1, 0]
        );
        assert!(locations[5].1 > locations[3].1);
        assert_eq!(
            cache.stats(),
            CacheStats {
                fills: 4,
                hits: 2,
                evictions: 2,
                consumed: 6
            }
        );
        assert_eq!((cache.read_calls(), control.payload_read_calls()), (36, 54));
        let l = cache.ledger();
        assert_eq!(cache.resident_bytes(), 2 * l.tuple_bytes);
        assert_eq!(cache.requested_bytes(), 4 * l.tuple_bytes);
        assert_eq!(
            cache.working_bytes(),
            2 * l.tuple_bytes + l.metadata_bytes + CONTROL_BYTES + WORKSPACE_BYTES
        );
        cache
            .consume(
                &demand[..1],
                || false,
                |view| {
                    assert_eq!(locations[5].2, view.components[0][0].as_ptr());
                    Ok(())
                },
            )
            .unwrap();
        assert_eq!(cache.read_calls(), 36);
        cache.finish().unwrap();
        println!(
            "recipe={:?} tuple={} metadata={} control_bound={} W={} reads=36 control_reads=54",
            f.request.bits, l.tuple_bytes, l.metadata_bytes, l.control_bound, l.working_bytes
        );
    }
}

#[test]
fn full_demand_admission_precedes_all_reads_and_evictions() {
    let (_f, mut cache) = setup(false);
    let a = cache.demand(0).unwrap();
    let b = cache.demand(1).unwrap();
    cache.consume(&[a, b], || false, |_| Ok(())).unwrap();
    let before = (cache.read_calls(), cache.stats(), cache.resident_bytes());
    let c = cache.demand(2).unwrap();
    let mut crossed = a;
    crossed.binding[0] ^= 1;
    let (_, other) = setup(true);
    let mut wrong_layer = a;
    wrong_layer.key.layer += 1;
    for d in [
        vec![],
        vec![a; 65],
        vec![c, a, crossed],
        vec![c, other.demand(0).unwrap()],
        vec![wrong_layer],
    ] {
        assert!(cache
            .consume(&d, || false, |_| panic!("unexpected consumer"))
            .is_err());
        assert_eq!(
            before,
            (cache.read_calls(), cache.stats(), cache.resident_bytes())
        );
    }
    assert!(cache.demand(3).is_err());
    assert!(parse_hash(&"X".repeat(64)).is_err());
}

#[test]
fn incorrect_final_digest_never_publishes_partial_tuple() {
    let f = support::fixture(128, 64, 3, false, 0, true);
    let source = BoundedSource::open(&f.root).unwrap();
    let meta = source.metadata_snapshot().to_owned();
    let mut expected = hashes(f.request.bits);
    expected[2][2][2][0] ^= 1;
    let mut cache = CopiedResidency::new(
        source,
        7,
        &f.request,
        ContentAuthority {
            checkpoint: f.root.file_name().unwrap().to_str().unwrap(),
            metadata: &meta,
            content: CONTENT,
            hashes: &expected,
        },
        u64::MAX,
        0,
    )
    .unwrap();
    let a = cache.demand(0).unwrap();
    let b = cache.demand(1).unwrap();
    let c = cache.demand(2).unwrap();
    cache.consume(&[a, b], || false, |_| Ok(())).unwrap();
    let e = cache
        .consume(&[c, b], || false, |_| panic!("partial publication"))
        .unwrap_err();
    assert_eq!(e.primary.phase, "CONTENT");
    assert_eq!(cache.read_calls(), 27);
    assert_eq!(cache.resident_bytes(), cache.ledger().tuple_bytes);
    cache.finish().unwrap();
    cache.consume(&[b], || false, |_| Ok(())).unwrap();
    assert_eq!(cache.read_calls(), 27);
}

#[test]
fn stale_descriptors_refuse_both_hits_and_misses() {
    let (f, mut c) = setup(false);
    let a = c.demand(0).unwrap();
    c.consume(&[a], || false, |_| Ok(())).unwrap();
    fs::OpenOptions::new()
        .write(true)
        .open(f.root.join("model.safetensors"))
        .unwrap()
        .set_len(32)
        .unwrap();
    for v in [a, c.demand(1).unwrap()] {
        let e = c.consume(&[v], || false, |_| panic!()).unwrap_err();
        assert_eq!(e.primary.phase, "MUTATION");
    }
    assert_eq!(c.read_calls(), 9);
    c.finish().unwrap();
}

#[test]
fn cancellation_drains_roles_and_only_complete_entries_survive() {
    for (stop, reads, occupied) in [
        (1, 0, false),
        (4, 3, false),
        (5, 6, false),
        (6, 9, false),
        (7, 9, true),
    ] {
        let (_f, mut cache) = setup(false);
        let a = cache.demand(0).unwrap();
        let polls = Cell::new(0);
        let err = cache
            .consume(
                &[a],
                || {
                    polls.set(polls.get() + 1);
                    polls.get() == stop
                },
                |_| panic!("cancelled occurrence"),
            )
            .unwrap_err();
        assert_eq!(err.primary.phase, "CANCELLED");
        assert_eq!(cache.read_calls(), reads);
        assert_eq!(cache.resident_bytes() > 0, occupied);
        cache.finish().unwrap();
    }
    let (_f, mut cache) = setup(false);
    let a = cache.demand(0).unwrap();
    let seen = Cell::new(0);
    cache
        .consume(
            &[a, a],
            || seen.get() == 1,
            |_| {
                seen.set(seen.get() + 1);
                Ok(())
            },
        )
        .unwrap_err();
    assert_eq!(seen.get(), 1);
    assert_eq!(cache.stats().consumed, 1);
    cache.finish().unwrap();
}

#[test]
fn invalid_class_metadata_and_memory_are_rejected_before_filling() {
    let f = support::fixture(128, 64, 3, false, 0, true);
    for (key, expected_phase) in [
        ("name", "RESOLVE"),
        ("shape", "GEOMETRY"),
        ("role", "MODULE"),
        ("bits", "RECIPE"),
        ("metadata", "SOURCE"),
        ("budget", "BUDGET"),
        ("workspace", "BUDGET"),
        ("control", "BUDGET"),
    ] {
        let source = BoundedSource::open(&f.root).unwrap();
        let mut r = f.request.clone();
        let mut meta = source.metadata_snapshot().to_owned();
        match key {
            "name" => r.modules[1] = "foreign".into(),
            "shape" => r.h = 128,
            "role" => r.modules.swap(0, 2),
            "bits" => r.bits[0] = 8,
            "metadata" => meta.clear(),
            "control" => r.modules[0] = "x".repeat(12000),
            _ => {}
        }
        if key == "role" {
            r.modules[0] = r.modules[1].clone();
        }
        let err = CopiedResidency::new(
            source,
            7,
            &r,
            ContentAuthority {
                checkpoint: f.root.file_name().unwrap().to_str().unwrap(),
                metadata: &meta,
                content: CONTENT,
                hashes: &hashes(f.request.bits),
            },
            if key == "budget" { 1 } else { u64::MAX },
            if key == "workspace" {
                WORKSPACE_BYTES + 1
            } else {
                0
            },
        )
        .err()
        .unwrap();
        assert_eq!(err.phase, expected_phase, "{key}");
    }
    let source = BoundedSource::open(&f.root).unwrap();
    let initial = source.logical_metadata_bytes().unwrap();
    let p = f.root.join("config.json");
    let mut v: serde_json::Value = serde_json::from_slice(&fs::read(&p).unwrap()).unwrap();
    v["extra"] = serde_json::json!(["longer", 1]);
    fs::write(p, v.to_string()).unwrap();
    let after = BoundedSource::open(&f.root).unwrap();
    assert_eq!(
        after.logical_metadata_bytes().unwrap() - initial,
        (std::mem::size_of::<(String, serde_json::Value)>()
            + 5
            + 2 * std::mem::size_of::<serde_json::Value>()
            + 6) as u64
    );
    assert_eq!(after.payload_read_calls(), 0);
}

#[test]
fn trusted_checkpoint_and_content_bindings_precede_warm_reuse() {
    let (f, mut cache) = setup(false);
    let make = |name: &str, content| {
        let source = BoundedSource::open(&f.root).unwrap();
        let meta = source.metadata_snapshot().to_owned();
        CopiedResidency::new(
            source,
            7,
            &f.request,
            ContentAuthority {
                checkpoint: name,
                metadata: &meta,
                content,
                hashes: &hashes(f.request.bits),
            },
            u64::MAX,
            0,
        )
    };
    assert_eq!(
        make("different-checkpoint", CONTENT).err().unwrap().phase,
        "SOURCE"
    );
    let other = make(f.root.file_name().unwrap().to_str().unwrap(), [0x43; 32]).unwrap();
    let a = cache.demand(0).unwrap();
    cache.consume(&[a], || false, |_| Ok(())).unwrap();
    assert_eq!(cache.read_calls(), 9);
    let before = cache.stats();
    assert!(cache
        .consume(&[a, other.demand(0).unwrap()], || false, |_| panic!())
        .is_err());
    assert_eq!(cache.stats(), before);
    assert_eq!(cache.read_calls(), 9);
}

#[test]
fn mutation_after_first_plane_withholds_the_tuple() {
    let (f, mut cache) = setup(false);
    let a = cache.demand(0).unwrap();
    let mut polls = 0;
    let err = cache
        .consume(
            &[a],
            || {
                polls += 1;
                if polls == 4 {
                    fs::OpenOptions::new()
                        .write(true)
                        .open(f.root.join("model.safetensors"))
                        .unwrap()
                        .set_len(8)
                        .unwrap();
                }
                false
            },
            |_| panic!("partly filled tuple exposed"),
        )
        .unwrap_err();
    assert_eq!(err.primary.phase, "MUTATION");
    assert_eq!(cache.read_calls(), 3);
    assert_eq!(cache.resident_bytes(), 0);
    cache.finish().unwrap();
}

#[test]
fn metadata_counts_separate_catalog_header_and_index_names() {
    use std::os::unix::fs::FileExt;
    let f = support::fixture(128, 64, 3, false, 0, true);
    let original = BoundedSource::open(&f.root)
        .unwrap()
        .logical_metadata_bytes()
        .unwrap();
    let file = fs::OpenOptions::new()
        .read(true)
        .write(true)
        .open(f.root.join("model.safetensors"))
        .unwrap();
    let mut prefix = [0; 8];
    file.read_exact_at(&mut prefix, 0).unwrap();
    let n = u64::from_le_bytes(prefix) as usize;
    let mut data = fs::read(f.root.join("model.safetensors")).unwrap();
    let header = String::from_utf8(data[8..8 + n].to_vec())
        .unwrap()
        .replace("fixture.gate.", "fixture.longgate.");
    let payload = data.split_off(8 + n);
    drop(data);
    file.set_len(0).unwrap();
    file.write_all_at(&(header.len() as u64).to_le_bytes(), 0)
        .unwrap();
    file.write_all_at(header.as_bytes(), 8).unwrap();
    file.write_all_at(&payload, 8 + header.len() as u64)
        .unwrap();
    let index = f.root.join("model.safetensors.index.json");
    fs::write(
        &index,
        fs::read_to_string(&index)
            .unwrap()
            .replace("fixture.gate.", "fixture.longgate."),
    )
    .unwrap();
    let source = BoundedSource::open(&f.root).unwrap();
    // Three tensors, four added characters, five retained copies of each name.
    assert_eq!(
        source.logical_metadata_bytes().unwrap() - original,
        3 * 4 * 5
    );
    assert_eq!(source.payload_read_calls(), 0);
}

#[test]
fn unsupported_rank_refuses_while_shape_is_borrowed() {
    let f = support::fixture(128, 64, 3, false, 0, true);
    let file = f.root.join("model.safetensors");
    let bytes = fs::read(&file).unwrap();
    let n = u64::from_le_bytes(bytes[..8].try_into().unwrap()) as usize;
    let mut header: serde_json::Value = serde_json::from_slice(&bytes[8..8 + n]).unwrap();
    let shape = header["fixture.gate.weight"]["shape"]
        .as_array_mut()
        .unwrap();
    for _ in 0..128 {
        shape.insert(0, 1.into());
    }
    let raw = serde_json::to_vec(&header).unwrap();
    fs::write(
        file,
        [&(raw.len() as u64).to_le_bytes()[..], &raw, &bytes[8 + n..]].concat(),
    )
    .unwrap();
    let source = BoundedSource::open(&f.root).unwrap();
    let meta = source.metadata_snapshot().to_owned();
    let result = CopiedResidency::new(
        source,
        7,
        &f.request,
        ContentAuthority {
            checkpoint: f.root.file_name().unwrap().to_str().unwrap(),
            metadata: &meta,
            content: CONTENT,
            hashes: &hashes(f.request.bits),
        },
        u64::MAX,
        0,
    );
    assert_eq!(result.err().unwrap().phase, "GEOMETRY");
}
