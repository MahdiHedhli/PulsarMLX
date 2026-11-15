//! The rename map: `specs/022-console-serving-parity/contracts/rename-map.json`.
//!
//! The map is the machine-readable form of the renames in `contracts/naming.md`, the one
//! published name table (reconciliation R4 in tasks.md). It is derived from that table
//! and checked against it by a test; no second table is maintained. The comparator
//! (CNF-04) applies it to the reference side of an observation before comparing, so a
//! donor observation that says `[maya] ` is compared as `[console] `. Every entry cites
//! the deviation that approves the rename.
//!
//! A name that naming.md marks as proposed is carried here as `proposed`, never as
//! `decided`, and [`RenameMap::apply`] never applies it: only `decided` and `mechanical`
//! entries rename the reference side, and [`RenameMap::proposed`] lets the comparator
//! report a difference a proposed value would explain, citing its deviation. An entry whose new value naming.md leaves open has no `new` value and
//! renames nothing until the owning package settles it. Engine-interface names that pass
//! through verbatim (naming.md section 3.4) are not in the map, so there is deliberately
//! no blanket `MAYA_` prefix rule: only the exact server settings are renamed.

use serde_json::Value;

use super::error::{ErrorKind, Result, ScenarioError};
use super::json::{self, Obj};

/// The largest rename-map file, in bytes.
pub const MAX_RENAME_MAP_BYTES: usize = 512 * 1024;

/// The most entries, and the most exclusions, of a rename map.
pub const MAX_RENAME_ENTRIES: usize = 1024;

/// The longest old or new name.
const MAX_NAME_CHARS: usize = 256;

/// The longest text a pattern entry is matched against; longer text never matches, so
/// the backtracking match stays bounded.
pub const MAX_PATTERN_TEXT_BYTES: usize = 1024;

/// Members of the top-level object.
pub const MAP_FIELDS: &[&str] = &[
    "title",
    "derived_from",
    "donor_commit",
    "use",
    "entries",
    "excluded",
];

/// Members of an entry.
pub const ENTRY_FIELDS: &[&str] = &[
    "old",
    "new",
    "scope",
    "match",
    "status",
    "deviation",
    "naming",
    "open",
    "note",
];

/// Members of an exclusion.
pub const EXCLUSION_FIELDS: &[&str] = &["naming", "reason"];

/// Members of a naming reference.
pub const NAMING_FIELDS: &[&str] = &["section", "row"];

/// What kind of text an entry renames, so the comparator applies it only there.
pub const SCOPES: &[&str] = &[
    "env",
    "file",
    "model-name",
    "storage",
    "dom",
    "download",
    "text",
    "log",
    "status-service",
    "json-key",
    "metric",
    "user-agent",
    "mcp-client-info",
    "cli",
    "tmp-prefix",
    "reasoning-prefix",
    "label",
];

/// How an entry matches a piece of text.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Match {
    /// The whole text equals `old`.
    Exact,
    /// The text starts with `old`; the rest is kept.
    Prefix,
    /// `old` holds placeholders such as `<name>`, each standing for one or more
    /// characters other than `/` and whitespace; `new` uses the same placeholders.
    Pattern,
}

/// How settled an entry's new name is, as naming.md states it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Status {
    /// Fixed by a binding decision, an approved deviation or a lead or owner decision.
    Decided,
    /// Produced by naming.md rule 9 (`MAYA_<SUFFIX>` becomes `PULSAR_CONSOLE_<SUFFIX>`).
    Mechanical,
    /// The rename is decided; the new value is a proposal, settled by the owning package.
    Proposed,
    /// The new value is an open item.
    Open,
}

impl Status {
    /// The status as the file writes it.
    pub fn as_str(self) -> &'static str {
        match self {
            Status::Decided => "decided",
            Status::Mechanical => "mechanical",
            Status::Proposed => "proposed",
            Status::Open => "open",
        }
    }
}

/// Where in naming.md an entry or exclusion comes from.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NamingRef {
    /// The section number, such as `3.1`.
    pub section: String,
    /// Text found in the first cell of exactly one row of that section.
    pub row: String,
}

/// One rename.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RenameEntry {
    /// The donor's name.
    pub old: String,
    /// The console's name; `None` while naming.md leaves the value open.
    pub new: Option<String>,
    /// What kind of text it applies to (one of [`SCOPES`]).
    pub scope: String,
    /// How it matches.
    pub matching: Match,
    /// How settled the new name is.
    pub status: Status,
    /// The approving deviation id, for example `BRAND-1.5`.
    pub deviation: String,
    /// The naming.md row it is derived from.
    pub naming: NamingRef,
    /// The naming.md open item that may still change it, for example `N2`.
    pub open: Option<String>,
    /// Free text for the reviewer.
    pub note: Option<String>,
}

/// A naming.md row deliberately left out of the map, with the reason.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Exclusion {
    /// The row.
    pub naming: NamingRef,
    /// Why it is not a rename the comparator can apply.
    pub reason: String,
}

/// The rename map.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RenameMap {
    /// The renames, in file order.
    pub entries: Vec<RenameEntry>,
    /// The rows left out.
    pub excluded: Vec<Exclusion>,
}

impl RenameMap {
    /// Reads and checks a rename map.
    pub fn from_json_str(text: &str) -> Result<Self> {
        let value = json::parse_strict(text, MAX_RENAME_MAP_BYTES)?;
        let obj = Obj::of(&value, "")?;
        obj.allow_only(MAP_FIELDS)?;
        for key in ["title", "derived_from", "donor_commit", "use"] {
            if let Some((v, p)) = obj.get(key) {
                json::nonempty_string(v, &p, 2000)?;
            }
        }
        let (v, p) = obj.required("entries")?;
        let mut entries: Vec<RenameEntry> = Vec::new();
        for (i, item) in json::nonempty_array(v, &p, MAX_RENAME_ENTRIES)?
            .iter()
            .enumerate()
        {
            let ip = json::index(&p, i);
            let entry = entry(item, &ip)?;
            if entries
                .iter()
                .any(|e| e.scope == entry.scope && e.old == entry.old)
            {
                return Err(ScenarioError::invalid(
                    ip,
                    format!("{:?} is renamed twice in scope {}", entry.old, entry.scope),
                ));
            }
            entries.push(entry);
        }
        let mut excluded = Vec::new();
        if let Some((v, p)) = obj.get("excluded") {
            for (i, item) in json::array(v, &p, MAX_RENAME_ENTRIES)?.iter().enumerate() {
                let ip = json::index(&p, i);
                let o = Obj::of(item, &ip)?;
                o.allow_only(EXCLUSION_FIELDS)?;
                let (nv, np) = o.required("naming")?;
                let naming = naming_ref(nv, &np, None)?;
                let (rv, rp) = o.required("reason")?;
                let reason = json::nonempty_string(rv, &rp, 2000)?.to_string();
                excluded.push(Exclusion { naming, reason });
            }
        }
        Ok(Self { entries, excluded })
    }

    /// The entries that rename something now: the `decided` and `mechanical` ones. A
    /// `proposed` value is not a parity requirement, so it never renames the reference
    /// side; see [`RenameMap::proposed`].
    pub fn applicable(&self) -> impl Iterator<Item = &RenameEntry> {
        self.entries
            .iter()
            .filter(|e| e.new.is_some() && matches!(e.status, Status::Decided | Status::Mechanical))
    }

    /// The new form of `text` under the first applicable entry of `scope` that matches
    /// it, or `None` when none does. Proposed values are never applied.
    pub fn apply(&self, scope: &str, text: &str) -> Option<String> {
        self.applicable()
            .filter(|e| e.scope == scope)
            .find_map(|e| e.apply(text))
    }

    /// The proposed form of `text` under the first `proposed` entry of `scope` that has a
    /// value and matches it, with that entry. The comparator does not accept it as equal:
    /// it reports the difference annotated with the entry's deviation, because the value
    /// is still the owning package's or the owner's to settle.
    pub fn proposed(&self, scope: &str, text: &str) -> Option<(String, &RenameEntry)> {
        self.entries
            .iter()
            .filter(|e| e.status == Status::Proposed && e.scope == scope)
            .find_map(|e| e.apply(text).map(|new| (new, e)))
    }
}

impl RenameEntry {
    /// The new form of `text` under this entry, or `None` when it does not match or has
    /// no new value yet.
    pub fn apply(&self, text: &str) -> Option<String> {
        let new = self.new.as_deref()?;
        match self.matching {
            Match::Exact => (text == self.old).then(|| new.to_string()),
            Match::Prefix => text
                .strip_prefix(self.old.as_str())
                .map(|rest| format!("{new}{rest}")),
            Match::Pattern => {
                let captures = match_pattern(&self.old, text)?;
                let mut out = String::new();
                for piece in split_pattern(new) {
                    match piece {
                        Piece::Literal(s) => out.push_str(s),
                        Piece::Hole(name) => {
                            let (_, value) = captures.iter().find(|(n, _)| *n == name)?;
                            out.push_str(value);
                        }
                    }
                }
                Some(out)
            }
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Piece<'a> {
    Literal(&'a str),
    Hole(&'a str),
}

/// Splits a pattern into literal text and `<name>` holes.
fn split_pattern(pattern: &str) -> Vec<Piece<'_>> {
    let mut pieces = Vec::new();
    let mut rest = pattern;
    while let Some(open) = rest.find('<') {
        let after = rest.get(open + 1..).unwrap_or_default();
        let close = after.find('>');
        let name = close.and_then(|c| after.get(..c));
        match name {
            Some(n) if !n.is_empty() && n.bytes().all(|b| b.is_ascii_lowercase() || b == b'_') => {
                if open > 0 {
                    pieces.push(Piece::Literal(rest.get(..open).unwrap_or_default()));
                }
                pieces.push(Piece::Hole(n));
                rest = after.get(n.len() + 1..).unwrap_or_default();
            }
            _ => {
                pieces.push(Piece::Literal(rest.get(..=open).unwrap_or_default()));
                rest = after;
            }
        }
    }
    if !rest.is_empty() {
        pieces.push(Piece::Literal(rest));
    }
    pieces
}

/// Matches `text` against `pattern`; each hole takes the shortest run of one or more
/// characters (other than `/` and whitespace) that lets the rest match.
fn match_pattern<'t>(pattern: &str, text: &'t str) -> Option<Vec<(String, &'t str)>> {
    fn go<'t>(pieces: &[Piece<'_>], text: &'t str, out: &mut Vec<(String, &'t str)>) -> bool {
        let Some((first, rest)) = pieces.split_first() else {
            return text.is_empty();
        };
        match first {
            Piece::Literal(lit) => match text.strip_prefix(lit) {
                Some(after) => go(rest, after, out),
                None => false,
            },
            Piece::Hole(name) => {
                for (i, c) in text.char_indices() {
                    if c == '/' || c.is_whitespace() {
                        break;
                    }
                    let (taken, after) = text.split_at(i + c.len_utf8());
                    out.push(((*name).to_string(), taken));
                    if go(rest, after, out) {
                        return true;
                    }
                    out.pop();
                }
                false
            }
        }
    }
    if text.len() > MAX_PATTERN_TEXT_BYTES {
        return None;
    }
    let pieces = split_pattern(pattern);
    let mut out = Vec::new();
    go(&pieces, text, &mut out).then_some(out)
}

fn holes(pattern: &str) -> Vec<&str> {
    let mut names: Vec<&str> = split_pattern(pattern)
        .into_iter()
        .filter_map(|p| match p {
            Piece::Hole(n) => Some(n),
            Piece::Literal(_) => None,
        })
        .collect();
    names.sort_unstable();
    names
}

/// A deviation id: upper-case letters, a hyphen, a number and an optional `.n`
/// sub-item, for example `BRAND-1.5`, `PLAN-2` or `P-13`.
pub(crate) fn is_deviation_id(s: &str) -> bool {
    let Some((head, tail)) = s.split_once('-') else {
        return false;
    };
    let digits = |t: &str| !t.is_empty() && t.bytes().all(|b| b.is_ascii_digit());
    let tail_ok = match tail.split_once('.') {
        Some((n, sub)) => digits(n) && digits(sub),
        None => digits(tail),
    };
    !head.is_empty() && head.bytes().all(|b| b.is_ascii_uppercase()) && tail_ok
}

fn naming_ref(v: &Value, p: &str, default_row: Option<&str>) -> Result<NamingRef> {
    let o = Obj::of(v, p)?;
    o.allow_only(NAMING_FIELDS)?;
    let (sv, sp) = o.required("section")?;
    let section = json::nonempty_string(sv, &sp, 8)?;
    let section_ok = section
        .split_once('.')
        .is_some_and(|(a, b)| a == "3" && !b.is_empty() && b.bytes().all(|c| c.is_ascii_digit()));
    if !section_ok {
        return Err(ScenarioError::invalid(
            sp,
            "must name a table section of naming.md, such as 3.1",
        ));
    }
    let row = match (o.get("row"), default_row) {
        (Some((rv, rp)), _) => json::nonempty_string(rv, &rp, 512)?.to_string(),
        (None, Some(d)) => d.to_string(),
        (None, None) => {
            return Err(ScenarioError::new(
                o.pointer.clone(),
                ErrorKind::MissingField { field: "row" },
            ))
        }
    };
    Ok(NamingRef {
        section: section.to_string(),
        row,
    })
}

fn entry(v: &Value, p: &str) -> Result<RenameEntry> {
    let o = Obj::of(v, p)?;
    o.allow_only(ENTRY_FIELDS)?;
    let (ov, op) = o.required("old")?;
    let old = json::nonempty_string(ov, &op, MAX_NAME_CHARS)?.to_string();
    let (nv, np) = o.required("new")?;
    let new = match nv {
        Value::Null => None,
        other => Some(json::nonempty_string(other, &np, MAX_NAME_CHARS)?.to_string()),
    };
    let (sv, sp) = o.required("scope")?;
    let scope = json::nonempty_string(sv, &sp, 32)?;
    if !SCOPES.contains(&scope) {
        return Err(ScenarioError::invalid(
            sp,
            format!("must be one of {}", SCOPES.join(", ")),
        ));
    }
    let (mv, mp) = o.required("match")?;
    let matching = match json::string(mv, &mp, 16)? {
        "exact" => Match::Exact,
        "prefix" => Match::Prefix,
        "pattern" => Match::Pattern,
        _ => {
            return Err(ScenarioError::invalid(
                mp,
                "must be \"exact\", \"prefix\" or \"pattern\"",
            ))
        }
    };
    let (stv, stp) = o.required("status")?;
    let status = match json::string(stv, &stp, 16)? {
        "decided" => Status::Decided,
        "mechanical" => Status::Mechanical,
        "proposed" => Status::Proposed,
        "open" => Status::Open,
        _ => {
            return Err(ScenarioError::invalid(
                stp,
                "must be \"decided\", \"mechanical\", \"proposed\" or \"open\"",
            ))
        }
    };
    if new.is_none() && matches!(status, Status::Decided | Status::Mechanical) {
        return Err(ScenarioError::invalid(
            np,
            "a decided or mechanical rename needs its new name",
        ));
    }
    if new.as_deref() == Some(old.as_str()) {
        return Err(ScenarioError::invalid(
            np,
            "the new name equals the old one",
        ));
    }
    if matching == Match::Pattern {
        let old_holes = holes(&old);
        if old_holes.is_empty() {
            return Err(ScenarioError::invalid(
                op,
                "a pattern holds at least one <placeholder>",
            ));
        }
        if let Some(n) = &new {
            if holes(n) != old_holes {
                return Err(ScenarioError::invalid(
                    np,
                    "the new name uses other placeholders than the old one",
                ));
            }
        }
    }
    let (dv, dp) = o.required("deviation")?;
    let deviation = json::nonempty_string(dv, &dp, 32)?;
    if !is_deviation_id(deviation) {
        return Err(ScenarioError::invalid(
            dp,
            "must be a deviation id such as BRAND-1.5, PLAN-2 or P-13",
        ));
    }
    let (rv, rp) = o.required("naming")?;
    let default_row = format!("`{old}`");
    let naming = naming_ref(rv, &rp, Some(&default_row))?;
    let open = match o.get("open") {
        Some((v, p)) => {
            let s = json::nonempty_string(v, &p, 8)?;
            let ok = s
                .strip_prefix('N')
                .is_some_and(|d| !d.is_empty() && d.bytes().all(|b| b.is_ascii_digit()));
            if !ok {
                return Err(ScenarioError::invalid(
                    p,
                    "must be a naming.md open item such as N2",
                ));
            }
            Some(s.to_string())
        }
        None => None,
    };
    let note = match o.get("note") {
        Some((v, p)) => Some(json::nonempty_string(v, &p, 2000)?.to_string()),
        None => None,
    };
    Ok(RenameEntry {
        old,
        new,
        scope: scope.to_string(),
        matching,
        status,
        deviation: deviation.to_string(),
        naming,
        open,
        note,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn map(entries: &str) -> Result<RenameMap> {
        RenameMap::from_json_str(&format!("{{\"entries\": [{entries}]}}"))
    }

    const LOG: &str = r#"{"old": "[maya] ", "new": "[console] ", "scope": "log", "match": "prefix",
        "status": "decided", "deviation": "BRAND-1.5", "naming": {"section": "3.8"}}"#;

    #[test]
    fn prefix_exact_and_pattern_apply() {
        let m = map(&format!(
            "{LOG}, {}, {}",
            r#"{"old": "MAYA_DEBUG", "new": "PULSAR_CONSOLE_DEBUG", "scope": "env", "match": "exact",
                "status": "mechanical", "deviation": "BRAND-1.2", "naming": {"section": "3.1"}}"#,
            r#"{"old": "maya-<name>.json", "new": "pulsar-<name>.json", "scope": "file", "match": "pattern",
                "status": "decided", "deviation": "BRAND-1.3", "naming": {"section": "3.6"}}"#
        ))
        .unwrap();
        assert_eq!(
            m.apply("log", "[maya] ready").as_deref(),
            Some("[console] ready")
        );
        assert_eq!(m.apply("log", "x [maya] ready"), None);
        assert_eq!(
            m.apply("env", "MAYA_DEBUG").as_deref(),
            Some("PULSAR_CONSOLE_DEBUG")
        );
        assert_eq!(m.apply("env", "MAYA_DEBUGX"), None);
        assert_eq!(
            m.apply("file", "maya-glm.json").as_deref(),
            Some("pulsar-glm.json")
        );
        assert_eq!(m.apply("file", "maya-.json"), None);
        assert_eq!(m.apply("file", "maya-a/b.json"), None);
        // scope is respected
        assert_eq!(m.apply("env", "[maya] x"), None);
        assert_eq!(m.entries[0].naming.row, "`[maya] `");
    }

    #[test]
    fn proposed_without_value_renames_nothing() {
        let m = map(
            r#"{"old": "maya-pdf-", "new": null, "scope": "tmp-prefix", "match": "prefix",
                "status": "proposed", "deviation": "BRAND-1.3", "naming": {"section": "3.6"}}"#,
        )
        .unwrap();
        assert_eq!(m.apply("tmp-prefix", "maya-pdf-x"), None);
        assert_eq!(m.proposed("tmp-prefix", "maya-pdf-x"), None);
        assert_eq!(m.applicable().count(), 0);
    }

    #[test]
    fn proposed_value_is_reported_never_applied() {
        let m = map(
            r#"{"old": "maya:", "new": "pulsar_console:", "scope": "metric", "match": "prefix",
                "status": "proposed", "deviation": "BRAND-1.6", "naming": {"section": "3.9"}}"#,
        )
        .unwrap();
        assert_eq!(m.applicable().count(), 0);
        assert_eq!(m.apply("metric", "maya:requests_total"), None);
        let (new, entry) = m.proposed("metric", "maya:requests_total").unwrap();
        assert_eq!(new, "pulsar_console:requests_total");
        assert_eq!(entry.deviation, "BRAND-1.6");
        assert_eq!(m.proposed("log", "maya:requests_total"), None);
        // a decided entry is applied and is not reported as proposed
        let m = map(LOG).unwrap();
        assert_eq!(m.proposed("log", "[maya] ready"), None);
        assert!(m.apply("log", "[maya] ready").is_some());
    }

    #[test]
    fn decided_needs_a_new_name() {
        let err = map(
            r#"{"old": "a", "new": null, "scope": "text", "match": "exact",
                "status": "decided", "deviation": "BRAND-1.1", "naming": {"section": "3.8"}}"#,
        )
        .unwrap_err();
        assert_eq!(err.pointer, "/entries/0/new");
    }

    #[test]
    fn bad_fields_are_named() {
        let cases = [
            (r#""scope": "nowhere""#, "/entries/0/scope"),
            (r#""match": "regex""#, "/entries/0/match"),
            (r#""status": "maybe""#, "/entries/0/status"),
            (r#""deviation": "brand-1""#, "/entries/0/deviation"),
            (
                r#""naming": {"section": "2.1"}"#,
                "/entries/0/naming/section",
            ),
            (r#""open": "X2""#, "/entries/0/open"),
        ];
        for (field, pointer) in cases {
            let key = field.split('"').nth(1).unwrap();
            let mut v: serde_json::Value = serde_json::from_str(LOG).unwrap();
            let patch: serde_json::Value = serde_json::from_str(&format!("{{{field}}}")).unwrap();
            v[key] = patch[key].clone();
            let err = map(&v.to_string()).unwrap_err();
            assert_eq!(err.pointer, pointer, "{field}: {err}");
        }
    }

    #[test]
    fn duplicate_rename_and_unknown_field_are_refused() {
        let err = map(&format!("{LOG}, {LOG}")).unwrap_err();
        assert_eq!(err.pointer, "/entries/1");
        let err = RenameMap::from_json_str(r#"{"entries": [], "x": 1}"#).unwrap_err();
        assert_eq!(err.kind, ErrorKind::UnknownField { field: "x".into() });
        let err = RenameMap::from_json_str(r#"{"entries": []}"#).unwrap_err();
        assert_eq!(err.kind, ErrorKind::Empty);
    }

    #[test]
    fn pattern_placeholders_must_agree() {
        let err = map(
            r#"{"old": "a-<x>", "new": "b-<y>", "scope": "file", "match": "pattern",
                "status": "decided", "deviation": "BRAND-1.3", "naming": {"section": "3.6"}}"#,
        )
        .unwrap_err();
        assert_eq!(err.pointer, "/entries/0/new");
        let err = map(
            r#"{"old": "a-x", "new": "b-x", "scope": "file", "match": "pattern",
                "status": "decided", "deviation": "BRAND-1.3", "naming": {"section": "3.6"}}"#,
        )
        .unwrap_err();
        assert_eq!(err.pointer, "/entries/0/old");
    }

    #[test]
    fn deviation_ids() {
        for ok in ["BRAND-1", "BRAND-1.5", "PLAN-2", "P-13", "SEC-1.1"] {
            assert!(is_deviation_id(ok), "{ok}");
        }
        for bad in [
            "", "BRAND", "brand-1", "BRAND-", "BRAND-1.", "-1", "B-1.2.3", "BRAND-x",
        ] {
            assert!(!is_deviation_id(bad), "{bad}");
        }
    }

    #[test]
    fn pattern_split_keeps_angle_text_that_is_not_a_hole() {
        assert_eq!(
            split_pattern("a<b>c<D>e<>f"),
            vec![
                Piece::Literal("a"),
                Piece::Hole("b"),
                Piece::Literal("c<"),
                Piece::Literal("D>e<"),
                Piece::Literal(">f"),
            ]
        );
    }
}
