//! The terminal record and the engine's own figures (contract section 9).

use super::pyparse::{py_float, py_int};
use super::text::BoundedText;

/// How a generation ended, as the engine saw it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EngineStop {
    /// The engine itself reached an end token.
    Stop {
        /// The end token, when the engine names it.
        token: Option<u32>,
    },
    /// `max_new` reached.
    Length,
    /// After a cancel request or `ConsumerGone`.
    Cancelled,
    /// After a pause request (contract section 14, Q5).
    Paused,
}

/// The engine's own counts. The 5, 8 and 10 field forms of the donor's `DONE` line stay
/// distinguishable through the `Option` fields.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct EngineCounts {
    /// As the engine counts them (`DONE` field 1); informational (Q4).
    pub generated: u32,
    /// `DONE` field 2; informational (Q4).
    pub prompt_tokens: u32,
    /// `DONE` field 8; the only source of the cached-token figure (contract section 9).
    pub reused_tokens: Option<u32>,
    /// Accepted and offered drafts (`DONE` fields 6 and 7).
    pub drafts: Option<(u32, u32)>,
    /// Hits and lookups (`DONE` fields 9 and 10).
    pub hits_lookups: Option<(u32, u32)>,
}

/// The engine's clock.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct EngineTimings {
    /// Prompt reading, in milliseconds.
    pub prompt_ms: f64,
    /// Decoding, in milliseconds.
    pub decode_ms: f64,
}

/// The one terminal record of a generation: the return value of `generate`, so a second
/// terminal is structurally impossible.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Terminal {
    /// How it ended.
    pub stop: EngineStop,
    /// `None` for an engine without a `DONE` (the scripted engine).
    pub counts: Option<EngineCounts>,
    /// `None` for an engine without a clock.
    pub timings: Option<EngineTimings>,
}

impl Terminal {
    /// A terminal with no figures.
    pub fn bare(stop: EngineStop) -> Self {
        Self {
            stop,
            counts: None,
            timings: None,
        }
    }
}

/// The longest `finish` word a [`DoneFigures`] keeps, in bytes.
pub const DONE_FINISH_MAX_BYTES: usize = 32;

/// The figures of one `DONE` line, per call (never left in shared state on the engine,
/// the donor's `last` attribute).
#[derive(Debug, Clone, PartialEq)]
pub struct DoneFigures {
    /// The counts.
    pub counts: EngineCounts,
    /// The clock.
    pub timings: EngineTimings,
    /// The finish word as written (`stop`, `length` or `cancel` from the donor's engines).
    pub finish: BoundedText,
}

impl DoneFigures {
    /// Reads the figures of a `DONE` line after its tag (and, in multi mode, after its
    /// request id): `generated prompt_tokens prompt_ms decode_ms finish`, then, with at
    /// least 8 figures, `drafts_accepted drafts_offered reused`, then, with at least 10,
    /// `hits lookups`. Extra fields are ignored, as in the donor. An error names the first
    /// field that does not read; a count must fit `u32`. A negative count, or one above
    /// `u32`, which the donor's `int()` would accept, is refused here; this difference is
    /// part of proposal P-21 in the deviation register, awaiting the owner's decision.
    ///
    /// Behavior reference: project-maya serve/server.py:1192-1199 at 7e68a30f.
    pub fn parse(fields: &[&str]) -> Result<Self, String> {
        let count = |i: usize| -> Result<u32, String> {
            let f = fields
                .get(i)
                .ok_or_else(|| format!("DONE has no field {}", i + 1))?;
            py_int(f)
                .and_then(|n| u32::try_from(n).ok())
                .ok_or_else(|| format!("DONE field {} does not read as a count", i + 1))
        };
        let ms = |i: usize| -> Result<f64, String> {
            let f = fields
                .get(i)
                .ok_or_else(|| format!("DONE has no field {}", i + 1))?;
            py_float(f).ok_or_else(|| format!("DONE field {} does not read as a number", i + 1))
        };
        let generated = count(0)?;
        let prompt_tokens = count(1)?;
        let prompt_ms = ms(2)?;
        let decode_ms = ms(3)?;
        let finish = fields
            .get(4)
            .ok_or_else(|| "DONE has no field 5".to_owned())?;
        let mut counts = EngineCounts {
            generated,
            prompt_tokens,
            ..EngineCounts::default()
        };
        if fields.len() >= 8 {
            counts.drafts = Some((count(5)?, count(6)?));
            counts.reused_tokens = Some(count(7)?);
        }
        if fields.len() >= 10 {
            counts.hits_lookups = Some((count(8)?, count(9)?));
        }
        Ok(Self {
            counts,
            timings: EngineTimings {
                prompt_ms,
                decode_ms,
            },
            finish: BoundedText::new(finish, DONE_FINISH_MAX_BYTES),
        })
    }

    /// The stop this `DONE` reports: `stop`, `length`, and `cancel` (as [`EngineStop::Paused`]
    /// when the adapter asked for a pause, else [`EngineStop::Cancelled`]); `None` for any
    /// other word.
    pub fn engine_stop(&self, pause_requested: bool) -> Option<EngineStop> {
        match self.finish.as_str() {
            "stop" => Some(EngineStop::Stop { token: None }),
            "length" => Some(EngineStop::Length),
            "cancel" if pause_requested => Some(EngineStop::Paused),
            "cancel" => Some(EngineStop::Cancelled),
            _ => None,
        }
    }

    /// The terminal record for `stop` with these figures.
    pub fn terminal(&self, stop: EngineStop) -> Terminal {
        Terminal {
            stop,
            counts: Some(self.counts),
            timings: Some(self.timings),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn split(line: &str) -> Vec<&str> {
        line.split_whitespace().collect()
    }

    #[test]
    fn done_five_fields() {
        let d = DoneFigures::parse(&split("3 1 1.0 2.5 stop")).unwrap();
        assert_eq!(d.counts.generated, 3);
        assert_eq!(d.counts.prompt_tokens, 1);
        assert_eq!(d.counts.drafts, None);
        assert_eq!(d.counts.reused_tokens, None);
        assert_eq!(d.counts.hits_lookups, None);
        assert_eq!(d.timings.prompt_ms, 1.0);
        assert_eq!(d.timings.decode_ms, 2.5);
        assert_eq!(d.engine_stop(false), Some(EngineStop::Stop { token: None }));
    }

    #[test]
    fn done_eight_fields() {
        let d = DoneFigures::parse(&split("1 12000 4000 10 stop 0 0 8000")).unwrap();
        assert_eq!(d.counts.drafts, Some((0, 0)));
        assert_eq!(d.counts.reused_tokens, Some(8000));
        assert_eq!(d.counts.hits_lookups, None);
        // Seven figures: the extra one is ignored, as `len(f) >= 9` is false.
        let d = DoneFigures::parse(&split("1 2 3 4 length 5 6")).unwrap();
        assert_eq!(d.counts.drafts, None);
        assert_eq!(d.engine_stop(false), Some(EngineStop::Length));
    }

    #[test]
    fn done_ten_fields() {
        let d = DoneFigures::parse(&split("2 3 1.0 1.0 cancel 4 5 6 7 8")).unwrap();
        assert_eq!(d.counts.drafts, Some((4, 5)));
        assert_eq!(d.counts.reused_tokens, Some(6));
        assert_eq!(d.counts.hits_lookups, Some((7, 8)));
        assert_eq!(d.engine_stop(false), Some(EngineStop::Cancelled));
        assert_eq!(d.engine_stop(true), Some(EngineStop::Paused));
        let t = d.terminal(EngineStop::Cancelled);
        assert_eq!(t.counts, Some(d.counts));
        assert_eq!(t.timings, Some(d.timings));
    }

    #[test]
    fn done_errors_name_the_field() {
        assert_eq!(
            DoneFigures::parse(&split("1 2 3")).unwrap_err(),
            "DONE has no field 4"
        );
        assert_eq!(
            DoneFigures::parse(&split("x 2 3 4 stop")).unwrap_err(),
            "DONE field 1 does not read as a count"
        );
        assert_eq!(
            DoneFigures::parse(&split("-1 2 3 4 stop")).unwrap_err(),
            "DONE field 1 does not read as a count"
        );
        assert_eq!(
            DoneFigures::parse(&split("1 2 3 y stop")).unwrap_err(),
            "DONE field 4 does not read as a number"
        );
        let d = DoneFigures::parse(&split("1 2 3 4 weird")).unwrap();
        assert_eq!(d.engine_stop(false), None);
        assert_eq!(Terminal::bare(EngineStop::Length).counts, None);
    }
}
