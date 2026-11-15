//! The parity ledger of this workspace, checked with the test kit's ledger helper (work
//! package API-19): its structure (contract sections 3 and 5), every Rust test a row names
//! found in its crate's sources, and the row counts of the eight API-reader files, which a
//! reviewer reproduces from the pinned donor files with `console/tools/list_donor_tests.py`.
//!
//! These are tests of the ledger itself, not re-expressions of donor methods.

use std::path::Path;

use console_testkit::ledger::{
    load, missing_from_source, structure_problems, workspace_ledger_path, workspace_root, Ledger,
};

fn ledger() -> Ledger {
    let path = workspace_ledger_path(Path::new(env!("CARGO_MANIFEST_DIR")));
    match load(&path) {
        Ok(l) => l,
        Err(e) => panic!("{}: {e}", path.display()),
    }
}

#[test]
fn the_ledger_is_well_formed() {
    let l = ledger();
    assert_eq!(
        l.count(),
        Some(913),
        "913 donor methods at the pinned commit"
    );
    assert_eq!(l.rows.len(), 913);
    let problems = structure_problems(&l);
    assert!(problems.is_empty(), "{problems:#?}");
}

#[test]
fn every_named_rust_test_exists_in_its_crate() {
    let l = ledger();
    let crates = workspace_root(Path::new(env!("CARGO_MANIFEST_DIR"))).join("crates");
    let missing = missing_from_source(&l, &crates);
    assert!(missing.is_empty(), "{missing:#?}");
}

/// The API reader's eight files and their method counts at 7e68a30f: 244 methods in all,
/// as the planner's detail for API-19 counts them.
const API_READER_FILES: [(&str, usize); 8] = [
    ("serve/test_server.py", 145),
    ("serve/test_stream_jobs.py", 8),
    ("serve/test_stop.py", 15),
    ("serve/test_logprobs.py", 19),
    ("serve/test_multi.py", 15),
    ("serve/test_fair.py", 14),
    ("serve/test_turbo.py", 25),
    ("serve/test_detok.py", 3),
];

#[test]
fn the_api_reader_files_have_their_244_rows() {
    let l = ledger();
    let mut total = 0;
    for (file, n) in API_READER_FILES {
        let rows = l.rows_of_file(file).count();
        assert_eq!(rows, n, "{file}");
        total += rows;
    }
    assert_eq!(total, 244);
    // The related dashboard file, whose route methods the reader also assigns.
    assert_eq!(l.rows_of_file("serve/test_dashboard.py").count(), 54);
}
