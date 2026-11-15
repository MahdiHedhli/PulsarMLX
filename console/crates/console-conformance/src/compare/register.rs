//! The set of approved deviation ids, read from the index of
//! `specs/022-console-serving-parity/contracts/deviations.md`.
//!
//! The register's rules (its section "How to read this register") are what this reader
//! encodes: the ids in the section "Index" are the approved ones (the SEC, PRIV, BRAND,
//! LIC, POL, PLAT, FIX and PLAN ids, and the P- ids of "Approved proposals"); a sub-item
//! `<id>.<n>` listed in a table row of the register is approved with its id; the P- ids
//! of "Declined proposals" and of "Deferred, awaiting owner decision" are not approved,
//! and an annotation that cites one fails. Any other id is unknown and fails too.

use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

/// The largest register text read.
pub const MAX_REGISTER_BYTES: usize = 1024 * 1024;

/// What the register says about one id.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IdStatus {
    /// Listed in the index (or a sub-item of an indexed id): approved by the owner.
    Approved,
    /// Listed under "Declined proposals".
    Declined,
    /// Listed under "Deferred, awaiting owner decision".
    AwaitingOwner,
    /// Not in the register.
    Unknown,
}

impl IdStatus {
    /// A short word for reports.
    pub fn as_str(self) -> &'static str {
        match self {
            IdStatus::Approved => "approved",
            IdStatus::Declined => "declined",
            IdStatus::AwaitingOwner => "awaiting the owner",
            IdStatus::Unknown => "not in the register",
        }
    }
}

/// A register the reader cannot use.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RegisterError {
    /// The 1-based line, or 0 for the whole text.
    pub line: usize,
    /// What is wrong.
    pub message: String,
}

impl fmt::Display for RegisterError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "deviations.md line {}: {}", self.line, self.message)
    }
}

impl std::error::Error for RegisterError {}

/// The approved deviation ids, and the ids the register keeps as not approved.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct ApprovedIds {
    approved: BTreeSet<String>,
    not_approved: BTreeMap<String, IdStatus>,
}

/// `SEC-1`, `PLAN-6`, `P-13`: upper-case letters, a hyphen, a number without a leading
/// zero.
fn is_id(s: &str) -> bool {
    let Some((letters, number)) = s.split_once('-') else {
        return false;
    };
    !letters.is_empty() && letters.bytes().all(|c| c.is_ascii_uppercase()) && is_number(number)
}

fn is_number(s: &str) -> bool {
    !s.is_empty() && !s.starts_with('0') && s.bytes().all(|c| c.is_ascii_digit())
}

/// The first cell of a Markdown table row, trimmed; `None` for a non-row or a separator.
fn first_cell(line: &str) -> Option<&str> {
    let rest = line.trim_start().strip_prefix('|')?;
    let cell = rest.split('|').next()?.trim();
    (!cell.is_empty() && !cell.bytes().all(|c| c == b'-' || c == b':' || c == b' ')).then_some(cell)
}

impl ApprovedIds {
    /// A set built from lists: `approved` ids (and sub-items), and ids known to be not
    /// approved with their status. An id given in both is not approved.
    pub fn from_ids<'a>(
        approved: impl IntoIterator<Item = &'a str>,
        not_approved: impl IntoIterator<Item = (&'a str, IdStatus)>,
    ) -> Self {
        let mut out = Self::default();
        for (id, status) in not_approved {
            if status != IdStatus::Approved {
                out.not_approved.insert(id.to_string(), status);
            }
        }
        for id in approved {
            if !out.not_approved.contains_key(id) {
                out.approved.insert(id.to_string());
            }
        }
        out
    }

    /// Reads the register's Markdown text.
    pub fn from_register(text: &str) -> Result<Self, RegisterError> {
        if text.len() > MAX_REGISTER_BYTES {
            return Err(RegisterError {
                line: 0,
                message: format!("larger than {MAX_REGISTER_BYTES} bytes"),
            });
        }
        #[derive(PartialEq)]
        enum Section {
            Other,
            Index,
            Declined,
            Deferred,
        }
        let mut section = Section::Other;
        let mut index: Vec<(usize, String)> = Vec::new();
        let mut not_approved: BTreeMap<String, IdStatus> = BTreeMap::new();
        let mut headings: BTreeSet<String> = BTreeSet::new();
        let mut sub_rows: Vec<(usize, String)> = Vec::new();
        let mut saw_index = false;
        for (n, line) in text.lines().enumerate() {
            let lineno = n + 1;
            if let Some(h) = line.strip_prefix("## ") {
                let h = h.trim();
                section = match h {
                    "Index" => {
                        saw_index = true;
                        Section::Index
                    }
                    "Declined proposals" => Section::Declined,
                    "Deferred, awaiting owner decision" => Section::Deferred,
                    _ => Section::Other,
                };
                headings.insert(h.to_string());
                continue;
            }
            if let Some(h) = line.strip_prefix("### ") {
                headings.insert(h.trim().to_string());
                continue;
            }
            let Some(cell) = first_cell(line) else {
                continue;
            };
            match section {
                Section::Index => {
                    if cell == "Id" {
                        continue;
                    }
                    let id = cell
                        .strip_prefix('[')
                        .and_then(|c| c.split_once(']'))
                        .map(|(id, _)| id)
                        .filter(|id| is_id(id))
                        .ok_or_else(|| RegisterError {
                            line: lineno,
                            message: format!("an index row does not start with [<id>]: {cell:?}"),
                        })?;
                    index.push((lineno, id.to_string()));
                }
                Section::Declined | Section::Deferred => {
                    if cell == "Ref" {
                        continue;
                    }
                    let id = cell.split_whitespace().next().unwrap_or_default();
                    if !is_id(id) {
                        return Err(RegisterError {
                            line: lineno,
                            message: format!("a proposal row does not start with an id: {cell:?}"),
                        });
                    }
                    let status = if section == Section::Declined {
                        IdStatus::Declined
                    } else {
                        IdStatus::AwaitingOwner
                    };
                    not_approved.insert(id.to_string(), status);
                }
                Section::Other => {
                    if let Some((base, sub)) = cell.rsplit_once('.') {
                        if is_id(base) && is_number(sub) {
                            sub_rows.push((lineno, cell.to_string()));
                        }
                    }
                }
            }
        }
        if !saw_index || index.is_empty() {
            return Err(RegisterError {
                line: 0,
                message: "no section \"Index\" with rows".into(),
            });
        }
        let mut approved = BTreeSet::new();
        for (lineno, id) in &index {
            if not_approved.contains_key(id) {
                return Err(RegisterError {
                    line: *lineno,
                    message: format!("{id} is indexed and also listed as declined or deferred"),
                });
            }
            if !headings.contains(id) {
                return Err(RegisterError {
                    line: *lineno,
                    message: format!("{id} is indexed but has no section of its own"),
                });
            }
            if !approved.insert(id.clone()) {
                return Err(RegisterError {
                    line: *lineno,
                    message: format!("{id} is indexed twice"),
                });
            }
        }
        for (lineno, sub) in sub_rows {
            let base = sub.rsplit_once('.').map(|(b, _)| b).unwrap_or_default();
            if approved.contains(base) {
                approved.insert(sub);
            } else if !not_approved.contains_key(base) {
                return Err(RegisterError {
                    line: lineno,
                    message: format!("sub-item {sub} of an id that is not indexed"),
                });
            }
        }
        Ok(Self {
            approved,
            not_approved,
        })
    }

    /// What the register says about `id`.
    pub fn status(&self, id: &str) -> IdStatus {
        if self.approved.contains(id) {
            return IdStatus::Approved;
        }
        if let Some(s) = self.not_approved.get(id) {
            return *s;
        }
        // a sub-item of a declined or deferred proposal is not approved either
        if let Some((base, sub)) = id.rsplit_once('.') {
            if is_number(sub) {
                if let Some(s) = self.not_approved.get(base) {
                    return *s;
                }
            }
        }
        IdStatus::Unknown
    }

    /// Whether `id` is approved.
    pub fn is_approved(&self, id: &str) -> bool {
        self.status(id) == IdStatus::Approved
    }

    /// The approved ids and sub-items, sorted.
    pub fn approved(&self) -> impl Iterator<Item = &str> {
        self.approved.iter().map(String::as_str)
    }

    /// The approved top-level ids (no sub-items), sorted.
    pub fn approved_entries(&self) -> impl Iterator<Item = &str> {
        self.approved
            .iter()
            .filter(|id| !id.contains('.'))
            .map(String::as_str)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = "# Deviation Register\n\n## Index\n\n| Id | Short title | Packages |\n| --- | --- | --- |\n| [SEC-1](#sec-1) | Host | API-02 |\n| [P-1](#p-1) | Server | API-02 |\n\n## SEC-1\n\n| Sub-item | Difference |\n| --- | --- |\n| SEC-1.1 | Host allowlist |\n\n## Approved proposals\n\n### P-1\n\ntext\n\n## Declined proposals\n\n| Ref | Proposed difference |\n| --- | --- |\n| P-12 (declined) | x |\n\n## Deferred, awaiting owner decision\n\n| Ref | Proposed difference |\n| --- | --- |\n| P-5 | y |\n";

    #[test]
    fn reads_index_sub_items_and_refused_ids() {
        let ids = ApprovedIds::from_register(SAMPLE).unwrap_or_else(|e| panic!("{e}"));
        assert_eq!(
            ids.approved().collect::<Vec<_>>(),
            ["P-1", "SEC-1", "SEC-1.1"]
        );
        assert_eq!(ids.status("SEC-1.1"), IdStatus::Approved);
        assert_eq!(ids.status("SEC-1.2"), IdStatus::Unknown);
        assert_eq!(ids.status("P-12"), IdStatus::Declined);
        assert_eq!(ids.status("P-5"), IdStatus::AwaitingOwner);
        assert_eq!(ids.status("P-5.1"), IdStatus::AwaitingOwner);
        assert_eq!(ids.status("P-2"), IdStatus::Unknown);
    }

    #[test]
    fn refuses_an_inconsistent_register() {
        let both = SAMPLE.replace("| P-5 | y |", "| P-1 | y |");
        assert!(ApprovedIds::from_register(&both).is_err());
        let no_section = SAMPLE.replace("### P-1", "### P-one");
        assert!(ApprovedIds::from_register(&no_section).is_err());
        let orphan = SAMPLE.replace("| SEC-1.1 |", "| SEC-9.1 |");
        assert!(ApprovedIds::from_register(&orphan).is_err());
        assert!(ApprovedIds::from_register("# nothing\n").is_err());
        let bad_row = SAMPLE.replace("| [P-1](#p-1) |", "| P-1 |");
        assert!(ApprovedIds::from_register(&bad_row).is_err());
    }

    #[test]
    fn from_ids_keeps_refused_ids_out() {
        let ids = ApprovedIds::from_ids(["SEC-1", "P-19"], [("P-19", IdStatus::AwaitingOwner)]);
        assert!(ids.is_approved("SEC-1"));
        assert_eq!(ids.status("P-19"), IdStatus::AwaitingOwner);
    }
}
