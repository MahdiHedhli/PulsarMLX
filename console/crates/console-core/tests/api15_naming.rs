//! API-15: `EnvSettings` and the name table of contracts/naming.md agree (decision B2,
//! reconciliation R4). The contract is read from the repository through a path relative to
//! `CARGO_MANIFEST_DIR`. The check covers section 3.1 (server settings), section 3.2 (the
//! Responses limits), section 3.3 (no legacy alias is read) and the run-config key of
//! section 3.11.

use std::collections::BTreeSet;
use std::path::PathBuf;

use console_core::config::{EnvSettings, EnvSource, ENV_PREFIX, RESPONSES_LIMITS, SERVER_SETTINGS};

fn naming_md() -> String {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../specs/022-console-serving-parity/contracts/naming.md");
    std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()))
}

/// The table rows of the section whose heading starts with `heading` and a space (so that
/// "### 3.1" is not "### 3.10"): the cells of every line that starts with "| `", up to the
/// next heading.
fn rows(doc: &str, heading: &str) -> Vec<Vec<String>> {
    let mut inside = false;
    let mut out = Vec::new();
    for line in doc.lines() {
        if line.starts_with("### ") || line.starts_with("## ") {
            inside = line
                .strip_prefix(heading)
                .is_some_and(|rest| rest.starts_with(' '));
            continue;
        }
        if inside && line.starts_with("| `") {
            out.push(
                line.trim_matches('|')
                    .split('|')
                    .map(|c| c.trim().to_string())
                    .collect(),
            );
        }
    }
    out
}

/// The text between the first pair of backticks of a cell, or `None` (for example "none").
fn ticked(cell: &str) -> Option<String> {
    let start = cell.find('`')?;
    let rest = cell.get(start + 1..)?;
    let end = rest.find('`')?;
    rest.get(..end).map(str::to_string)
}

#[test]
fn server_settings_table_and_env_settings_agree() {
    let doc = naming_md();
    let table = rows(&doc, "### 3.1");
    assert!(!table.is_empty(), "section 3.1 has rows");
    let mut read: BTreeSet<(String, String)> = BTreeSet::new();
    let mut removed: Vec<String> = Vec::new();
    for row in &table {
        let old = ticked(&row[0]).expect("old name");
        let status = row.get(2).cloned().unwrap_or_default();
        match ticked(&row[1]) {
            Some(new) => {
                assert!(
                    status.starts_with("Mechanical") || status.starts_with("Decided"),
                    "{old}: {status}"
                );
                read.insert((new, old));
            }
            None => {
                assert!(status.starts_with("Removed"), "{old}: {status}");
                removed.push(old);
            }
        }
    }
    let code: BTreeSet<(String, String)> = SERVER_SETTINGS
        .iter()
        .map(|s| (s.name.to_string(), s.donor.to_string()))
        .collect();
    assert_eq!(
        code, read,
        "SERVER_SETTINGS and naming.md section 3.1 differ"
    );
    // A removed name is not read under its mechanical new name either (SEC-7.1).
    for old in removed {
        let mechanical = format!("{ENV_PREFIX}{}", old.trim_start_matches("MAYA_"));
        assert!(
            SERVER_SETTINGS
                .iter()
                .all(|s| s.name != mechanical && s.donor != old),
            "{old} is removed but read"
        );
    }
}

#[test]
fn responses_limits_table_and_env_settings_agree() {
    let doc = naming_md();
    let table: BTreeSet<(String, String)> = rows(&doc, "### 3.2")
        .iter()
        .filter_map(|r| Some((ticked(&r[1])?, ticked(&r[0])?)))
        .collect();
    let code: BTreeSet<(String, String)> = RESPONSES_LIMITS
        .iter()
        .map(|l| (l.name.to_string(), l.donor.to_string()))
        .collect();
    assert_eq!(code, table);
}

#[test]
fn no_legacy_name_is_read() {
    struct Recording(std::cell::RefCell<Vec<String>>);
    impl EnvSource for Recording {
        fn var(&self, name: &str) -> Option<String> {
            self.0.borrow_mut().push(name.to_string());
            None
        }
    }
    let rec = Recording(std::cell::RefCell::new(Vec::new()));
    let _ = EnvSettings::from_env(&rec);
    let asked = rec.0.borrow();
    assert!(!asked.is_empty());
    for name in asked.iter() {
        assert!(name.starts_with(ENV_PREFIX), "{name}");
        assert!(
            !name.starts_with("MAYA_") && !name.starts_with("STRATA_"),
            "{name}"
        );
    }
    // Section 3.3 records both legacy families as removed.
    let doc = naming_md();
    let legacy = rows(&doc, "### 3.3");
    assert!(legacy.iter().all(|r| r[2].starts_with("Removed")));
}

#[test]
fn the_allowed_hosts_key_is_recorded() {
    let doc = naming_md();
    let section: String = doc
        .split("### 3.11")
        .nth(1)
        .and_then(|s| s.split("## 4.").next())
        .unwrap_or_default()
        .to_string();
    assert!(section.contains("`allowed_hosts`"));
    assert!(section.contains("Read from the run config by API-15"));
}
