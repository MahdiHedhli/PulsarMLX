//! CNF-04: the normalizer and the comparator against the committed contracts.
//!
//! - every entry of `contracts/volatile-fields.json` is one the normalizer can apply
//!   (it refuses to build otherwise), and each carries a donor citation;
//! - the reader of `contracts/deviations.md` finds exactly the approved ids: the SEC,
//!   PRIV, BRAND, LIC, POL, PLAT, FIX and PLAN ids with their sub-items and the approved
//!   proposals P-1 to P-4, P-6 to P-11 and P-13 to P-16; it keeps P-12 and P-17 as
//!   declined and P-5 and P-18 to P-25 as awaiting the owner;
//! - an entry with a location the normalizer cannot apply refuses to build it.
//!
//! No donor test method is re-expressed here: CNF-04 owns none.

use std::path::PathBuf;

use console_conformance::compare::{ApprovedIds, IdStatus};
use console_conformance::normalize::Normalizer;
use console_conformance::scenario::{
    load_rename_map, load_volatile_fields, Location, RenameMap, VolatileClass, VolatileField,
    VolatileFields,
};

fn contracts() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../specs/022-console-serving-parity/contracts")
}

fn renames() -> RenameMap {
    load_rename_map(&contracts().join("rename-map.json")).unwrap_or_else(|e| panic!("{e}"))
}

fn volatile() -> VolatileFields {
    load_volatile_fields(&contracts().join("volatile-fields.json"))
        .unwrap_or_else(|e| panic!("{e}"))
}

#[test]
fn every_volatile_field_is_applied_and_cited() {
    let list = volatile();
    let n = Normalizer::new(&list, renames()).unwrap_or_else(|e| panic!("{e}"));
    let ids: Vec<&str> = n.field_ids().collect();
    assert_eq!(ids.len(), list.fields.len());
    for f in &list.fields {
        assert!(!f.donor.is_empty(), "{} has no donor citation", f.id);
        assert!(
            f.donor.iter().all(|d| d.starts_with("serve/")),
            "{}: {:?}",
            f.id,
            f.donor
        );
    }
    // the fields the review added
    for id in [
        "status-elapsed",
        "status-tokens-per-s",
        "status-tokens-per-s-mean",
        "id-answer-file",
        "answer-done",
        "update-checked",
        "pull-bytes-per-s",
        "tmp-model-path",
        "tmp-model-folder",
        "log-done-figures",
        "log-progress-prompt",
        "log-progress-decode",
        "log-still-starting",
        "log-queue-waited",
    ] {
        assert!(ids.contains(&id), "{id}");
    }
    // live-elapsed was made redundant by the parentless status-elapsed and removed
    assert!(!ids.contains(&"live-elapsed"));
}

#[test]
fn an_entry_the_normalizer_cannot_apply_refuses_to_build_it() {
    let base = volatile();
    let cases = [
        (VolatileClass::Num, Location::Header { name: "X".into() }),
        (
            VolatileClass::Id,
            Location::JsonKey {
                key: "id".into(),
                parent: None,
                value_type: None,
            },
        ),
        (
            VolatileClass::Pid,
            Location::FileName {
                pattern: "kept-<name>.json".into(),
            },
        ),
        (
            VolatileClass::Id,
            Location::FileName {
                pattern: "kept-<pid>.json".into(),
            },
        ),
        (
            VolatileClass::Port,
            Location::LogText {
                pattern: "listening on <host>".into(),
            },
        ),
        (VolatileClass::Iso, Location::Metric { name: "m".into() }),
        // a figure pattern has only <num> holes, a port pattern no <num> hole, and a
        // file name never takes a <num> hole
        (
            VolatileClass::Num,
            Location::LogText {
                pattern: "took <port> s".into(),
            },
        ),
        (
            VolatileClass::Num,
            Location::LogText {
                pattern: "no holes here".into(),
            },
        ),
        (
            VolatileClass::Port,
            Location::LogText {
                pattern: "ready <port> in <num> s".into(),
            },
        ),
        (
            VolatileClass::Pid,
            Location::FileName {
                pattern: "kept-<num>.json".into(),
            },
        ),
    ];
    for (class, location) in cases {
        let mut list = base.clone();
        list.fields.push(VolatileField {
            id: "extra".into(),
            class,
            location: location.clone(),
            donor: vec!["serve/server.py:1".into()],
            note: None,
        });
        assert!(
            Normalizer::new(&list, renames()).is_err(),
            "{class:?} at {location:?} was accepted"
        );
    }
}

fn register() -> ApprovedIds {
    let text = std::fs::read_to_string(contracts().join("deviations.md"))
        .unwrap_or_else(|e| panic!("{e}"));
    ApprovedIds::from_register(&text).unwrap_or_else(|e| panic!("{e}"))
}

#[test]
fn the_register_index_gives_the_approved_ids() {
    let ids = register();
    let entries: Vec<&str> = ids.approved_entries().collect();
    let mut want: Vec<String> = Vec::new();
    for n in 1..=7 {
        want.push(format!("SEC-{n}"));
    }
    want.extend(["PRIV-1", "BRAND-1", "BRAND-2", "LIC-1", "LIC-2", "POL-1"].map(String::from));
    for n in 1..=3 {
        want.push(format!("PLAT-{n}"));
    }
    want.push("FIX-1".into());
    for n in 1..=6 {
        want.push(format!("PLAN-{n}"));
    }
    for n in [1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16] {
        want.push(format!("P-{n}"));
    }
    want.sort();
    let mut got: Vec<String> = entries.iter().map(|s| s.to_string()).collect();
    got.sort();
    assert_eq!(got, want);
    for sub in [
        "SEC-1.1",
        "SEC-1.5",
        "BRAND-1.2",
        "BRAND-2.5",
        "FIX-1.3",
        "PLAT-3.3",
        "POL-1.3",
    ] {
        assert_eq!(ids.status(sub), IdStatus::Approved, "{sub}");
    }
    assert_eq!(ids.status("SEC-1.9"), IdStatus::Unknown);
    for declined in ["P-12", "P-17"] {
        assert_eq!(ids.status(declined), IdStatus::Declined, "{declined}");
    }
    for waiting in [
        "P-5", "P-18", "P-19", "P-20", "P-21", "P-22", "P-23", "P-24", "P-25",
    ] {
        assert_eq!(ids.status(waiting), IdStatus::AwaitingOwner, "{waiting}");
    }
    assert_eq!(ids.status("P-26"), IdStatus::Unknown);
}

#[test]
fn every_rename_entry_cites_an_approved_id() {
    // the reference side is renamed only under approved deviations
    let ids = register();
    for e in renames().applicable() {
        assert!(
            ids.is_approved(&e.deviation),
            "{} cites {}",
            e.old,
            e.deviation
        );
    }
}
