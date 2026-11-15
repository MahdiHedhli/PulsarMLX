//! A test engine whose descriptor reports a provenance that is not synthetic, for the
//! refusal tests of the synthetic-only rule (owner decision of 2026-11-14 on OPEN-29,
//! lead decision LD28; ENG-10 and API-08 pin the refusal with it). It has no donor
//! counterpart.

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Instant;

use console_core::engine::{
    require_synthetic, ControlProbe, EngineDescriptor, EngineFactory, EngineFailure,
    EngineInstance, EngineKind, EngineStartConfig, EventSink, GenerationRequest, Health,
    Provenance, ShutdownOutcome, Terminal,
};

use crate::fake::mock::mock_descriptor;
use crate::fake::{FakeConfigError, FakeFactory, FakeScript, DEFAULT_MAX_CONTEXT};

#[derive(Debug, Default)]
struct Counters {
    starts: AtomicU64,
    synthetic_starts: AtomicU64,
    generate_calls: AtomicU64,
    shutdowns: AtomicU64,
}

/// A scripted-engine shape whose descriptor reports `Provenance::NotSynthetic`: with the
/// declaration given to [`declaring`](Self::declaring), or with none
/// ([`undeclared`](Self::undeclared)). It exists only with the `test-support` feature, so
/// that the refusal of `require_synthetic` can be tested on every admission path; no
/// configuration key, command-line flag or environment variable can select it.
///
/// It never serves: should a path ever call `generate` without the guard, the call fails
/// with the guard's own refusal and delivers nothing, and the call is counted, so a test
/// can assert that it was never reached. It is not an engine to make work: it is the
/// thing the server must refuse.
///
/// For the admission paths that reuse a factory (restart, model switch, context reload),
/// [`after_synthetic_starts`](Self::after_synthetic_starts) builds one whose first starts
/// are the synthetic scripted engine, which serves, and whose later starts report the
/// provenance that is not synthetic.
#[derive(Debug, Clone)]
pub struct NotSyntheticEngine {
    declared: Option<Arc<str>>,
    counters: Arc<Counters>,
    synthetic: Option<(FakeFactory, u64)>,
}

impl NotSyntheticEngine {
    /// An engine that declares the provenance `declared` (anything: the guard accepts
    /// only the synthetic provenance the in-process engines construct themselves).
    pub fn declaring(declared: &str) -> Self {
        Self {
            declared: Some(Arc::from(declared)),
            counters: Arc::new(Counters::default()),
            synthetic: None,
        }
    }

    /// An engine that declares no provenance (fail closed: not synthetic).
    pub fn undeclared() -> Self {
        Self {
            declared: None,
            counters: Arc::new(Counters::default()),
            synthetic: None,
        }
    }

    /// An engine whose first `n` starts are instances of the scripted engine of `script`
    /// (synthetic: they pass the guard and serve), and whose every later start is
    /// refused as [`declaring`](Self::declaring) `declared` makes it: for the refusal tests
    /// of a restart, a model switch or a context reload, where a factory that first served
    /// starts again. Every start is counted by [`starts`](Self::starts); the synthetic ones
    /// also by [`synthetic_starts`](Self::synthetic_starts).
    pub fn after_synthetic_starts(
        script: FakeScript,
        n: u32,
        declared: &str,
    ) -> Result<Self, FakeConfigError> {
        Ok(Self {
            declared: Some(Arc::from(declared)),
            counters: Arc::new(Counters::default()),
            synthetic: Some((script.build()?, u64::from(n))),
        })
    }

    /// The provenance its instances report.
    pub fn provenance(&self) -> Provenance {
        Provenance::not_synthetic(self.declared.as_deref())
    }

    /// Instances started, synthetic ones included.
    pub fn starts(&self) -> u64 {
        self.counters.starts.load(Ordering::SeqCst)
    }

    /// Starts that gave the synthetic scripted engine (see
    /// [`after_synthetic_starts`](Self::after_synthetic_starts)).
    pub fn synthetic_starts(&self) -> u64 {
        self.counters.synthetic_starts.load(Ordering::SeqCst)
    }

    /// Calls of `generate` on any instance: 0 unless a path served it without the guard.
    pub fn generate_calls(&self) -> u64 {
        self.counters.generate_calls.load(Ordering::SeqCst)
    }

    /// Instances shut down (a refused engine is closed).
    pub fn shutdowns(&self) -> u64 {
        self.counters.shutdowns.load(Ordering::SeqCst)
    }
}

struct NotSyntheticInstance {
    desc: EngineDescriptor,
    counters: Arc<Counters>,
}

impl EngineFactory for NotSyntheticEngine {
    fn kind(&self) -> EngineKind {
        EngineKind::Scripted
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        let before = self.counters.starts.fetch_add(1, Ordering::SeqCst);
        if let Some((scripted, n)) = &self.synthetic {
            if before < *n {
                self.counters
                    .synthetic_starts
                    .fetch_add(1, Ordering::SeqCst);
                return scripted.start(cfg);
            }
        }
        let mut desc = mock_descriptor(cfg.context.unwrap_or(DEFAULT_MAX_CONTEXT));
        desc.provenance = self.provenance();
        Ok(Box::new(NotSyntheticInstance {
            desc,
            counters: Arc::clone(&self.counters),
        }))
    }
}

impl EngineInstance for NotSyntheticInstance {
    fn descriptor(&self) -> &EngineDescriptor {
        &self.desc
    }

    fn generate(
        &mut self,
        _req: &GenerationRequest,
        _control: &ControlProbe,
        _sink: &mut dyn EventSink,
    ) -> Result<Terminal, EngineFailure> {
        self.counters.generate_calls.fetch_add(1, Ordering::SeqCst);
        Err(match require_synthetic(&self.desc) {
            Err(refused) => refused.to_failure(),
            // Unreachable by construction (the provenance is never synthetic); still a
            // refusal, never an answer.
            Ok(()) => EngineFailure::unsupported("serving from this test engine"),
        })
    }

    fn health(&mut self) -> Health {
        Health::Alive
    }

    fn shutdown(self: Box<Self>, _deadline: Instant) -> ShutdownOutcome {
        self.counters.shutdowns.fetch_add(1, Ordering::SeqCst);
        ShutdownOutcome::Graceful
    }
}

#[cfg(test)]
mod tests {
    use console_core::engine::{FailureKind, ALLOWING_NON_SYNTHETIC_ENGINES_PATH};

    use super::*;
    use crate::fake::testutil::{req, run};

    #[test]
    fn fake_not_synthetic_engine_is_refused_by_the_guard() {
        for f in [
            NotSyntheticEngine::declaring("real-weights"),
            NotSyntheticEngine::undeclared(),
        ] {
            let e = f.start(&EngineStartConfig::new()).expect("starts");
            let refused = require_synthetic(e.descriptor()).expect_err("refused");
            assert_eq!(refused.kind, EngineKind::Scripted);
            assert_eq!(refused.reported, f.provenance());
            let line = refused.to_string();
            assert!(line.contains(ALLOWING_NON_SYNTHETIC_ENGINES_PATH), "{line}");
            assert!(line.contains("not synthetic"), "{line}");
            assert_eq!(e.shutdown(Instant::now()), ShutdownOutcome::Graceful);
            assert_eq!((f.starts(), f.shutdowns(), f.generate_calls()), (1, 1, 0));
        }
    }

    #[test]
    fn fake_not_synthetic_after_synthetic_starts_serves_then_is_refused() {
        let f = NotSyntheticEngine::after_synthetic_starts(
            crate::fake::FakeScript::new(vec![5, 6]),
            1,
            "real-weights",
        )
        .expect("valid");
        // First start: the synthetic scripted engine, admitted, and it serves.
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        assert_eq!(e.descriptor().provenance, Provenance::Synthetic);
        assert!(require_synthetic(e.descriptor()).is_ok());
        let (sink, out) = run(e.as_mut(), &req(vec![1], 4));
        assert!(out.is_ok());
        assert_eq!(sink.tokens(), vec![5, 6]);
        e.shutdown(Instant::now());
        // A restart, and a context reload: the same factory now reports a provenance that
        // is not synthetic, and the guard refuses it before it serves.
        for cfg in [
            EngineStartConfig::new(),
            EngineStartConfig::new().with_context(8192),
        ] {
            let e = f.start(&cfg).expect("starts");
            let refused = require_synthetic(e.descriptor()).expect_err("refused");
            assert_eq!(refused.reported, f.provenance());
            assert_eq!(
                e.descriptor().max_context,
                cfg.context.unwrap_or(DEFAULT_MAX_CONTEXT)
            );
            e.shutdown(Instant::now());
        }
        assert_eq!((f.starts(), f.synthetic_starts()), (3, 1));
        assert_eq!((f.generate_calls(), f.shutdowns()), (0, 2));
    }

    #[test]
    fn fake_not_synthetic_engine_never_serves_even_without_the_guard() {
        let f = NotSyntheticEngine::declaring("x");
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        let (sink, out) = run(e.as_mut(), &req(vec![1], 4));
        let err = out.unwrap_err();
        assert_eq!(err.kind, FailureKind::StartFailed);
        assert!(err.poisoned);
        assert!(err.to_string().contains("declared \"x\""));
        assert!(sink.events.is_empty());
        assert_eq!(f.generate_calls(), 1);
    }
}
