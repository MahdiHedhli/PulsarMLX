//! Checks that tie the parity ledger to the Rust tests it names.
//!
//! The ledger is `console/parity/ledger.json` (contracts/parity-ledger.md, R19): one row
//! per donor test method, each with one disposition. Its full checker, with the deviation
//! register and the evidence listings of every job, is CNF-12's (M10). Until then this
//! module gives each package's tests the checks a reviewer would otherwise do by hand:
//!
//! - [`structure_problems`]: the rules of contract sections 3 and 5 that the ledger alone
//!   can show (the count, unique sorted ids, the id made of file, class and method, one
//!   known disposition with exactly the fields it requires, no unknown field, a
//!   not-applicable reason from the closed list, test entries in the `crate::path` form);
//! - [`missing_from_source`]: every Rust test a row names (in `rust_tests` or
//!   `asserted_by`) is a test function of that name in the source file its path names: for
//!   an integration test, `tests/<stem>.rs`; for a unit test, `src/<a>/<b>.rs` or
//!   `src/<a>/<b>/mod.rs` (or `src/lib.rs` for a top-level path), with the inline modules
//!   left in the path (`tests`) declared in that file, and the `fn` preceded by a
//!   `#[test]` or `#[tokio::test]` attribute, indented as `cargo fmt` indents that many
//!   nested modules, and not inside a line comment. It is a
//!   source-level check, an approximation of the `cargo test -- --list` listing that
//!   contract section 3.2 names until CNF-12's listing check exists: it does not check
//!   the order in which the inline modules nest, nor `cfg` or `ignore` attributes;
//! - [`missing_from_listing`]: the same against the exact output of
//!   `cargo test -p <crate> -- --list`, for a caller that has it;
//! - [`count_donor_methods`]: the methods of one donor test file, counted from its text
//!   with the listing tool's rule, so a count can be checked against the rows.
//!
//! The authoritative row list comes from `console/tools/list_donor_tests.py`, which parses
//! the donor files with Python's `ast`; [`count_donor_methods`] is a line scan for files
//! written the way the donor's are (four-space indents). It skips the lines inside
//! triple-quoted strings (the donor's test files hold fake-engine scripts and page code at
//! column 0 inside such strings), so a class body goes on after them.
//!
//! Behavior reference: contracts/parity-ledger.md sections 3, 4 and 5 (feature 022).

use std::collections::BTreeSet;
use std::fmt;
use std::path::{Path, PathBuf};

use serde_json::{Map, Value};

/// The eight dispositions of contract section 3.2.
pub const DISPOSITIONS: [&str; 8] = [
    "rust-test",
    "scenario",
    "shim",
    "web-test",
    "vendor-render",
    "deviation",
    "not-applicable",
    "pending",
];

/// The closed list of not-applicable reasons (contract section 3.3).
pub const NOT_APPLICABLE_REASONS: [&str; 4] = [
    "engine-source-reads",
    "launcher-only",
    "needs-real-pack-or-GPU",
    "Windows-only-process-model",
];

/// The fields every row has (contract section 3.1).
pub const COMMON_FIELDS: [&str; 6] = ["id", "file", "class", "method", "subsystem", "disposition"];

/// The fields any row may have (contract section 3.1).
pub const OPTIONAL_FIELDS: [&str; 3] = ["package", "upstream_skipped", "notes"];

/// The top-level fields of the ledger (contract section 3).
pub const TOP_FIELDS: [&str; 5] = ["ledger", "donor", "listing_tool", "count", "rows"];

/// The largest ledger file read (16 MiB; the ledger is well under 1 MiB).
pub const MAX_LEDGER_BYTES: u64 = 16 << 20;

/// The fields a disposition requires (contract section 3.2).
pub fn required_fields(disposition: &str) -> Option<&'static [&'static str]> {
    Some(match disposition {
        "rust-test" => &["rust_tests"],
        "scenario" => &["scenarios"],
        "shim" => &["shim", "shim_record"],
        "web-test" => &["web_tests"],
        "vendor-render" => &["vendor_cases", "vendor_record"],
        "deviation" => &["deviation", "asserted_by"],
        "not-applicable" => &["reason", "notes"],
        "pending" => &[],
        _ => return None,
    })
}

/// Why the ledger could not be read.
#[derive(Debug)]
pub enum LedgerError {
    /// The file could not be read.
    Io(std::io::Error),
    /// The file is larger than [`MAX_LEDGER_BYTES`].
    TooLarge(u64),
    /// The text is not JSON.
    Json(serde_json::Error),
    /// The JSON is not a ledger object with a `rows` array of objects.
    Shape(String),
}

impl fmt::Display for LedgerError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(e) => write!(f, "ledger: {e}"),
            Self::TooLarge(n) => write!(f, "ledger: {n} bytes is over the limit"),
            Self::Json(e) => write!(f, "ledger: {e}"),
            Self::Shape(what) => write!(f, "ledger: {what}"),
        }
    }
}

impl std::error::Error for LedgerError {}

/// One row, with the fields the checks read and the whole object.
#[derive(Debug, Clone, PartialEq)]
pub struct Row {
    /// `file::Class::method` or `file::function`.
    pub id: String,
    /// The disposition (empty when the field is missing or not a string).
    pub disposition: String,
    /// The package that resolved the row, if recorded.
    pub package: Option<String>,
    /// The row as written.
    pub fields: Map<String, Value>,
}

impl Row {
    /// A string field.
    pub fn text(&self, name: &str) -> Option<&str> {
        self.fields.get(name).and_then(Value::as_str)
    }

    /// The Rust test entries the row names: `rust_tests`, and the entries of
    /// `asserted_by` that are not web tests or scenarios (no `/` before the first `::`).
    pub fn rust_test_entries(&self) -> Vec<&str> {
        let mut out = Vec::new();
        for field in ["rust_tests", "asserted_by"] {
            if let Some(Value::Array(items)) = self.fields.get(field) {
                for item in items.iter().filter_map(Value::as_str) {
                    if parse_test_ref(item).is_some() {
                        out.push(item);
                    }
                }
            }
        }
        out
    }
}

/// The parity ledger as read.
#[derive(Debug, Clone, PartialEq)]
pub struct Ledger {
    /// The top-level object without its rows.
    pub top: Map<String, Value>,
    /// The rows in file order.
    pub rows: Vec<Row>,
}

impl Ledger {
    /// The row with this id.
    pub fn row(&self, id: &str) -> Option<&Row> {
        self.rows.iter().find(|r| r.id == id)
    }

    /// The rows of one donor file (`serve/test_server.py`).
    pub fn rows_of_file<'a>(&'a self, file: &'a str) -> impl Iterator<Item = &'a Row> + 'a {
        self.rows
            .iter()
            .filter(move |r| r.text("file") == Some(file))
    }

    /// The `count` field.
    pub fn count(&self) -> Option<u64> {
        self.top.get("count").and_then(Value::as_u64)
    }
}

/// Parses ledger text.
pub fn parse(text: &str) -> Result<Ledger, LedgerError> {
    let value: Value = serde_json::from_str(text).map_err(LedgerError::Json)?;
    let Value::Object(mut top) = value else {
        return Err(LedgerError::Shape("the ledger is not an object".into()));
    };
    let Some(Value::Array(items)) = top.remove("rows") else {
        return Err(LedgerError::Shape("the ledger has no rows array".into()));
    };
    let mut rows = Vec::with_capacity(items.len());
    for (i, item) in items.into_iter().enumerate() {
        let Value::Object(fields) = item else {
            return Err(LedgerError::Shape(format!("row {i} is not an object")));
        };
        let id = fields
            .get("id")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned();
        let disposition = fields
            .get("disposition")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned();
        let package = fields
            .get("package")
            .and_then(Value::as_str)
            .map(str::to_owned);
        rows.push(Row {
            id,
            disposition,
            package,
            fields,
        });
    }
    Ok(Ledger { top, rows })
}

/// Reads and parses the ledger file at `path`.
pub fn load(path: &Path) -> Result<Ledger, LedgerError> {
    let size = std::fs::metadata(path).map_err(LedgerError::Io)?.len();
    if size > MAX_LEDGER_BYTES {
        return Err(LedgerError::TooLarge(size));
    }
    let text = std::fs::read_to_string(path).map_err(LedgerError::Io)?;
    parse(&text)
}

/// The ledger of this workspace: `console/parity/ledger.json`, found from a crate's
/// manifest directory (`env!("CARGO_MANIFEST_DIR")` of a crate under `console/crates/`).
pub fn workspace_ledger_path(manifest_dir: &Path) -> PathBuf {
    workspace_root(manifest_dir)
        .join("parity")
        .join("ledger.json")
}

/// The `console/` folder, from a crate's manifest directory under `console/crates/`.
pub fn workspace_root(manifest_dir: &Path) -> PathBuf {
    manifest_dir
        .parent()
        .and_then(Path::parent)
        .map_or_else(|| manifest_dir.to_path_buf(), Path::to_path_buf)
}

/// A Rust test entry, `crate::path::to::test`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TestRef {
    /// The crate's package name (`console-http`).
    pub krate: String,
    /// The path after the crate: for a unit test the path `cargo test -- --list` prints;
    /// for an integration test, the test file's stem and then that path.
    pub path: Vec<String>,
}

impl TestRef {
    /// The test function's name (the last segment).
    pub fn name(&self) -> &str {
        self.path.last().map_or("", String::as_str)
    }
}

/// Splits `crate::a::b` into its crate and path; `None` for anything else (web tests and
/// scenario ids among them).
pub fn parse_test_ref(entry: &str) -> Option<TestRef> {
    let mut parts = entry.split("::");
    let krate = parts.next()?;
    let path: Vec<String> = parts.map(str::to_owned).collect();
    let crate_ok = !krate.is_empty()
        && krate
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-' || c == '_');
    let path_ok = !path.is_empty()
        && path
            .iter()
            .all(|p| !p.is_empty() && p.chars().all(|c| c.is_ascii_alphanumeric() || c == '_'));
    (crate_ok && path_ok).then(|| TestRef {
        krate: krate.to_owned(),
        path,
    })
}

/// The id a row should have: `file::Class::method`, or `file::method` without a class.
fn expected_id(row: &Row) -> Option<String> {
    let file = row.text("file")?;
    let method = row.text("method")?;
    Some(match row.fields.get("class") {
        Some(Value::String(class)) => format!("{file}::{class}::{method}"),
        Some(Value::Null) => format!("{file}::{method}"),
        _ => return None,
    })
}

fn non_empty_array(row: &Row, field: &str) -> bool {
    matches!(row.fields.get(field), Some(Value::Array(a)) if !a.is_empty()
        && a.iter().all(|v| v.as_str().is_some_and(|s| !s.is_empty())))
}

/// The structural problems of the ledger, one line each; empty when there are none.
pub fn structure_problems(ledger: &Ledger) -> Vec<String> {
    let mut problems = Vec::new();
    for key in ledger.top.keys() {
        if !TOP_FIELDS.contains(&key.as_str()) {
            problems.push(format!("unknown top-level field {key:?}"));
        }
    }
    match ledger.count() {
        Some(n) if usize::try_from(n).is_ok_and(|n| n == ledger.rows.len()) => {}
        Some(n) => problems.push(format!("count {n} but {} rows", ledger.rows.len())),
        None => problems.push("no count".to_owned()),
    }
    let mut seen = BTreeSet::new();
    let mut previous: Option<&str> = None;
    for row in &ledger.rows {
        let id = row.id.as_str();
        if !seen.insert(id) {
            problems.push(format!("{id}: duplicate id"));
        }
        if previous.is_some_and(|p| p >= id) {
            problems.push(format!("{id}: rows are not sorted by id"));
        }
        previous = Some(id);
        if expected_id(row).as_deref() != Some(id) {
            problems.push(format!("{id}: the id is not file::class::method"));
        }
        let Some(required) = required_fields(&row.disposition) else {
            problems.push(format!("{id}: unknown disposition {:?}", row.disposition));
            continue;
        };
        for field in COMMON_FIELDS {
            if !row.fields.contains_key(field) {
                problems.push(format!("{id}: missing {field}"));
            }
        }
        for field in required {
            if !row.fields.contains_key(*field) {
                problems.push(format!("{id}: {} needs {field}", row.disposition));
            }
        }
        for key in row.fields.keys() {
            let k = key.as_str();
            if !COMMON_FIELDS.contains(&k)
                && !OPTIONAL_FIELDS.contains(&k)
                && !required.contains(&k)
            {
                problems.push(format!("{id}: field {k:?} is not allowed here"));
            }
        }
        for field in [
            "rust_tests",
            "scenarios",
            "web_tests",
            "vendor_cases",
            "asserted_by",
        ] {
            if required.contains(&field) && !non_empty_array(row, field) {
                problems.push(format!("{id}: {field} must be a non-empty list of names"));
            }
        }
        if let Some(Value::Array(items)) = row.fields.get("rust_tests") {
            for item in items {
                if !item.as_str().is_some_and(|s| parse_test_ref(s).is_some()) {
                    problems.push(format!("{id}: rust_tests entry {item} is not crate::path"));
                }
            }
        }
        if row.disposition == "not-applicable"
            && !row
                .text("reason")
                .is_some_and(|r| NOT_APPLICABLE_REASONS.contains(&r))
        {
            problems.push(format!("{id}: the reason is not in the closed list"));
        }
    }
    problems
}

/// The test names in the output of `cargo test -- --list` (lines `name: test`).
pub fn listing_names(output: &str) -> BTreeSet<String> {
    output
        .lines()
        .filter_map(|l| l.strip_suffix(": test"))
        .map(str::to_owned)
        .collect()
}

/// One test target's listing: its crate, its integration test file stem (`None` for the
/// library's unit tests) and the exact output of `cargo test -- --list` for it.
#[derive(Debug, Clone, Copy)]
pub struct Listing<'a> {
    /// The crate's package name.
    pub krate: &'a str,
    /// The integration test file stem, or `None` for unit tests.
    pub target: Option<&'a str>,
    /// The listing output.
    pub output: &'a str,
}

/// The Rust test entries of the ledger that none of `listings` contains, as
/// `row id: entry`. Entries of crates not in `listings` are not judged.
pub fn missing_from_listing(ledger: &Ledger, listings: &[Listing<'_>]) -> Vec<String> {
    let mut known = BTreeSet::new();
    let mut crates = BTreeSet::new();
    for l in listings {
        crates.insert(l.krate);
        for name in listing_names(l.output) {
            known.insert(match l.target {
                Some(t) => format!("{}::{t}::{name}", l.krate),
                None => format!("{}::{name}", l.krate),
            });
        }
    }
    let mut missing = Vec::new();
    for row in &ledger.rows {
        for entry in row.rust_test_entries() {
            let Some(r) = parse_test_ref(entry) else {
                continue;
            };
            if crates.contains(r.krate.as_str()) && !known.contains(entry) {
                missing.push(format!("{}: {entry}", row.id));
            }
        }
    }
    missing
}

/// The text of a line without leading spaces, and with `pub`, `pub(...)`, `async`,
/// `unsafe` and `const` qualifiers removed from its front.
fn strip_qualifiers(line: &str) -> &str {
    let mut t = line.trim_start();
    loop {
        let before = t;
        for q in [
            "pub(crate) ",
            "pub(super) ",
            "pub ",
            "async ",
            "unsafe ",
            "const ",
        ] {
            if let Some(rest) = t.strip_prefix(q) {
                t = rest.trim_start();
            }
        }
        if t == before {
            return t;
        }
    }
}

/// Whether `line` (not a comment) declares the function `name`: `fn name(` or `fn name<`.
fn declares_fn(line: &str, name: &str) -> bool {
    if line.trim_start().starts_with("//") {
        return false;
    }
    strip_qualifiers(line)
        .strip_prefix("fn ")
        .and_then(|rest| rest.strip_prefix(name))
        .is_some_and(|after| after.starts_with('(') || after.starts_with('<'))
}

/// Whether the attribute lines above line `at` of `lines` hold `#[test]` or
/// `#[tokio::test...]`. Doc comments, other attributes and attributes written over
/// several lines may stand between them and the `fn`.
fn has_test_attribute(lines: &[&str], at: usize) -> bool {
    let mut j = at;
    while j > 0 {
        j -= 1;
        let t = lines.get(j).map_or("", |l| l.trim());
        if t.starts_with("#[test]") || t.starts_with("#[tokio::test") {
            return true;
        }
        if t.starts_with("#[") || t.starts_with("//") {
            continue;
        }
        if t.ends_with(")]") || t.ends_with(',') {
            // The inside or the end of an attribute written over several lines: go up to
            // its `#[`, at most 32 lines.
            let floor = j.saturating_sub(32);
            while j > floor && !lines.get(j).is_some_and(|l| l.trim().starts_with("#[")) {
                j -= 1;
            }
            let opening = lines.get(j).map_or("", |l| l.trim());
            if opening.starts_with("#[test") || opening.starts_with("#[tokio::test") {
                return true;
            }
            if opening.starts_with("#[") {
                continue;
            }
        }
        return false;
    }
    false
}

/// Whether `line` (not a comment) declares the inline module `name` (`mod name {`).
fn declares_inline_mod(line: &str, name: &str) -> bool {
    if line.trim_start().starts_with("//") {
        return false;
    }
    strip_qualifiers(line)
        .strip_prefix("mod ")
        .and_then(|rest| rest.strip_prefix(name))
        .is_some_and(|after| after.trim_start().starts_with('{'))
}

/// Whether the source `text` holds a test function `name` (a `fn name` under a test
/// attribute, outside line comments), with each of `inline_mods` declared as an inline
/// module of the file, and the `fn` indented as `cargo fmt` indents a function nested in
/// that many modules (four spaces each), so a test inside `mod tests` does not stand for a
/// path that leaves `tests` out.
pub fn defines_test_fn(text: &str, inline_mods: &[String], name: &str) -> bool {
    let lines: Vec<&str> = text.lines().collect();
    let mods_ok = inline_mods
        .iter()
        .all(|m| lines.iter().any(|l| declares_inline_mod(l, m)));
    let indent = 4 * inline_mods.len();
    mods_ok
        && lines.iter().enumerate().any(|(i, l)| {
            let lead = l.len() - l.trim_start_matches(' ').len();
            lead == indent && declares_fn(l, name) && has_test_attribute(&lines, i)
        })
}

/// The source file a test path names in `crate_dir`, with the inline modules left in the
/// path: the integration test file `tests/<stem>.rs` when the first segment names one,
/// otherwise the deepest module file under `src/` (`a/b.rs` or `a/b/mod.rs`, then
/// `lib.rs` or `main.rs`).
pub fn test_source(crate_dir: &Path, r: &TestRef) -> Option<(PathBuf, Vec<String>)> {
    let (_, mods) = r.path.split_last()?;
    if let Some((stem, inner)) = mods.split_first() {
        let file = crate_dir.join("tests").join(format!("{stem}.rs"));
        if file.is_file() {
            return Some((file, inner.to_vec()));
        }
    }
    let src = crate_dir.join("src");
    for k in (0..=mods.len()).rev() {
        let (outer, inner) = mods.split_at(k);
        let candidates = match outer.split_last() {
            None => vec![src.join("lib.rs"), src.join("main.rs")],
            Some((last, parents)) => {
                let dir = parents.iter().fold(src.clone(), |d, p| d.join(p));
                vec![
                    dir.join(format!("{last}.rs")),
                    dir.join(last).join("mod.rs"),
                ]
            }
        };
        if let Some(file) = candidates.into_iter().find(|f| f.is_file()) {
            return Some((file, inner.to_vec()));
        }
    }
    None
}

/// The Rust test entries of the ledger that cannot be found as test functions in the
/// sources under `crates_dir` (`console/crates`), as `row id: entry (why)`. See
/// [`test_source`] for the file an entry names and [`defines_test_fn`] for what counts as
/// found.
pub fn missing_from_source(ledger: &Ledger, crates_dir: &Path) -> Vec<String> {
    let mut missing = Vec::new();
    for row in &ledger.rows {
        for entry in row.rust_test_entries() {
            let Some(r) = parse_test_ref(entry) else {
                continue;
            };
            let crate_dir = crates_dir.join(&r.krate);
            if !crate_dir.join("Cargo.toml").is_file() {
                missing.push(format!("{}: {entry} (no crate {})", row.id, r.krate));
                continue;
            }
            let Some((file, inner)) = test_source(&crate_dir, &r) else {
                missing.push(format!("{}: {entry} (no source file for the path)", row.id));
                continue;
            };
            let found = std::fs::read_to_string(&file)
                .is_ok_and(|text| defines_test_fn(&text, &inner, r.name()));
            if !found {
                missing.push(format!(
                    "{}: {entry} (no test fn {} in {})",
                    row.id,
                    r.name(),
                    file.file_name()
                        .map_or_else(String::new, |f| f.to_string_lossy().into_owned())
                ));
            }
        }
    }
    missing
}

/// One test method found in a donor file.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DonorMethod {
    /// The module-level class, or `None` for a module-level function.
    pub class: Option<String>,
    /// The method or function name.
    pub method: String,
}

impl DonorMethod {
    /// The ledger id for this method in `file`.
    pub fn id(&self, file: &str) -> String {
        match &self.class {
            Some(c) => format!("{file}::{c}::{}", self.method),
            None => format!("{file}::{}", self.method),
        }
    }
}

fn test_def_name(line: &str) -> Option<&str> {
    let rest = line
        .strip_prefix("async def ")
        .or_else(|| line.strip_prefix("def "))?;
    let end = rest.find(|c: char| !(c.is_alphanumeric() || c == '_'))?;
    let name = rest.get(..end)?;
    name.starts_with("test").then_some(name)
}

/// The triple-quote delimiter a Python line leaves open, given the one open at its start
/// (`None` outside a string). Comments and one-line strings are skipped; a backslash
/// escapes the next character inside any string.
fn open_string_after(line: &str, open: Option<&'static str>) -> Option<&'static str> {
    let bytes = line.as_bytes();
    let mut open = open;
    let mut i = 0usize;
    while i < bytes.len() {
        let rest = bytes.get(i..).unwrap_or_default();
        if let Some(delim) = open {
            if rest.first() == Some(&b'\\') {
                i += 2;
            } else if rest.starts_with(delim.as_bytes()) {
                open = None;
                i += 3;
            } else {
                i += 1;
            }
            continue;
        }
        match rest.first() {
            Some(b'#') => break,
            Some(b'"' | b'\'') if rest.starts_with(b"\"\"\"") || rest.starts_with(b"\'\'\'") => {
                open = Some(if rest.starts_with(b"\"\"\"") {
                    "\"\"\""
                } else {
                    "\'\'\'"
                });
                i += 3;
            }
            Some(&q @ (b'"' | b'\'')) => {
                // A one-line string: up to its unescaped closing quote or the line's end.
                i += 1;
                while let Some(&b) = bytes.get(i) {
                    i += if b == b'\\' { 2 } else { 1 };
                    if b == q {
                        break;
                    }
                }
            }
            _ => i += 1,
        }
    }
    open
}

/// The test methods of one donor test file, from its text: a `def test*` or
/// `async def test*` written directly in the body of a module-level class (four spaces
/// in), or directly at module level, in file order. This is the listing tool's rule
/// (contract section 4, step 2) applied line by line; lines inside a triple-quoted string
/// are skipped, whatever their indent. It is meant for files written as the donor's are,
/// and the `ast`-based tool stays authoritative.
pub fn count_donor_methods(source: &str) -> Vec<DonorMethod> {
    let mut out = Vec::new();
    let mut class: Option<String> = None;
    let mut open: Option<&'static str> = None;
    for line in source.lines() {
        let inside = open.is_some();
        open = open_string_after(line, open);
        if inside || line.trim().is_empty() {
            continue;
        }
        let top_level = !line.starts_with(' ') && !line.starts_with('\t');
        if top_level {
            if line.starts_with('#') || line.starts_with('@') || line.starts_with(')') {
                continue;
            }
            if let Some(rest) = line.strip_prefix("class ") {
                let end = rest
                    .find(|c: char| !(c.is_alphanumeric() || c == '_'))
                    .unwrap_or(rest.len());
                class = rest.get(..end).map(str::to_owned);
                continue;
            }
            class = None;
            if let Some(name) = test_def_name(line) {
                out.push(DonorMethod {
                    class: None,
                    method: name.to_owned(),
                });
            }
            continue;
        }
        if let (Some(c), Some(body)) = (&class, line.strip_prefix("    ")) {
            if body.starts_with(' ') || body.starts_with('\t') {
                continue;
            }
            if let Some(name) = test_def_name(body) {
                out.push(DonorMethod {
                    class: Some(c.clone()),
                    method: name.to_owned(),
                });
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ledger(rows: &str) -> Ledger {
        let n = rows.matches("\"id\"").count();
        let text = format!(
            "{{\"ledger\": \"PulsarMLX Console parity ledger\", \"count\": {n}, \"rows\": [{rows}]}}"
        );
        parse(&text).expect("ledger text")
    }

    const PENDING: &str = r#"{"id": "serve/test_a.py::A::test_x", "file": "serve/test_a.py", "class": "A", "method": "test_x", "subsystem": "s", "disposition": "pending"}"#;

    #[test]
    fn a_pending_row_is_well_formed() {
        assert_eq!(structure_problems(&ledger(PENDING)), Vec::<String>::new());
    }

    #[test]
    fn every_rule_names_its_row() {
        let rows = [
            r#"{"id": "serve/test_a.py::A::test_y", "file": "serve/test_a.py", "class": "A", "method": "test_y", "subsystem": "s", "disposition": "rust-test", "package": "X-1", "rust_tests": []}"#,
            PENDING,
            PENDING,
            r#"{"id": "serve/test_a.py::B::test_z", "file": "serve/test_a.py", "class": "A", "method": "test_z", "subsystem": "s", "disposition": "maybe"}"#,
            r#"{"id": "serve/test_b.py::f::test_n", "file": "serve/test_b.py", "class": "f", "method": "test_n", "subsystem": "s", "disposition": "not-applicable", "package": "X-1", "reason": "too hard", "notes": "n", "extra": 1}"#,
            r#"{"id": "serve/test_c.py::test_m", "file": "serve/test_c.py", "class": null, "method": "test_m", "subsystem": "s", "disposition": "deviation", "deviation": "P-1", "asserted_by": ["bad entry"]}"#,
        ]
        .join(", ");
        let p = structure_problems(&ledger(&rows));
        let has = |s: &str| p.iter().any(|l| l.contains(s));
        assert!(has("test_y: rust_tests must be a non-empty list"), "{p:?}");
        assert!(has("test_x: duplicate id"), "{p:?}");
        assert!(has("rows are not sorted"), "{p:?}");
        assert!(has("test_z: the id is not file::class::method"), "{p:?}");
        assert!(has("unknown disposition \"maybe\""), "{p:?}");
        assert!(has("test_n: field \"extra\" is not allowed"), "{p:?}");
        assert!(has("test_n: the reason is not in the closed list"), "{p:?}");
        assert!(
            !p.iter().any(|l| l.contains("test_m:")),
            "package is optional (contract section 3.1): {p:?}"
        );
        let wrong_count = parse(&format!("{{\"count\": 2, \"rows\": [{PENDING}]}}")).expect("text");
        assert!(structure_problems(&wrong_count)
            .iter()
            .any(|l| l == "count 2 but 1 rows"));
        assert!(matches!(parse("[]"), Err(LedgerError::Shape(_))));
        assert!(matches!(parse("{"), Err(LedgerError::Json(_))));
    }

    #[test]
    fn test_entries() {
        let r = parse_test_ref("console-http::api02_donor::a_bad_content_length").expect("ref");
        assert_eq!(r.krate, "console-http");
        assert_eq!(r.path, vec!["api02_donor", "a_bad_content_length"]);
        assert_eq!(r.name(), "a_bad_content_length");
        for bad in [
            "console/web/x.test.mjs::name",
            "console-http",
            "console-http::",
            "Console::x",
            "c::a b",
        ] {
            assert_eq!(parse_test_ref(bad), None, "{bad}");
        }
    }

    #[test]
    fn listings_resolve_entries_per_target() {
        let l = ledger(
            r#"{"id": "serve/test_a.py::A::test_x", "file": "serve/test_a.py", "class": "A", "method": "test_x", "subsystem": "s", "disposition": "deviation", "package": "P", "deviation": "P-1", "asserted_by": ["k::it::one", "k::m::tests::two", "k::it::gone", "other::x", "console/web/a.test.mjs::w"]}"#,
        );
        let listings = [
            Listing {
                krate: "k",
                target: Some("it"),
                output: "one: test\nignored: bench\n",
            },
            Listing {
                krate: "k",
                target: None,
                output: "m::tests::two: test\n\n2 tests, 0 benchmarks\n",
            },
        ];
        assert_eq!(
            missing_from_listing(&l, &listings),
            vec!["serve/test_a.py::A::test_x: k::it::gone".to_owned()]
        );
    }

    #[test]
    fn test_functions_are_found_by_whole_name_under_a_test_attribute() {
        let text = "\
#[tokio::test]
async fn alpha() {}
#[test]
fn beta_two<T>() {}
#[test]
/// doc
#[should_panic(
    expected = \"x\",
)]
pub fn gamma_x() {}
fn helper() {}
// #[test]
// fn commented() {}
#[tokio::test(start_paused = true)]
async fn paused() {}
";
        let none: &[String] = &[];
        assert!(defines_test_fn(text, none, "alpha"));
        assert!(defines_test_fn(text, none, "beta_two"));
        assert!(defines_test_fn(text, none, "gamma_x"));
        assert!(defines_test_fn(text, none, "paused"));
        assert!(!defines_test_fn(text, none, "gamma"), "a prefix of a name");
        assert!(!defines_test_fn(text, none, "lpha"), "a suffix of a name");
        assert!(!defines_test_fn(text, none, "helper"), "not a test");
        assert!(
            !defines_test_fn(text, none, "commented"),
            "only in a comment"
        );
        assert!(!defines_test_fn("fnalpha()", none, "alpha"));
        let in_mod = "#[cfg(test)]\nmod tests {\n    #[test]\n    fn t() {}\n}\n";
        assert!(defines_test_fn(in_mod, &["tests".to_owned()], "t"));
        assert!(
            !defines_test_fn(in_mod, &["other".to_owned()], "t"),
            "a module the file does not declare"
        );
    }

    /// A crate folder under the system temporary folder, removed on drop.
    struct Scratch(PathBuf);

    impl Drop for Scratch {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    fn scratch_crate(files: &[(&str, &str)]) -> Scratch {
        use std::sync::atomic::{AtomicUsize, Ordering};
        static N: AtomicUsize = AtomicUsize::new(0);
        let root = std::env::temp_dir().join(format!(
            "pulsar-console-testkit-ledger-{}-{}",
            std::process::id(),
            N.fetch_add(1, Ordering::Relaxed)
        ));
        let krate = root.join("k");
        for (path, text) in files {
            let file = krate.join(path);
            if let Some(dir) = file.parent() {
                std::fs::create_dir_all(dir).expect("dir");
            }
            std::fs::write(file, text).expect("write");
        }
        std::fs::write(krate.join("Cargo.toml"), "[package]\n").expect("manifest");
        Scratch(root)
    }

    #[test]
    fn source_entries_resolve_by_module_path() {
        let unit = "pub fn arrival_order() {}\n#[cfg(test)]\nmod tests {\n    #[test]\n    fn arrival_order() {}\n}\n";
        let scratch = scratch_crate(&[
            ("src/lib.rs", "pub mod fifo;\npub mod other;\n"),
            ("src/fifo.rs", unit),
            (
                "src/other/mod.rs",
                "// fn in_comment() {}\npub fn plain() {}\n",
            ),
            (
                "src/deep/inner.rs",
                "#[cfg(test)]\nmod tests {\n    #[test]\n    fn deep() {}\n}\n",
            ),
            (
                "tests/it.rs",
                "#[tokio::test]\nasync fn one() {}\nfn helper() {}\n",
            ),
        ]);
        let entries = [
            "k::fifo::tests::arrival_order",
            "k::deep::inner::tests::deep",
            "k::it::one",
            "k::nosuch::tests::arrival_order",
            "k::other::tests::arrival_order",
            "k::other::plain",
            "k::other::in_comment",
            "k::it::helper",
            "k::fifo::arrival_order",
            "absent::x::y",
        ];
        let list = entries
            .iter()
            .map(|e| format!("\"{e}\""))
            .collect::<Vec<_>>()
            .join(", ");
        let l = ledger(&format!(
            r#"{{"id": "serve/test_a.py::A::test_x", "file": "serve/test_a.py", "class": "A", "method": "test_x", "subsystem": "s", "disposition": "deviation", "deviation": "P-1", "asserted_by": [{list}]}}"#
        ));
        let missing = missing_from_source(&l, &scratch.0);
        let named: Vec<&str> = missing
            .iter()
            .filter_map(|m| m.split(": ").nth(1))
            .filter_map(|m| m.split(' ').next())
            .collect();
        assert_eq!(
            named,
            vec![
                "k::nosuch::tests::arrival_order",
                "k::other::tests::arrival_order",
                "k::other::plain",
                "k::other::in_comment",
                "k::it::helper",
                "k::fifo::arrival_order",
                "absent::x::y",
            ],
            "{missing:#?}"
        );
    }

    #[test]
    fn donor_methods_are_counted_by_the_listing_rule() {
        let src = "\
import x


def test_module_level():
    def test_nested():
        pass


class A(unittest.TestCase):
    \"\"\"doc\"\"\"

    @classmethod
    def setUpClass(cls):
        pass

    def test_one(self):
        def test_inner():
            pass

    async def test_two(self):
        pass

    class Inner:
        def test_not_listed(self):
            pass


@decorator
class B:
    def helper(self):
        pass
    def test_three(self): pass

    def test_holds_a_script(self):
        script = \"\"\"
import sys
n = 0
for line in sys.stdin:
    def test_in_string(): pass
\"\"\"
        js = '''
class Fake {}
'''  # comment with \"\"\" inside
        s = \"'''\"

    def test_after_the_script(self):
        pass


def helper():
    pass

    def test_after_function(self):
        pass
";
        let ids: Vec<String> = count_donor_methods(src)
            .iter()
            .map(|m| m.id("serve/test_x.py"))
            .collect();
        assert_eq!(
            ids,
            vec![
                "serve/test_x.py::test_module_level",
                "serve/test_x.py::A::test_one",
                "serve/test_x.py::A::test_two",
                "serve/test_x.py::B::test_three",
                "serve/test_x.py::B::test_holds_a_script",
                "serve/test_x.py::B::test_after_the_script",
            ]
        );
    }

    #[test]
    fn the_workspace_paths() {
        let manifest = Path::new("/w/console/crates/console-testkit");
        assert_eq!(workspace_root(manifest), Path::new("/w/console"));
        assert_eq!(
            workspace_ledger_path(manifest),
            Path::new("/w/console/parity/ledger.json")
        );
    }
}
