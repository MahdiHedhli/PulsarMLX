//! A turn's figures: the engine's own counts and clock merged over the engine calls of one
//! request, and the llama.cpp-style `timings` computed from them.
//!
//! The donor keeps these in the engine's `last` dictionary, replaced by every `DONE` line;
//! here every engine call returns its own [`Terminal`], and the turn driver merges them.
//! An engine without a clock (the scripted engine) reports no figures, and then a turn has
//! no timings and nothing cached.
//!
//! Behavior reference: project-maya serve/server.py:4256-4271, 4773-4793 at 7e68a30f.

use crate::engine::{EngineFailure, Terminal};

/// One engine call's figures, as the donor's `last` dictionary holds them after a `DONE`
/// line: every field is optional, because a 5-field `DONE` has no drafts, reuse or hits,
/// and a merged record keeps a field only when every call reported it.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct SegmentFigures {
    /// Tokens the engine generated (`DONE` field 1).
    pub generated: Option<u32>,
    /// The call's prompt length as the engine counts it (`DONE` field 2).
    pub prompt_tokens: Option<u32>,
    /// Prompt reading, in milliseconds.
    pub prompt_ms: Option<f64>,
    /// Decoding, in milliseconds.
    pub decode_ms: Option<f64>,
    /// Drafts accepted (`DONE` field 6).
    pub drafts_accepted: Option<u32>,
    /// Drafts offered (`DONE` field 7).
    pub drafts_offered: Option<u32>,
    /// Prompt tokens the conversation cache already held (`DONE` field 8).
    pub reused: Option<u32>,
    /// Expert-cache hits (`DONE` field 9).
    pub hits: Option<u32>,
    /// Expert-cache lookups (`DONE` field 10).
    pub lookups: Option<u32>,
}

impl SegmentFigures {
    /// The figures of one engine call's terminal record, or `None` when the engine reported
    /// none (no `DONE` counts and no clock): the donor's `last` is then not replaced.
    pub fn from_terminal(t: &Terminal) -> Option<Self> {
        if t.counts.is_none() && t.timings.is_none() {
            return None;
        }
        let mut s = SegmentFigures::default();
        if let Some(c) = &t.counts {
            s.generated = Some(c.generated);
            s.prompt_tokens = Some(c.prompt_tokens);
            s.reused = c.reused_tokens;
            if let Some((accepted, offered)) = c.drafts {
                s.drafts_accepted = Some(accepted);
                s.drafts_offered = Some(offered);
            }
            if let Some((hits, lookups)) = c.hits_lookups {
                s.hits = Some(hits);
                s.lookups = Some(lookups);
            }
        }
        if let Some(tm) = &t.timings {
            s.prompt_ms = Some(tm.prompt_ms);
            s.decode_ms = Some(tm.decode_ms);
        }
        Some(s)
    }
}

/// The figures of several engine calls within one request (fair slices and
/// continuations): the last call's, with `prompt_tokens` and `reused` from the first call,
/// and `generated`, `prompt_ms`, `decode_ms`, the draft counts, `hits` and `lookups`
/// summed when every call reported them (a field some call lacks keeps the last call's
/// value, as the donor's `dict(last, ...)` does). One call's figures are returned as they
/// are; no call's figures give `None`. A count sum beyond `u32` is a protocol failure
/// (contract section 9, rule 5).
///
/// Behavior reference: project-maya serve/server.py:4256-4264 at 7e68a30f.
pub fn merge_segments(
    segments: &[SegmentFigures],
) -> Result<Option<SegmentFigures>, EngineFailure> {
    let (Some(first), Some(last)) = (segments.first(), segments.last()) else {
        return Ok(None);
    };
    if segments.len() == 1 {
        return Ok(Some(*last));
    }
    let mut merged = *last;
    merged.prompt_tokens = first.prompt_tokens;
    merged.reused = first.reused;
    let sum = |get: fn(&SegmentFigures) -> Option<u32>| -> Result<Option<u32>, EngineFailure> {
        let mut total: u32 = 0;
        for s in segments {
            match get(s) {
                Some(v) => {
                    total = total
                        .checked_add(v)
                        .ok_or_else(|| EngineFailure::protocol("the request's figures overflow"))?;
                }
                None => return Ok(None),
            }
        }
        Ok(Some(total))
    };
    let fsum = |get: fn(&SegmentFigures) -> Option<f64>| -> Option<f64> {
        segments.iter().map(get).sum::<Option<f64>>()
    };
    if let Some(v) = sum(|s| s.generated)? {
        merged.generated = Some(v);
    }
    if let Some(v) = fsum(|s| s.prompt_ms) {
        merged.prompt_ms = Some(v);
    }
    if let Some(v) = fsum(|s| s.decode_ms) {
        merged.decode_ms = Some(v);
    }
    if let Some(v) = sum(|s| s.drafts_accepted)? {
        merged.drafts_accepted = Some(v);
    }
    if let Some(v) = sum(|s| s.drafts_offered)? {
        merged.drafts_offered = Some(v);
    }
    if let Some(v) = sum(|s| s.hits)? {
        merged.hits = Some(v);
    }
    if let Some(v) = sum(|s| s.lookups)? {
        merged.lookups = Some(v);
    }
    Ok(Some(merged))
}

/// A request's own prompt figures when its last engine call went on from what it had
/// written (after a fair slice or the loop guard): that call's prompt was the request's
/// prompt plus the kept tokens, all in the conversation cache, so its `prompt_tokens` and
/// `reused` count those too. The request's own: its prompt, and what the cache held of it
/// (the call's `reused` less the kept tokens, between 0 and the prompt length).
///
/// Behavior reference: project-maya serve/server.py:4774-4782 at 7e68a30f.
pub fn own_prompt_figures(last: &SegmentFigures, n_prompt: u32) -> SegmentFigures {
    let extra = i64::from(last.prompt_tokens.unwrap_or(0)) - i64::from(n_prompt);
    let reused = i64::from(last.reused.unwrap_or(0)) - extra.max(0);
    let reused = reused.min(i64::from(n_prompt)).max(0);
    SegmentFigures {
        prompt_tokens: Some(n_prompt),
        reused: Some(u32::try_from(reused).unwrap_or(0)),
        ..*last
    }
}

/// The figures a request reports: [`merge_segments`], then [`own_prompt_figures`] when
/// the merged `prompt_tokens` is larger than the request's prompt (the first call's `DONE`
/// was not seen).
///
/// Behavior reference: project-maya serve/server.py:4256-4267 at 7e68a30f.
pub fn request_figures(
    segments: &[SegmentFigures],
    n_prompt: u32,
) -> Result<Option<SegmentFigures>, EngineFailure> {
    Ok(merge_segments(segments)?.map(|m| {
        if m.prompt_tokens.unwrap_or(0) > n_prompt {
            own_prompt_figures(&m, n_prompt)
        } else {
            m
        }
    }))
}

/// One request's `timings` in llama.cpp's names, from the engine's own clock. Fields are
/// listed in the donor's key order; `None` fields are written as JSON `null`, and the two
/// draft fields are present only when the engine reported drafts.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RequestTimings {
    /// What the conversation cache already held.
    pub cache_n: u32,
    /// What was read: the prompt less `cache_n`, at least 0.
    pub prompt_n: u32,
    /// Prompt reading, rounded to 0.1 ms.
    pub prompt_ms: f64,
    /// Milliseconds a read token, rounded to 0.001; `None` when nothing was read.
    pub prompt_per_token_ms: Option<f64>,
    /// Read tokens a second, rounded to 0.1; `None` when nothing was read or no time passed.
    pub prompt_per_second: Option<f64>,
    /// The tokens the request took (the completion tokens).
    pub predicted_n: u32,
    /// Decoding, rounded to 0.1 ms.
    pub predicted_ms: f64,
    /// Milliseconds a generated token, rounded to 0.001, by the engine's count.
    pub predicted_per_token_ms: Option<f64>,
    /// Generated tokens a second, rounded to 0.1, by the engine's count.
    pub predicted_per_second: Option<f64>,
    /// Drafts offered and accepted: `(draft_n, draft_n_accepted)`, only when reported.
    pub drafts: Option<(u32, u32)>,
}

/// Python's `round(x, ndigits)` on a float: the decimal value nearest to `x` with
/// `ndigits` decimals, ties to even on the exact binary value, read back as a float.
/// Rust's fixed-precision formatting rounds the same way.
pub(crate) fn py_round(x: f64, ndigits: usize) -> f64 {
    if !x.is_finite() {
        return x;
    }
    format!("{x:.ndigits$}").parse::<f64>().unwrap_or(x)
}

/// `request_timings(prompt_tokens, generated, last)` of the donor: `None` when the engine
/// keeps no clock (no `prompt_ms`), else the figures below, with the engine's own
/// `generated` count giving the decode rate (the request's count when the engine reported
/// none or 0).
///
/// Behavior reference: project-maya serve/server.py:4785-4800 at 7e68a30f.
pub fn request_timings(
    prompt_tokens: u32,
    generated: u32,
    last: &SegmentFigures,
) -> Option<RequestTimings> {
    let prompt_ms = last.prompt_ms?;
    let cache_n = last.reused.unwrap_or(0);
    let prompt_n = prompt_tokens.saturating_sub(cache_n);
    let decode_ms = last.decode_ms.unwrap_or(0.0);
    let decoded = match last.generated {
        Some(g) if g != 0 => g,
        _ => generated,
    };
    let pn = f64::from(prompt_n);
    let dn = f64::from(decoded);
    Some(RequestTimings {
        cache_n,
        prompt_n,
        prompt_ms: py_round(prompt_ms, 1),
        prompt_per_token_ms: (prompt_n != 0).then(|| py_round(prompt_ms / pn, 3)),
        prompt_per_second: (prompt_n != 0 && prompt_ms > 0.0)
            .then(|| py_round(pn / (prompt_ms / 1000.0), 1)),
        predicted_n: generated,
        predicted_ms: py_round(decode_ms, 1),
        predicted_per_token_ms: (decoded != 0).then(|| py_round(decode_ms / dn, 3)),
        predicted_per_second: (decoded != 0 && decode_ms > 0.0)
            .then(|| py_round(dn / (decode_ms / 1000.0), 1)),
        drafts: last
            .drafts_offered
            .map(|offered| (offered, last.drafts_accepted.unwrap_or(0))),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::{EngineCounts, EngineStop, EngineTimings};

    fn seg(
        generated: u32,
        prompt_tokens: u32,
        reused: Option<u32>,
        ms: (f64, f64),
    ) -> SegmentFigures {
        SegmentFigures {
            generated: Some(generated),
            prompt_tokens: Some(prompt_tokens),
            prompt_ms: Some(ms.0),
            decode_ms: Some(ms.1),
            reused,
            ..SegmentFigures::default()
        }
    }

    #[test]
    fn python_rounding_is_half_even_on_the_exact_value() {
        assert_eq!(py_round(2.675, 2), 2.67); // 2.675 is 2.67499999... in binary
        assert_eq!(py_round(0.125, 2), 0.12);
        assert_eq!(py_round(0.375, 2), 0.38);
        assert_eq!(py_round(40.0, 1), 40.0);
        assert_eq!(py_round(1.0 / 3.0, 3), 0.333);
        assert!(py_round(f64::NAN, 1).is_nan());
        assert_eq!(py_round(f64::INFINITY, 1), f64::INFINITY);
    }

    #[test]
    fn a_terminal_without_figures_gives_none() {
        let bare = Terminal::bare(EngineStop::Stop { token: None });
        assert_eq!(SegmentFigures::from_terminal(&bare), None);
        let t = Terminal {
            stop: EngineStop::Length,
            counts: Some(EngineCounts {
                generated: 3,
                prompt_tokens: 7,
                reused_tokens: Some(2),
                drafts: Some((4, 5)),
                hits_lookups: Some((9, 10)),
            }),
            timings: Some(EngineTimings {
                prompt_ms: 1.5,
                decode_ms: 2.5,
            }),
        };
        let s = SegmentFigures::from_terminal(&t).unwrap();
        assert_eq!(
            (
                s.generated,
                s.prompt_tokens,
                s.reused,
                s.drafts_accepted,
                s.drafts_offered
            ),
            (Some(3), Some(7), Some(2), Some(4), Some(5))
        );
        assert_eq!(
            (s.hits, s.lookups, s.prompt_ms, s.decode_ms),
            (Some(9), Some(10), Some(1.5), Some(2.5))
        );
    }

    #[test]
    fn segments_merge_as_the_donor_merges_them() {
        let a = seg(10, 100, Some(40), (50.0, 100.0));
        let mut b = seg(5, 110, Some(108), (2.0, 60.0));
        b.hits = Some(3);
        b.lookups = Some(4);
        let m = merge_segments(&[a, b]).unwrap().unwrap();
        assert_eq!(m.prompt_tokens, Some(100));
        assert_eq!(m.reused, Some(40));
        assert_eq!(m.generated, Some(15));
        assert_eq!(m.prompt_ms, Some(52.0));
        assert_eq!(m.decode_ms, Some(160.0));
        // Not every segment has hits: the last one's stay.
        assert_eq!((m.hits, m.lookups), (Some(3), Some(4)));
        assert_eq!(merge_segments(&[]).unwrap(), None);
        assert_eq!(merge_segments(&[a]).unwrap(), Some(a));
        let big = seg(u32::MAX, 1, None, (0.0, 0.0));
        let err = merge_segments(&[big, big]).unwrap_err();
        assert_eq!(err.kind, crate::engine::FailureKind::Protocol);
    }

    #[test]
    fn own_prompt_figures_take_the_kept_tokens_out() {
        // A guarded answer reported 5,919 cached tokens of a 246-token prompt: its last
        // call read the prompt and 5,673 kept tokens, all cached.
        let last = seg(10, 5919, Some(5919), (1.0, 1.0));
        let own = own_prompt_figures(&last, 246);
        assert_eq!(own.prompt_tokens, Some(246));
        assert_eq!(own.reused, Some(246));
        let last = seg(10, 300, Some(10), (1.0, 1.0));
        assert_eq!(own_prompt_figures(&last, 246).reused, Some(0));
        let merged = request_figures(&[last], 246).unwrap().unwrap();
        assert_eq!(merged.prompt_tokens, Some(246));
        let fits = seg(10, 246, Some(10), (1.0, 1.0));
        assert_eq!(request_figures(&[fits], 246).unwrap(), Some(fits));
    }

    #[test]
    fn timings_follow_the_formula() {
        // ClockedEngine: 40 ms prompt, 20 ms a token, 5 reused.
        let last = seg(4, 20, Some(5), (40.0, 80.0));
        let t = request_timings(20, 4, &last).unwrap();
        assert_eq!((t.cache_n, t.prompt_n), (5, 15));
        assert_eq!(t.prompt_ms, 40.0);
        assert_eq!(t.prompt_per_token_ms, Some(2.667));
        assert_eq!(t.prompt_per_second, Some(375.0));
        assert_eq!(t.predicted_n, 4);
        assert_eq!(t.predicted_ms, 80.0);
        assert_eq!(t.predicted_per_token_ms, Some(20.0));
        assert_eq!(t.predicted_per_second, Some(50.0));
        assert_eq!(t.drafts, None);
        // Everything read from the cache: no per-token figures.
        let all = seg(4, 5, Some(5), (0.0, 0.0));
        let t = request_timings(5, 4, &all).unwrap();
        assert_eq!(
            (t.prompt_n, t.prompt_per_token_ms, t.prompt_per_second),
            (0, None, None)
        );
        assert_eq!(t.predicted_per_second, None);
        assert_eq!(t.predicted_per_token_ms, Some(0.0));
        // The engine's count 0 falls back to the request's.
        let mut zero = seg(0, 5, None, (1.0, 10.0));
        zero.generated = Some(0);
        assert_eq!(
            request_timings(5, 2, &zero).unwrap().predicted_per_token_ms,
            Some(5.0)
        );
        // No clock: none.
        assert_eq!(request_timings(5, 2, &SegmentFigures::default()), None);
    }
}
