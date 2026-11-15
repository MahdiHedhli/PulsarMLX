//! Owned by CNF-04. The structural comparator with deviation annotations.
//!
//! [`compare`] walks two normalized documents ([`crate::normalize::Normalized`]) side by
//! side and reports every difference with a JSON pointer:
//!
//! - a value that differs, including a number written differently (`1` and `1.0` are
//!   different tokens) and a change of type;
//! - a member or element present on one side only;
//! - members in a different order (JSON key order is observable,
//!   `contracts/parity-ledger.md` section 1.1, so a key-order difference is a
//!   difference, not an advisory note);
//! - a long text (a body, a raw head) that differs, with the first differing character
//!   and an excerpt of each side;
//! - each problem the normalizer found on either side ([`crate::normalize::Issue`]).
//!
//! A difference is suppressed only by an [`Annotation`] that names an approved id of the
//! deviation register (read by [`ApprovedIds`]) and whose pointer pattern, and expected
//! values when given, match it. An annotation must say what it covers: the kind of
//! difference ([`CoveredKind`]), or both expected values; one that gives neither (or only
//! one expected value and no kind) is refused and suppresses nothing, so that an exact
//! pointer alone never suppresses every kind of difference at it. A text difference shows
//! excerpts, so only an annotation of kind text covers one, and its expected values are
//! compared with the whole texts, never with the excerpts. An annotation that
//! cites a declined proposal, a proposal still awaiting the owner (P-5 and P-18 to P-27 at
//! the time of writing) or an id the register does not hold is an error that fails the
//! comparison, and suppresses nothing.
//! An annotation that suppresses nothing is reported as unused.
//!
//! There is no header allowlist: every header is compared by name (with its case), value
//! and position, and only the values the volatile list names were replaced by the
//! normalizer.

pub mod register;

use std::fmt;

use serde_json::{json, Map, Value};

use crate::normalize::{NormalizeError, Normalized, Normalizer, Side, SideContext};
use crate::scenario::{RenameMap, Status};

pub use register::{ApprovedIds, IdStatus, RegisterError, MAX_REGISTER_BYTES};

/// The most differences a report holds; past it the report is marked truncated and does
/// not pass.
pub const MAX_DIFFERENCES: usize = 1000;

/// A string longer than this (in characters), or holding a line break, is reported as a
/// text difference with excerpts instead of whole.
pub const LONG_TEXT_CHARS: usize = 120;

/// Characters of context on each side of the first difference in a text excerpt.
pub const EXCERPT_CHARS: usize = 40;

/// The most annotations one comparison takes.
pub const MAX_ANNOTATIONS: usize = 4096;

/// The kind of difference an annotation covers.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CoveredKind {
    /// The values differ ([`DiffKind::Value`]).
    Value,
    /// Present on the reference side only ([`DiffKind::Missing`]).
    Missing,
    /// Present on the candidate side only ([`DiffKind::Extra`]).
    Extra,
    /// The same members in another order ([`DiffKind::KeyOrder`]).
    KeyOrder,
    /// Two long texts differ ([`DiffKind::Text`], at any offset).
    Text,
}

impl CoveredKind {
    /// Every kind, in the order of [`DiffKind`].
    pub const ALL: &'static [CoveredKind] = &[
        CoveredKind::Value,
        CoveredKind::Missing,
        CoveredKind::Extra,
        CoveredKind::KeyOrder,
        CoveredKind::Text,
    ];

    /// The kind as a report and an annotation list write it (as [`Difference::to_json`]
    /// writes the kind of a difference).
    pub fn as_str(self) -> &'static str {
        match self {
            CoveredKind::Value => "value",
            CoveredKind::Missing => "missing",
            CoveredKind::Extra => "extra",
            CoveredKind::KeyOrder => "key-order",
            CoveredKind::Text => "text",
        }
    }

    /// The kind written `s`.
    pub fn parse(s: &str) -> Option<Self> {
        Self::ALL.iter().copied().find(|k| k.as_str() == s)
    }

    /// Whether a difference of kind `d` is of this kind. A normalization problem is of
    /// no kind an annotation covers.
    pub fn covers(self, d: &DiffKind) -> bool {
        matches!(
            (self, d),
            (CoveredKind::Value, DiffKind::Value)
                | (CoveredKind::Missing, DiffKind::Missing)
                | (CoveredKind::Extra, DiffKind::Extra)
                | (CoveredKind::KeyOrder, DiffKind::KeyOrder)
                | (CoveredKind::Text, DiffKind::Text { .. })
        )
    }
}

/// A deviation annotation: a difference the register approves.
#[derive(Debug, Clone, PartialEq)]
pub struct Annotation {
    /// The approved id or sub-item id, for example `P-1` or `SEC-1.1`.
    pub deviation: String,
    /// A JSON pointer into the comparison document; a segment `*` matches any one
    /// segment other than the last, and a pointer with one needs `reference` or
    /// `candidate`. It matches a difference's pointer exactly, never a prefix of it.
    pub pointer: String,
    /// The kind of difference it covers. Without it, both `reference` and `candidate`
    /// are required, and it never covers a text difference.
    pub kind: Option<CoveredKind>,
    /// When given, the reference value the difference must show (for a text
    /// difference, the whole text at the pointer, not the excerpt).
    pub reference: Option<Value>,
    /// When given, the candidate value the difference must show.
    pub candidate: Option<Value>,
    /// Why, for the reviewer.
    pub note: Option<String>,
}

impl Annotation {
    /// An annotation without a kind or expected values: it is refused until
    /// [`Annotation::covering`] or [`Annotation::expecting`] says what it covers.
    pub fn new(deviation: &str, pointer: &str) -> Self {
        Self {
            deviation: deviation.to_string(),
            pointer: pointer.to_string(),
            kind: None,
            reference: None,
            candidate: None,
            note: None,
        }
    }

    /// Covering differences of `kind` only.
    pub fn covering(mut self, kind: CoveredKind) -> Self {
        self.kind = Some(kind);
        self
    }

    /// With the values the difference must show.
    pub fn expecting(mut self, reference: Option<Value>, candidate: Option<Value>) -> Self {
        self.reference = reference;
        self.candidate = candidate;
        self
    }

    /// Reads a list of annotations: an array of objects with `deviation` and `pointer`,
    /// and optionally `kind` (one of the names of [`CoveredKind::as_str`]), `reference`,
    /// `candidate` and `note`; no other member.
    pub fn list_from_json(v: &Value) -> Result<Vec<Annotation>, AnnotationError> {
        let bad = |index: usize, why: &str| AnnotationError {
            index,
            deviation: String::new(),
            problem: AnnotationProblem::Shape(why.to_string()),
        };
        let items = v
            .as_array()
            .ok_or_else(|| bad(0, "the annotations are not an array"))?;
        if items.len() > MAX_ANNOTATIONS {
            return Err(bad(0, "too many annotations"));
        }
        let mut out = Vec::new();
        for (i, item) in items.iter().enumerate() {
            let o = item.as_object().ok_or_else(|| bad(i, "not an object"))?;
            if let Some(k) = o.keys().find(|k| {
                ![
                    "deviation",
                    "pointer",
                    "kind",
                    "reference",
                    "candidate",
                    "note",
                ]
                .contains(&k.as_str())
            }) {
                return Err(bad(i, &format!("unknown member {k:?}")));
            }
            let text = |k: &str| o.get(k).and_then(Value::as_str).map(str::to_string);
            out.push(Annotation {
                deviation: text("deviation").ok_or_else(|| bad(i, "deviation is not a string"))?,
                pointer: text("pointer").ok_or_else(|| bad(i, "pointer is not a string"))?,
                kind: match o.get("kind") {
                    None => None,
                    Some(k) => Some(
                        k.as_str()
                            .and_then(CoveredKind::parse)
                            .ok_or_else(|| bad(i, "kind is not a kind of difference"))?,
                    ),
                },
                reference: o.get("reference").cloned(),
                candidate: o.get("candidate").cloned(),
                note: match o.get("note") {
                    None => None,
                    Some(n) => Some(
                        n.as_str()
                            .ok_or_else(|| bad(i, "note is not a string"))?
                            .to_string(),
                    ),
                },
            });
        }
        Ok(out)
    }

    /// Whether it covers `d`, a difference between the documents `reference` and
    /// `candidate`. A text difference shows excerpts, which do not identify a text: only
    /// an annotation of kind text covers one, and its expected values, when given, are
    /// compared with the whole texts at the difference's pointer, never with the
    /// excerpts (so that values written for one change do not hide a later one).
    fn matches(&self, d: &Difference, reference: &Value, candidate: &Value) -> bool {
        if !pointer_matches(&self.pointer, &d.pointer) {
            return false;
        }
        let (r_shown, c_shown) = match d.kind {
            DiffKind::Text { .. } => {
                if self.kind != Some(CoveredKind::Text) {
                    return false;
                }
                (reference.pointer(&d.pointer), candidate.pointer(&d.pointer))
            }
            _ => (d.reference.as_ref(), d.candidate.as_ref()),
        };
        self.kind.is_none_or(|k| k.covers(&d.kind))
            && self.reference.as_ref().is_none_or(|r| r_shown == Some(r))
            && self.candidate.as_ref().is_none_or(|c| c_shown == Some(c))
    }
}

fn pointer_matches(pattern: &str, pointer: &str) -> bool {
    if pattern.is_empty() || pointer.is_empty() {
        return pattern == pointer;
    }
    let (Some(p), Some(q)) = (pattern.strip_prefix('/'), pointer.strip_prefix('/')) else {
        return false;
    };
    let ps: Vec<&str> = p.split('/').collect();
    let qs: Vec<&str> = q.split('/').collect();
    ps.len() == qs.len() && ps.iter().zip(&qs).all(|(a, b)| *a == "*" || a == b)
}

/// Why an annotation is refused for its shape. Every annotation says what it covers: the
/// kind of difference, or both expected values (an exact pointer alone would suppress a
/// missing member, an extra one, a key-order change and any value at once). Without a
/// kind, it never covers a text difference, whose values are excerpts: a text is covered
/// only by kind text, with the whole texts as its expected values when given. A `*`
/// segment may stand for an exchange, a header or an element, never for the last segment
/// (which would name any member), and a pointer with a `*` must give the value the
/// difference shows on at least one side, so that one approved id cannot suppress
/// unrelated differences.
fn shape_problem(a: &Annotation) -> Option<&'static str> {
    if a.kind.is_none() && (a.reference.is_none() || a.candidate.is_none()) {
        return Some(
            "an annotation names the kind of difference it covers, or gives both the reference and the candidate value",
        );
    }
    let segments: Vec<&str> = a.pointer.split('/').skip(1).collect();
    if !segments.contains(&"*") {
        return None;
    }
    if segments.last() == Some(&"*") {
        return Some("a wildcard pointer may not end in *");
    }
    if a.reference.is_none() && a.candidate.is_none() {
        return Some("a wildcard pointer needs the reference or the candidate value it expects");
    }
    None
}

/// What is wrong with an annotation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AnnotationProblem {
    /// The id is not approved: declined, awaiting the owner, or not in the register.
    NotApproved(IdStatus),
    /// The pointer is not a JSON pointer.
    BadPointer,
    /// The annotation list is malformed.
    Shape(String),
}

/// An annotation that fails the comparison.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AnnotationError {
    /// Its index in the list given.
    pub index: usize,
    /// The id it cites.
    pub deviation: String,
    /// What is wrong.
    pub problem: AnnotationProblem,
}

impl fmt::Display for AnnotationError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match &self.problem {
            AnnotationProblem::NotApproved(s) => write!(
                f,
                "annotation {} cites {}, which is {}: only an approved id of deviations.md suppresses a difference",
                self.index,
                self.deviation,
                s.as_str()
            ),
            AnnotationProblem::BadPointer => {
                write!(f, "annotation {} has a pointer that is not a JSON pointer", self.index)
            }
            AnnotationProblem::Shape(why) => write!(f, "annotation {}: {why}", self.index),
        }
    }
}

impl std::error::Error for AnnotationError {}

/// The kind of a difference.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DiffKind {
    /// The values differ (or their types do).
    Value,
    /// Present on the reference side only.
    Missing,
    /// Present on the candidate side only.
    Extra,
    /// The same members in a different order; the values are the two key lists.
    KeyOrder,
    /// Two texts differ from this character on; the values are excerpts.
    Text {
        /// The first differing character, counted in characters from 0.
        offset: usize,
    },
    /// A problem the normalizer found on one side.
    Normalization(Side),
}

impl DiffKind {
    fn as_str(&self) -> &'static str {
        match self {
            DiffKind::Value => "value",
            DiffKind::Missing => "missing",
            DiffKind::Extra => "extra",
            DiffKind::KeyOrder => "key-order",
            DiffKind::Text { .. } => "text",
            DiffKind::Normalization(_) => "normalization",
        }
    }
}

/// One difference.
#[derive(Debug, Clone, PartialEq)]
pub struct Difference {
    /// A JSON pointer into the comparison document.
    pub pointer: String,
    /// What kind.
    pub kind: DiffKind,
    /// The reference side's value (an excerpt for a text, the message for a
    /// normalization problem).
    pub reference: Option<Value>,
    /// The candidate side's value.
    pub candidate: Option<Value>,
    /// A rename-map proposal that would explain the difference, cited by its deviation
    /// id; the difference still counts, because a proposed value is not decided.
    pub hint: Option<String>,
}

impl Difference {
    /// The difference as JSON.
    pub fn to_json(&self) -> Value {
        let mut m = Map::new();
        m.insert("pointer".into(), json!(self.pointer));
        m.insert("kind".into(), json!(self.kind.as_str()));
        match &self.kind {
            DiffKind::Text { offset } => {
                m.insert("offset".into(), json!(offset));
            }
            DiffKind::Normalization(side) => {
                m.insert(
                    "side".into(),
                    json!(match side {
                        Side::Reference => "reference",
                        Side::Candidate => "candidate",
                    }),
                );
            }
            _ => {}
        }
        m.insert(
            "reference".into(),
            self.reference.clone().unwrap_or(Value::Null),
        );
        m.insert(
            "candidate".into(),
            self.candidate.clone().unwrap_or(Value::Null),
        );
        if let Some(h) = &self.hint {
            m.insert("hint".into(), json!(h));
        }
        Value::Object(m)
    }
}

/// A difference an annotation suppressed.
#[derive(Debug, Clone, PartialEq)]
pub struct Suppression {
    /// The difference.
    pub difference: Difference,
    /// The index of the annotation that suppressed it.
    pub annotation: usize,
    /// Its deviation id.
    pub deviation: String,
}

/// The result of one comparison.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Report {
    /// Differences no annotation suppressed.
    pub differences: Vec<Difference>,
    /// Differences an approved annotation suppressed.
    pub suppressed: Vec<Suppression>,
    /// Annotations that fail the comparison.
    pub annotation_errors: Vec<AnnotationError>,
    /// Indexes of valid annotations that suppressed nothing (a warning).
    pub unused_annotations: Vec<usize>,
    /// More than [`MAX_DIFFERENCES`] differences were found; the rest are not listed.
    pub truncated: bool,
}

impl Report {
    /// No unsuppressed difference, no annotation error, nothing truncated.
    pub fn passed(&self) -> bool {
        self.differences.is_empty() && self.annotation_errors.is_empty() && !self.truncated
    }

    /// Passed, and no annotation went unused.
    pub fn clean(&self) -> bool {
        self.passed() && self.unused_annotations.is_empty()
    }

    /// The report as JSON.
    pub fn to_json(&self) -> Value {
        json!({
            "passed": self.passed(),
            "differences": self.differences.iter().map(Difference::to_json).collect::<Vec<_>>(),
            "suppressed": self.suppressed.iter().map(|s| json!({
                "deviation": s.deviation,
                "annotation": s.annotation,
                "difference": s.difference.to_json(),
            })).collect::<Vec<_>>(),
            "annotation_errors": self.annotation_errors.iter().map(|e| json!({
                "annotation": e.index,
                "deviation": e.deviation,
                "error": e.to_string(),
            })).collect::<Vec<_>>(),
            "unused_annotations": self.unused_annotations,
            "truncated": self.truncated,
        })
    }
}

/// Compares two normalized sides. `renames`, when given, adds a hint to a difference
/// that one of its `proposed` entries would explain.
pub fn compare(
    reference: &Normalized,
    candidate: &Normalized,
    annotations: &[Annotation],
    approved: &ApprovedIds,
    renames: Option<&RenameMap>,
) -> Report {
    let mut found = Vec::new();
    let mut truncated = false;
    {
        let mut push = |d: Difference| {
            if found.len() < MAX_DIFFERENCES {
                found.push(d);
            } else {
                truncated = true;
            }
        };
        for (n, want) in [(reference, Side::Reference), (candidate, Side::Candidate)] {
            if n.side != want {
                push(Difference {
                    pointer: String::new(),
                    kind: DiffKind::Normalization(want),
                    reference: Some(json!("this side was normalized as the other side")),
                    candidate: None,
                    hint: None,
                });
            }
            for issue in &n.issues {
                push(Difference {
                    pointer: issue.pointer.clone(),
                    kind: DiffKind::Normalization(want),
                    reference: Some(json!(issue.message)),
                    candidate: None,
                    hint: None,
                });
            }
        }
        diff(
            &reference.document,
            &candidate.document,
            &mut String::new(),
            &mut push,
        );
    }

    let mut report = Report {
        truncated,
        ..Report::default()
    };
    let mut valid = vec![false; annotations.len()];
    for (i, a) in annotations.iter().enumerate().take(MAX_ANNOTATIONS) {
        let pointer_ok = a.pointer.is_empty() || a.pointer.starts_with('/');
        let status = approved.status(&a.deviation);
        if status != IdStatus::Approved {
            report.annotation_errors.push(AnnotationError {
                index: i,
                deviation: a.deviation.clone(),
                problem: AnnotationProblem::NotApproved(status),
            });
        } else if !pointer_ok {
            report.annotation_errors.push(AnnotationError {
                index: i,
                deviation: a.deviation.clone(),
                problem: AnnotationProblem::BadPointer,
            });
        } else if let Some(why) = shape_problem(a) {
            report.annotation_errors.push(AnnotationError {
                index: i,
                deviation: a.deviation.clone(),
                problem: AnnotationProblem::Shape(why.into()),
            });
        } else if let Some(v) = valid.get_mut(i) {
            *v = true;
        }
    }
    if annotations.len() > MAX_ANNOTATIONS {
        report.annotation_errors.push(AnnotationError {
            index: MAX_ANNOTATIONS,
            deviation: String::new(),
            problem: AnnotationProblem::Shape("too many annotations".into()),
        });
    }
    let mut used = vec![false; annotations.len()];
    for mut d in found {
        let by = annotations.iter().enumerate().find(|(i, a)| {
            valid.get(*i).copied().unwrap_or(false)
                && !matches!(d.kind, DiffKind::Normalization(_))
                && a.matches(&d, &reference.document, &candidate.document)
        });
        match by {
            Some((i, a)) => {
                if let Some(u) = used.get_mut(i) {
                    *u = true;
                }
                report.suppressed.push(Suppression {
                    difference: d,
                    annotation: i,
                    deviation: a.deviation.clone(),
                });
            }
            None => {
                if let Some(r) = renames {
                    d.hint = hint(r, &d);
                }
                report.differences.push(d);
            }
        }
    }
    report.unused_annotations = (0..annotations.len())
        .filter(|i| {
            valid.get(*i).copied().unwrap_or(false) && !used.get(*i).copied().unwrap_or(false)
        })
        .collect();
    report
}

/// Normalizes both observation documents and compares them.
#[allow(clippy::too_many_arguments)]
pub fn compare_documents(
    normalizer: &Normalizer,
    reference: &Value,
    reference_ctx: &SideContext,
    candidate: &Value,
    candidate_ctx: &SideContext,
    annotations: &[Annotation],
    approved: &ApprovedIds,
) -> Result<Report, NormalizeError> {
    let r = normalizer.normalize(reference, Side::Reference, reference_ctx)?;
    let c = normalizer.normalize(candidate, Side::Candidate, candidate_ctx)?;
    Ok(compare(
        &r,
        &c,
        annotations,
        approved,
        Some(normalizer.renames()),
    ))
}

fn hint(renames: &RenameMap, d: &Difference) -> Option<String> {
    let (Some(Value::String(r)), Some(Value::String(c))) = (&d.reference, &d.candidate) else {
        return None;
    };
    renames
        .entries
        .iter()
        .filter(|e| e.status == Status::Proposed)
        .find(|e| e.apply(r).as_deref() == Some(c.as_str()))
        .map(|e| {
            format!(
                "the proposed rename {:?} to {:?} ({}, naming.md section {}) would explain it; a proposed value is not decided",
                e.old,
                e.new.as_deref().unwrap_or_default(),
                e.deviation,
                e.naming.section
            )
        })
}

fn is_long(s: &str) -> bool {
    s.contains('\n') || s.chars().count() > LONG_TEXT_CHARS
}

fn excerpt(s: &str, offset: usize) -> String {
    let from = offset.saturating_sub(EXCERPT_CHARS);
    s.chars().skip(from).take(2 * EXCERPT_CHARS).collect()
}

/// The deepest nesting the comparator walks; below it two values are compared whole
/// and reported as one difference.
pub const MAX_DIFF_DEPTH: usize = 512;

fn diff(a: &Value, b: &Value, path: &mut String, push: &mut impl FnMut(Difference)) {
    diff_at(a, b, path, push, 0);
}

fn diff_at(
    a: &Value,
    b: &Value,
    path: &mut String,
    push: &mut impl FnMut(Difference),
    depth: usize,
) {
    let deeper = depth < MAX_DIFF_DEPTH;
    match (a, b) {
        (Value::Object(x), Value::Object(y)) if deeper => {
            for (k, v) in x {
                if !y.contains_key(k) {
                    push(Difference {
                        pointer: format!("{path}/{}", crate::normalize::pointer_segment(k)),
                        kind: DiffKind::Missing,
                        reference: Some(v.clone()),
                        candidate: None,
                        hint: None,
                    });
                }
            }
            for (k, v) in y {
                if !x.contains_key(k) {
                    push(Difference {
                        pointer: format!("{path}/{}", crate::normalize::pointer_segment(k)),
                        kind: DiffKind::Extra,
                        reference: None,
                        candidate: Some(v.clone()),
                        hint: None,
                    });
                }
            }
            let ka: Vec<&String> = x.keys().filter(|k| y.contains_key(*k)).collect();
            let kb: Vec<&String> = y.keys().filter(|k| x.contains_key(*k)).collect();
            if ka != kb {
                push(Difference {
                    pointer: path.clone(),
                    kind: DiffKind::KeyOrder,
                    reference: Some(json!(ka)),
                    candidate: Some(json!(kb)),
                    hint: None,
                });
            }
            for k in ka {
                if let (Some(va), Some(vb)) = (x.get(k), y.get(k)) {
                    let len = path.len();
                    path.push('/');
                    path.push_str(&crate::normalize::pointer_segment(k));
                    diff_at(va, vb, path, push, depth + 1);
                    path.truncate(len);
                }
            }
        }
        (Value::Array(x), Value::Array(y)) if deeper => {
            for i in 0..x.len().max(y.len()) {
                let len = path.len();
                path.push('/');
                path.push_str(&i.to_string());
                match (x.get(i), y.get(i)) {
                    (Some(va), Some(vb)) => diff_at(va, vb, path, push, depth + 1),
                    (Some(va), None) => push(Difference {
                        pointer: path.clone(),
                        kind: DiffKind::Missing,
                        reference: Some(va.clone()),
                        candidate: None,
                        hint: None,
                    }),
                    (None, Some(vb)) => push(Difference {
                        pointer: path.clone(),
                        kind: DiffKind::Extra,
                        reference: None,
                        candidate: Some(vb.clone()),
                        hint: None,
                    }),
                    (None, None) => {}
                }
                path.truncate(len);
            }
        }
        (Value::String(x), Value::String(y)) if x != y && (is_long(x) || is_long(y)) => {
            let offset = x.chars().zip(y.chars()).take_while(|(p, q)| p == q).count();
            push(Difference {
                pointer: path.clone(),
                kind: DiffKind::Text { offset },
                reference: Some(json!(excerpt(x, offset))),
                candidate: Some(json!(excerpt(y, offset))),
                hint: None,
            });
        }
        _ => {
            if a != b {
                push(Difference {
                    pointer: path.clone(),
                    kind: DiffKind::Value,
                    reference: Some(a.clone()),
                    candidate: Some(b.clone()),
                    hint: None,
                });
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn norm(side: Side, document: Value) -> Normalized {
        Normalized {
            side,
            document,
            applied: Vec::new(),
            applied_truncated: false,
            issues: Vec::new(),
        }
    }

    fn run(a: Value, b: Value, ann: &[Annotation]) -> Report {
        let ids = ApprovedIds::from_ids(
            ["P-1", "SEC-1.1"],
            [
                ("P-19", IdStatus::AwaitingOwner),
                ("P-12", IdStatus::Declined),
            ],
        );
        compare(
            &norm(Side::Reference, a),
            &norm(Side::Candidate, b),
            ann,
            &ids,
            None,
        )
    }

    #[test]
    fn key_order_is_a_difference() {
        let r = run(json!({"a": 1, "b": 2}), json!({"b": 2, "a": 1}), &[]);
        assert!(!r.passed());
        assert_eq!(r.differences.len(), 1);
        assert_eq!(r.differences[0].kind, DiffKind::KeyOrder);
        assert_eq!(r.differences[0].pointer, "");
    }

    #[test]
    fn numbers_compare_as_written() {
        let a: Value = serde_json::from_str(r#"{"x": 1}"#).unwrap_or_default();
        let b: Value = serde_json::from_str(r#"{"x": 1.0}"#).unwrap_or_default();
        let r = run(a, b, &[]);
        assert_eq!(r.differences.len(), 1);
        assert_eq!(r.differences[0].pointer, "/x");
    }

    #[test]
    fn missing_extra_and_text() {
        let long_a = format!("{}A", "x".repeat(200));
        let long_b = format!("{}B", "x".repeat(200));
        let r = run(
            json!({"a": [1, 2], "t": long_a}),
            json!({"a": [1], "c": 3, "t": long_b}),
            &[],
        );
        let kinds: Vec<(&str, &DiffKind)> = r
            .differences
            .iter()
            .map(|d| (d.pointer.as_str(), &d.kind))
            .collect();
        assert_eq!(
            kinds,
            [
                ("/c", &DiffKind::Extra),
                ("/a/1", &DiffKind::Missing),
                ("/t", &DiffKind::Text { offset: 200 })
            ]
        );
    }

    #[test]
    fn annotations_need_an_approved_id_and_an_exact_pointer() {
        let a = json!({"h": "BaseHTTP/0.6 Python/3.14.7", "k": 1});
        let b = json!({"h": "pulsar-console/0.1.0", "k": 1});
        // approved, exact pointer, the kind it covers: suppressed (CNF-04F: an annotation
        // names its kind or both values)
        let value = |id: &str, p: &str| Annotation::new(id, p).covering(CoveredKind::Value);
        let r = run(a.clone(), b.clone(), &[value("P-1", "/h")]);
        assert!(r.clean(), "{:?}", r.to_json());
        // a prefix pointer does not match
        let r = run(
            json!({"o": a.clone()}),
            json!({"o": b.clone()}),
            &[value("P-1", "/o")],
        );
        assert!(!r.passed());
        assert_eq!(r.unused_annotations, [0]);
        // wildcard segment, with the expected value
        let r = run(
            json!({"o": a.clone()}),
            json!({"o": b.clone()}),
            &[value("P-1", "/*/h").expecting(None, Some(json!("pulsar-console/0.1.0")))],
        );
        assert!(r.clean());
        // a wildcard without an expected value, or in the last segment, is refused and
        // suppresses nothing; each annotation names its kind, so that the wildcard rule is
        // the only reason left to refuse it
        for (bad, why) in [
            (value("P-1", "/*/h"), "wildcard pointer needs"),
            (
                value("P-1", "/o/*").expecting(None, Some(json!("pulsar-console/0.1.0"))),
                "may not end in *",
            ),
        ] {
            let r = run(json!({"o": a.clone()}), json!({"o": b.clone()}), &[bad]);
            assert!(!r.passed());
            assert_eq!(r.differences.len(), 1);
            assert!(
                matches!(&r.annotation_errors[0].problem, AnnotationProblem::Shape(s) if s.contains(why)),
                "{:?}",
                r.annotation_errors
            );
        }
        // expected values must match
        let wrong = value("P-1", "/h").expecting(None, Some(json!("other")));
        let r = run(a.clone(), b.clone(), &[wrong]);
        assert!(!r.passed() && r.annotation_errors.is_empty());
        // not approved ids fail and suppress nothing
        // (a well-shaped annotation, so that only the approval check can refuse it)
        for id in ["P-19", "P-12", "P-99", "SEC-1.2"] {
            let r = run(a.clone(), b.clone(), &[value(id, "/h")]);
            assert!(!r.passed(), "{id}");
            assert_eq!(r.differences.len(), 1, "{id}");
            assert_eq!(r.annotation_errors.len(), 1, "{id}");
            assert!(
                matches!(
                    r.annotation_errors[0].problem,
                    AnnotationProblem::NotApproved(_)
                ),
                "{id}"
            );
        }
        // an unused annotation is reported, and does not fail
        let r = run(a.clone(), a.clone(), &[value("SEC-1.1", "/k")]);
        assert!(r.passed() && !r.clean());
        assert_eq!(r.unused_annotations, [0]);
        // a bad pointer
        let r = run(a.clone(), b, &[Annotation::new("P-1", "h")]);
        assert_eq!(
            r.annotation_errors[0].problem,
            AnnotationProblem::BadPointer
        );
    }

    #[test]
    fn an_exact_pointer_alone_suppresses_nothing() {
        // CNF-04F: without a kind and without both values, an annotation is refused; were
        // it accepted, it would swallow each of these differences at /o
        let cases = [
            (json!({"o": 1}), json!({"o": 2})),
            (json!({"o": {"x": 1}}), json!({"o": {}})),
            (json!({"o": {}}), json!({"o": {"x": 1}})),
            (
                json!({"o": {"x": 1, "y": 2}}),
                json!({"o": {"y": 2, "x": 1}}),
            ),
        ];
        for (a, b) in &cases {
            for bare in [
                Annotation::new("P-1", "/o"),
                Annotation::new("P-1", "/o").expecting(Some(a["o"].clone()), None),
                Annotation::new("P-1", "/o").expecting(None, Some(b["o"].clone())),
            ] {
                let r = run(a.clone(), b.clone(), &[bare]);
                assert!(!r.passed(), "{a} {b}");
                assert!(r.suppressed.is_empty(), "{a} {b}");
                assert!(matches!(
                    &r.annotation_errors[0].problem,
                    AnnotationProblem::Shape(s) if s.contains("names the kind of difference")
                ));
            }
        }
        // both values: suppresses the value difference that shows them
        let both = Annotation::new("P-1", "/o").expecting(Some(json!(1)), Some(json!(2)));
        assert!(run(
            json!({"o": 1}),
            json!({"o": 2}),
            std::slice::from_ref(&both)
        )
        .clean());
        // ... and nothing else at that pointer
        let r = run(json!({"o": 1}), json!({"o": 3}), &[both]);
        assert!(!r.passed() && r.unused_annotations == [0]);
    }

    #[test]
    fn an_excerpt_valued_annotation_does_not_hide_a_later_difference() {
        // a text difference shows excerpts; values copied from them must not cover a
        // second change past the excerpt
        let base = "x".repeat(LONG_TEXT_CHARS + 200);
        let mut approved_change = base.clone();
        approved_change.replace_range(10..11, "A");
        let r0 = run(json!({"o": base}), json!({"o": approved_change}), &[]);
        let d = &r0.differences[0];
        assert!(matches!(d.kind, DiffKind::Text { offset: 10 }));
        let mut more = approved_change.clone();
        more.replace_range(150..151, "Z");
        // without a kind, both excerpt values: never a text difference
        let no_kind =
            Annotation::new("P-1", "/o").expecting(d.reference.clone(), d.candidate.clone());
        let r = run(
            json!({"o": base}),
            json!({"o": more}),
            std::slice::from_ref(&no_kind),
        );
        assert!(!r.passed(), "{}", r.to_json());
        assert!(r.suppressed.is_empty());
        // ... not even the one the excerpts were taken from
        let r = run(
            json!({"o": base}),
            json!({"o": approved_change}),
            &[no_kind],
        );
        assert!(!r.passed() && r.unused_annotations == [0]);
        // kind text with the excerpts: compared with the whole texts, so nothing matches
        let text_excerpts = Annotation::new("P-1", "/o")
            .covering(CoveredKind::Text)
            .expecting(d.reference.clone(), d.candidate.clone());
        let r = run(
            json!({"o": base}),
            json!({"o": approved_change}),
            &[text_excerpts],
        );
        assert!(!r.passed());
        // kind text with the whole texts: covers exactly that change, not the wider one
        let whole = Annotation::new("P-1", "/o")
            .covering(CoveredKind::Text)
            .expecting(Some(json!(base)), Some(json!(approved_change)));
        let r = run(
            json!({"o": base}),
            json!({"o": approved_change}),
            std::slice::from_ref(&whole),
        );
        assert!(r.clean(), "{}", r.to_json());
        let r = run(json!({"o": base}), json!({"o": more}), &[whole]);
        assert!(!r.passed() && r.unused_annotations == [0]);
    }

    #[test]
    fn an_annotation_covers_only_its_kind() {
        let missing = Annotation::new("P-1", "/o/x").covering(CoveredKind::Missing);
        // the member is missing: suppressed
        let r = run(
            json!({"o": {"x": 1}}),
            json!({"o": {}}),
            std::slice::from_ref(&missing),
        );
        assert!(r.clean(), "{:?}", r.to_json());
        // the member is there with another value, or only on the candidate side: reported
        for (a, b) in [
            (json!({"o": {"x": 1}}), json!({"o": {"x": 2}})),
            (json!({"o": {}}), json!({"o": {"x": 1}})),
        ] {
            let r = run(a.clone(), b.clone(), std::slice::from_ref(&missing));
            assert!(!r.passed(), "{a} {b}");
            assert_eq!(r.differences.len(), 1);
            assert_eq!(r.unused_annotations, [0]);
        }
        // a key-order annotation does not cover a value under that object, nor a text
        // annotation a short value
        let order = Annotation::new("P-1", "/o").covering(CoveredKind::KeyOrder);
        let r = run(
            json!({"o": {"x": 1, "y": 2}}),
            json!({"o": {"y": 2, "x": 1}}),
            std::slice::from_ref(&order),
        );
        assert!(r.clean());
        let r = run(json!({"o": 1}), json!({"o": 2}), &[order]);
        assert!(!r.passed());
        let text = Annotation::new("P-1", "/o").covering(CoveredKind::Text);
        assert!(!run(
            json!({"o": "a"}),
            json!({"o": "b"}),
            std::slice::from_ref(&text)
        )
        .passed());
        let long = |c: char| format!("{}{c}", "x".repeat(LONG_TEXT_CHARS));
        assert!(run(json!({"o": long('a')}), json!({"o": long('b')}), &[text]).clean());
        // a kind with one value: both must match
        let one = Annotation::new("P-1", "/o")
            .covering(CoveredKind::Value)
            .expecting(None, Some(json!(2)));
        assert!(run(json!({"o": 1}), json!({"o": 2}), std::slice::from_ref(&one)).clean());
        assert!(!run(json!({"o": 1}), json!({"o": 3}), &[one]).passed());
        for k in CoveredKind::ALL {
            assert_eq!(CoveredKind::parse(k.as_str()), Some(*k));
        }
        assert_eq!(CoveredKind::parse("normalization"), None);
    }

    #[test]
    fn annotation_lists_are_read_strictly() {
        let ok = json!([{"deviation": "P-1", "pointer": "/h", "kind": "value", "candidate": "x", "note": "why"}]);
        let list = Annotation::list_from_json(&ok).unwrap_or_default();
        assert_eq!(list.len(), 1);
        assert_eq!(list[0].candidate, Some(json!("x")));
        assert_eq!(list[0].kind, Some(CoveredKind::Value));
        for bad in [
            json!({}),
            json!([{"deviation": "P-1"}]),
            json!([{"deviation": "P-1", "pointer": "/h", "why": 1}]),
            json!([{"deviation": 1, "pointer": "/h"}]),
            json!([{"deviation": "P-1", "pointer": "/h", "kind": "any"}]),
            json!([{"deviation": "P-1", "pointer": "/h", "kind": "normalization"}]),
            json!([{"deviation": "P-1", "pointer": "/h", "kind": 1}]),
        ] {
            assert!(Annotation::list_from_json(&bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn differences_are_capped() {
        let a = Value::Array((0..MAX_DIFFERENCES + 5).map(|i| json!(i)).collect());
        let b = Value::Array((0..MAX_DIFFERENCES + 5).map(|i| json!(i + 1)).collect());
        let r = run(a, b, &[]);
        assert_eq!(r.differences.len(), MAX_DIFFERENCES);
        assert!(r.truncated && !r.passed());
    }
}
