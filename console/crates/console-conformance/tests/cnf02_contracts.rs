//! CNF-02: the three contract files this package owns agree with the code and with the
//! documents they are derived from.
//!
//! - `contracts/conformance-scenario.schema.json` documents exactly the members and
//!   required members the loader enforces (`scenario::schema::SCHEMA_OBJECTS`).
//! - `contracts/rename-map.json` loads, and every entry and exclusion is checked against
//!   the row of `contracts/naming.md` it is derived from (status, new value), every
//!   rename row of naming.md section 3 is covered, and every deviation it cites is an
//!   approved id of `contracts/deviations.md`.
//! - `contracts/volatile-fields.json` loads, covers every category of
//!   `contracts/parity-ledger.md` section 1.1, and keeps header names observable.
//!
//! The documents are read from the repository; nothing is fetched or executed.

use std::collections::BTreeSet;
use std::fs;
use std::path::PathBuf;

use console_conformance::scenario::schema::SCHEMA_OBJECTS;
use console_conformance::scenario::{
    load_rename_map, load_volatile_fields, Location, RenameMap, Status, VolatileClass,
};

fn contracts() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../specs/022-console-serving-parity/contracts")
}

fn read(name: &str) -> String {
    let path = contracts().join(name);
    fs::read_to_string(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()))
}

// ------------------------------------------------------------------ schema

fn names(v: &serde_json::Value) -> Vec<String> {
    match v {
        serde_json::Value::Array(items) => items
            .iter()
            .filter_map(|i| i.as_str().map(str::to_string))
            .collect(),
        serde_json::Value::Object(map) => map.keys().cloned().collect(),
        _ => Vec::new(),
    }
}

#[test]
fn schema_file_matches_the_loader_table() {
    let schema: serde_json::Value =
        serde_json::from_str(&read("conformance-scenario.schema.json")).expect("schema JSON");
    assert_eq!(
        schema["$schema"],
        "https://json-schema.org/draft/2020-12/schema"
    );
    let defs = schema["$defs"].as_object().expect("$defs");
    let mut documented = BTreeSet::new();
    for (name, def) in defs {
        let Some(props) = def.get("properties") else {
            continue;
        };
        documented.insert(name.clone());
        let object = SCHEMA_OBJECTS
            .iter()
            .find(|o| o.name == name)
            .unwrap_or_else(|| panic!("$defs/{name} has no loader table entry"));
        assert_eq!(names(props), object.properties, "$defs/{name} properties");
        let mut required = names(&def["required"]);
        let mut want: Vec<String> = object.required.iter().map(|s| s.to_string()).collect();
        required.sort();
        want.sort();
        assert_eq!(required, want, "$defs/{name} required");
        assert_eq!(
            def["additionalProperties"], false,
            "$defs/{name} must refuse unknown members"
        );
        assert_eq!(def["type"], "object", "$defs/{name}");
    }
    for object in SCHEMA_OBJECTS {
        assert!(
            documented.contains(object.name),
            "{} is not documented in the schema",
            object.name
        );
    }
    assert_eq!(schema["$ref"], "#/$defs/scenario");
}

// ------------------------------------------------------------------ naming.md

/// One body row of a naming.md section 3 table.
struct Row {
    section: String,
    first: String,
    new: String,
    status: String,
}

fn naming_rows() -> Vec<Row> {
    let text = read("naming.md");
    let mut rows = Vec::new();
    let mut section: Option<String> = None;
    for line in text.lines() {
        if let Some(rest) = line.strip_prefix("### ") {
            section = rest.split_whitespace().next().map(str::to_string);
            continue;
        }
        if line.starts_with("## ") {
            section = None;
            continue;
        }
        let Some(sec) = &section else { continue };
        if !line.starts_with('|') || line.starts_with("| Old name") || line.starts_with("| ---") {
            continue;
        }
        let cells: Vec<String> = line
            .trim_matches('|')
            .split('|')
            .map(|c| c.trim().to_string())
            .collect();
        if cells.len() < 3 {
            continue;
        }
        rows.push(Row {
            section: sec.clone(),
            first: cells[0].clone(),
            new: cells[1].clone(),
            status: cells[2].clone(),
        });
    }
    rows
}

/// The rename-map status a naming.md status cell implies, if it is a rename at all.
fn implied_status(cell: &str) -> Option<Status> {
    let s = cell.to_ascii_lowercase();
    if s.starts_with("mechanical") {
        Some(Status::Mechanical)
    } else if s.contains("value open") || s.starts_with("open") {
        Some(Status::Open)
    } else if s.contains("proposed") {
        Some(Status::Proposed)
    } else if s.starts_with("decided") {
        Some(Status::Decided)
    } else {
        None
    }
}

/// A row that renames something: a rename status, and a new value that is not
/// "unchanged" or "none".
fn is_rename_row(row: &Row) -> bool {
    let new = row.new.to_ascii_lowercase();
    let status = row.status.to_ascii_lowercase();
    let rename_status = ["mechanical", "decided", "rename", "open"]
        .iter()
        .any(|p| status.starts_with(p));
    rename_status && !new.starts_with("unchanged") && !new.starts_with("none")
}

fn matching_rows<'a>(rows: &'a [Row], section: &str, needle: &str) -> Vec<&'a Row> {
    rows.iter()
        .filter(|r| r.section == section && r.first.contains(needle))
        .collect()
}

fn map() -> RenameMap {
    load_rename_map(&contracts().join("rename-map.json"))
        .unwrap_or_else(|e| panic!("rename-map.json: {e}"))
}

#[test]
fn naming_tables_are_found() {
    let rows = naming_rows();
    let sections: BTreeSet<&str> = rows.iter().map(|r| r.section.as_str()).collect();
    for s in [
        "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8", "3.9", "3.10",
    ] {
        assert!(sections.contains(s), "naming.md section {s} has no rows");
    }
    assert!(rows.len() > 100, "only {} rows read", rows.len());
}

#[test]
fn every_rename_entry_matches_its_naming_row() {
    let rows = naming_rows();
    let map = map();
    for e in &map.entries {
        let found = matching_rows(&rows, &e.naming.section, &e.naming.row);
        assert_eq!(
            found.len(),
            1,
            "{:?}: row {:?} matches {} rows of section {}",
            e.old,
            e.naming.row,
            found.len(),
            e.naming.section
        );
        let row = found[0];
        assert!(
            is_rename_row(row),
            "{:?}: row {:?} is not a rename",
            e.old,
            row.first
        );
        assert!(
            row.first.contains(&e.old),
            "{:?} is not in the row's old-name cell {:?}",
            e.old,
            row.first
        );
        assert_eq!(
            implied_status(&row.status),
            Some(e.status),
            "{:?}: naming.md says {:?}",
            e.old,
            row.status
        );
        if let Some(new) = &e.new {
            assert!(
                row.new.contains(new.as_str()),
                "{:?}: new {new:?} is not in naming.md's {:?}",
                e.old,
                row.new
            );
        }
    }
}

#[test]
fn proposed_names_are_never_carried_as_decided() {
    let rows = naming_rows();
    for e in &map().entries {
        let row = matching_rows(&rows, &e.naming.section, &e.naming.row)[0];
        if row.status.to_ascii_lowercase().contains("proposed") {
            assert_ne!(e.status, Status::Decided, "{:?}", e.old);
            assert_ne!(e.status, Status::Mechanical, "{:?}", e.old);
        }
    }
}

#[test]
fn every_rename_row_is_covered_or_excluded() {
    let rows = naming_rows();
    let map = map();
    for x in &map.excluded {
        let found = matching_rows(&rows, &x.naming.section, &x.naming.row);
        assert_eq!(
            found.len(),
            1,
            "exclusion {:?} matches {} rows",
            x.naming.row,
            found.len()
        );
        assert!(
            is_rename_row(found[0]),
            "exclusion {:?} is not a rename row",
            x.naming.row
        );
    }
    for row in rows
        .iter()
        .filter(|r| r.section != "3.10" && is_rename_row(r))
    {
        let covered = map
            .entries
            .iter()
            .any(|e| e.naming.section == row.section && row.first.contains(&e.naming.row))
            || map
                .excluded
                .iter()
                .any(|x| x.naming.section == row.section && row.first.contains(&x.naming.row));
        assert!(
            covered,
            "naming.md {} row {:?} is neither in the rename map nor excluded",
            row.section, row.first
        );
    }
}

#[test]
fn every_server_setting_of_section_3_1_is_renamed_exactly() {
    let map = map();
    for row in naming_rows()
        .iter()
        .filter(|r| r.section == "3.1" && is_rename_row(r))
    {
        let old = row.first.trim_matches('`');
        let new = row.new.trim_matches('`');
        assert_eq!(map.apply("env", old).as_deref(), Some(new), "{old}");
    }
    // engine-interface names pass verbatim: no blanket prefix rule renames them
    for verbatim in [
        "MAYA_GLM_SLOT_KEEP",
        "MAYA_GPU_RELEASE_S",
        "FAKE_ENGINE_IDS",
    ] {
        assert_eq!(map.apply("env", verbatim), None, "{verbatim}");
    }
}

#[test]
fn renames_apply_to_donor_observations() {
    let map = map();
    assert_eq!(
        map.apply("log", "[maya] stopping (SIGTERM): the engine ends")
            .as_deref(),
        Some("[console] stopping (SIGTERM): the engine ends")
    );
    assert_eq!(
        map.apply("storage", "maya.theme").as_deref(),
        Some("pulsar.theme")
    );
    assert_eq!(
        map.apply("storage", "maya").as_deref(),
        Some("pulsar-console")
    );
    assert_eq!(
        map.apply("file", "maya-glm.json").as_deref(),
        Some("pulsar-glm.json")
    );
    assert_eq!(
        map.apply("file", ".maya-switch.json").as_deref(),
        Some(".pulsar-switch.json")
    );
    assert_eq!(
        map.apply("model-name", "qwen3.8-flash-next").as_deref(),
        Some("pulsar-console-synthetic")
    );
    // a value naming.md leaves open renames nothing
    assert_eq!(map.apply("reasoning-prefix", "maya-r1:abc"), None);
    assert_eq!(map.apply("label", "Maya-XS"), None);
    // a proposed value is never applied: it is reported with its deviation instead
    assert_eq!(map.apply("metric", "maya:requests_total"), None);
    assert_eq!(map.apply("cli", "--engine maya"), None);
    assert_eq!(map.apply("json-key", "maya"), None);
    assert_eq!(map.apply("status-service", "maya"), None);
    let (new, entry) = map.proposed("metric", "maya:requests_total").unwrap();
    assert_eq!(new, "pulsar_console:requests_total");
    assert_eq!(entry.status, Status::Proposed);
    assert_eq!(entry.deviation, "BRAND-1.6");
    let (new, _) = map.proposed("cli", "--engine maya").unwrap();
    assert_eq!(new, "--engine line");
    // no proposed entry is applicable, whatever its value
    assert!(map.applicable().all(|e| e.status != Status::Proposed));
}

// ------------------------------------------------------------------ deviations.md

/// The deviation ids deviations.md approves: section headings and sub-item rows outside
/// the declined and deferred sections.
fn approved_deviation_ids() -> BTreeSet<String> {
    let text = read("deviations.md");
    let mut ids = BTreeSet::new();
    let mut skip = false;
    for line in text.lines() {
        if let Some(h) = line.strip_prefix("## ") {
            skip = h.starts_with("Declined") || h.starts_with("Deferred");
            if !skip {
                ids.insert(h.trim().to_string());
            }
            continue;
        }
        if let Some(h) = line.strip_prefix("### ") {
            if !skip {
                ids.insert(h.trim().to_string());
            }
            continue;
        }
        if skip {
            continue;
        }
        if let Some(rest) = line.strip_prefix("| ") {
            if let Some(id) = rest.split(" |").next() {
                ids.insert(id.trim().to_string());
            }
        }
    }
    ids
}

#[test]
fn every_cited_deviation_is_approved_in_the_register() {
    let approved = approved_deviation_ids();
    assert!(
        approved.contains("BRAND-1.5") && approved.contains("PLAN-2") && approved.contains("P-1")
    );
    assert!(
        !approved.contains("P-12") && !approved.contains("P-5"),
        "declined or deferred ids leak in"
    );
    for e in &map().entries {
        assert!(
            approved.contains(&e.deviation),
            "{:?} cites {}, not an approved deviation",
            e.old,
            e.deviation
        );
    }
}

// ------------------------------------------------------------------ volatile fields

#[test]
fn volatile_fields_cover_every_category_of_the_rule() {
    let list = load_volatile_fields(&contracts().join("volatile-fields.json"))
        .unwrap_or_else(|e| panic!("volatile-fields.json: {e}"));
    for class in VolatileClass::ALL {
        assert!(
            list.of_class(*class).count() > 0,
            "no field of class {}",
            class.as_str()
        );
    }
    // the Date header and the Server value (P-1) are volatile, by value only
    assert!(list.header_value_is_volatile("Date"));
    assert!(list.header_value_is_volatile("server"));
    let headers: Vec<_> = list
        .fields
        .iter()
        .filter(|f| matches!(f.location, Location::Header { .. }))
        .collect();
    assert_eq!(
        headers.len(),
        2,
        "only Date and Server values are volatile headers"
    );
    assert!(headers
        .iter()
        .all(|f| f.class == VolatileClass::HeaderValue));
    assert!(!list.header_value_is_volatile("Content-Type"));
    // generated ids of every donor id site
    let prefixes: BTreeSet<&str> = list
        .fields
        .iter()
        .filter_map(|f| match &f.location {
            Location::IdPrefix { prefix, .. } => Some(prefix.as_str()),
            _ => None,
        })
        .collect();
    for p in ["chatcmpl-", "msg_", "resp_", "rs_", "fc_", "item_", "call_"] {
        assert!(prefixes.contains(p), "no id field for {p}");
    }
    // timestamps and created fields, uptime
    let keys: BTreeSet<&str> = list
        .fields
        .iter()
        .filter_map(|f| match &f.location {
            Location::JsonKey { key, .. } => Some(key.as_str()),
            _ => None,
        })
        .collect();
    for k in [
        "created",
        "created_at",
        "completed_at",
        "uptime_s",
        "prompt_ms",
        "decode_ms",
        "total_duration",
    ] {
        assert!(keys.contains(k), "no volatile field for {k}");
    }
    // counts that sit beside timing figures are not volatile
    for k in [
        "cache_n",
        "prompt_n",
        "predicted_n",
        "prompt_tokens",
        "completion_tokens",
    ] {
        assert!(!keys.contains(k), "{k} is a count, not a volatile figure");
    }
    for f in &list.fields {
        assert!(!f.donor.is_empty(), "{} has no donor citation", f.id);
    }
    // the wall-clock and timing fields of the status, model and context routes
    for (id, class, key, parent) in [
        (
            "last-timings-at",
            VolatileClass::EpochS,
            "at",
            Some("last_timings"),
        ),
        (
            "status-machine-at",
            VolatileClass::EpochS,
            "at",
            Some("machine"),
        ),
        ("expires-at-ps", VolatileClass::Iso, "expires_at", None),
        ("modified-at-model", VolatileClass::Iso, "modified_at", None),
        ("context-load-s", VolatileClass::Num, "load_s", None),
    ] {
        let f = list
            .fields
            .iter()
            .find(|f| f.id == id)
            .unwrap_or_else(|| panic!("no volatile field {id}"));
        assert_eq!(f.class, class, "{id}");
        match &f.location {
            Location::JsonKey {
                key: k, parent: p, ..
            } => {
                assert_eq!(k, key, "{id}");
                assert_eq!(p.as_deref(), parent, "{id}");
            }
            other => panic!("{id}: {other:?}"),
        }
    }
}
