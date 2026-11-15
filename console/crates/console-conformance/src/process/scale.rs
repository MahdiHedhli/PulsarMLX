//! Scaled deadlines.
//!
//! Every bound the harness waits for is a deadline, never a fixed wait, multiplied by the
//! test time scale: 1 by default, larger on a slow runner (3 in the drift canary).

use std::time::Duration;

use super::ProcessError;

/// The environment variable that scales every deadline (contracts/naming.md section
/// 3.10; the detail files call it `CONSOLE_TEST_TIME_SCALE`).
pub const TIME_SCALE_ENV: &str = "PULSAR_CONSOLE_TEST_TIME_SCALE";

/// The largest accepted scale.
pub const MAX_TIME_SCALE: f64 = 1000.0;

/// How long the harness waits for the ready line, before scaling (tasks/conformance.md,
/// "Starting and stopping the Rust binary").
pub const DEFAULT_READY_DEADLINE: Duration = Duration::from_secs(20);

/// How long the processes of the group get to end after `SIGTERM`, before scaling.
pub const DEFAULT_GRACE: Duration = Duration::from_secs(10);

/// How long the harness waits for the processes to vanish after `SIGKILL`, before
/// scaling.
pub const DEFAULT_KILL_DEADLINE: Duration = Duration::from_secs(10);

/// A factor applied to every deadline.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct TimeScale(f64);

impl Default for TimeScale {
    fn default() -> Self {
        TimeScale(1.0)
    }
}

impl TimeScale {
    /// A scale of `factor`, which must be finite, above 0 and at most
    /// [`MAX_TIME_SCALE`].
    pub fn new(factor: f64) -> Result<Self, ProcessError> {
        if factor.is_finite() && factor > 0.0 && factor <= MAX_TIME_SCALE {
            Ok(TimeScale(factor))
        } else {
            Err(ProcessError::BadTimeScale {
                value: factor.to_string(),
            })
        }
    }

    /// The scale a variable's value gives: 1 when it is unset or empty, otherwise the
    /// number it holds. A value that is not an accepted number is an error, so that a
    /// mistyped scale is never silently ignored.
    pub fn from_env_value(value: Option<&str>) -> Result<Self, ProcessError> {
        let text = match value.map(str::trim) {
            None | Some("") => return Ok(TimeScale::default()),
            Some(text) => text,
        };
        let bad = || ProcessError::BadTimeScale {
            value: text.to_string(),
        };
        let factor: f64 = text.parse().map_err(|_| bad())?;
        TimeScale::new(factor).map_err(|_| bad())
    }

    /// The scale from [`TIME_SCALE_ENV`] in this process's environment.
    pub fn from_env() -> Result<Self, ProcessError> {
        match std::env::var(TIME_SCALE_ENV) {
            Ok(v) => TimeScale::from_env_value(Some(&v)),
            Err(std::env::VarError::NotPresent) => Ok(TimeScale::default()),
            Err(std::env::VarError::NotUnicode(raw)) => Err(ProcessError::BadTimeScale {
                value: raw.to_string_lossy().into_owned(),
            }),
        }
    }

    /// The factor.
    pub fn factor(self) -> f64 {
        self.0
    }

    /// `base` multiplied by the factor; a product too large for a [`Duration`] saturates.
    pub fn apply(self, base: Duration) -> Duration {
        Duration::try_from_secs_f64(base.as_secs_f64() * self.0).unwrap_or(Duration::MAX)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unset_or_empty_is_one() {
        assert_eq!(TimeScale::from_env_value(None).unwrap().factor(), 1.0);
        assert_eq!(TimeScale::from_env_value(Some("")).unwrap().factor(), 1.0);
        assert_eq!(TimeScale::from_env_value(Some("  ")).unwrap().factor(), 1.0);
    }

    #[test]
    fn a_number_scales_every_deadline() {
        let s = TimeScale::from_env_value(Some("3")).unwrap();
        assert_eq!(s.apply(DEFAULT_READY_DEADLINE), Duration::from_secs(60));
        let half = TimeScale::from_env_value(Some("0.5")).unwrap();
        assert_eq!(half.apply(Duration::from_secs(20)), Duration::from_secs(10));
    }

    #[test]
    fn a_bad_value_is_refused_not_ignored() {
        for v in ["0", "-1", "abc", "NaN", "inf", "1001", "3s"] {
            let err = TimeScale::from_env_value(Some(v)).unwrap_err();
            assert!(err.to_string().contains(TIME_SCALE_ENV), "{v}: {err}");
        }
        assert!(TimeScale::new(MAX_TIME_SCALE).is_ok());
    }

    #[test]
    fn a_huge_product_saturates() {
        let s = TimeScale::new(MAX_TIME_SCALE).unwrap();
        assert_eq!(s.apply(Duration::MAX), Duration::MAX);
    }
}
