use crate::{FailureClass, RunnerError};
use std::collections::HashSet;
use std::ffi::OsString;
use std::path::PathBuf;

pub const USAGE: &str = "usage: f017-glm52-runner \
  --m1d-execution-config JSON --execution-config-sha256 SHA256\n\
or: f017-glm52-runner \
  --out FRESH_JSON \
  --validation-mode golden-strict \
  --stream-mode default-gpu|owned-device \
  --memory-floor-bytes BYTES \
  --environment-manifest JSON \
  [--repository-root DIR] \
  [--numerical-mode exact-qualification-scaffold|production-mlx-tier-b] \
  [--dry-run | --adapter-preflight-only | --checkpoint-identity-only | --fixture-checkpoint-identity-only | --fixture-mode MANIFEST | --fixture-projection-boundary PACKAGE | --real-projection-boundary PACKAGE] \
  [--checkpoint-manifest JSON --tokens IDS --n-new N --expected-token ID]";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ValidationMode {
    GoldenStrict,
    TeacherForcedValidation,
}

impl ValidationMode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::GoldenStrict => "golden_strict",
            Self::TeacherForcedValidation => "teacher_forced_validation",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StreamMode {
    DefaultGpu,
    OwnedDevice,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NumericalMode {
    ExactQualificationScaffold,
    ProductionMlxTierB,
}

impl NumericalMode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::ExactQualificationScaffold => "exact_qualification_scaffold",
            Self::ProductionMlxTierB => "production_mlx_tier_b",
        }
    }
}

impl StreamMode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::DefaultGpu => "default_gpu",
            Self::OwnedDevice => "owned_device",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RunnerMode {
    DryRun,
    AdapterPreflight,
    CheckpointIdentity,
    FixtureCheckpointIdentity,
    Fixture { manifest: PathBuf },
    FixtureProjection { package: PathBuf },
    RealProjection { package: PathBuf },
    P1,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EnvironmentPolicy {
    ProductionReviewed,
    CheckpointFreeFixture,
    AnyValidated,
}

pub fn mode_environment_policy(mode: &str) -> Option<EnvironmentPolicy> {
    match mode {
        "adapter_preflight" | "checkpoint_identity" | "real_projection" | "p1" => {
            Some(EnvironmentPolicy::ProductionReviewed)
        }
        "fixture_checkpoint_identity" | "fixture_projection" => {
            Some(EnvironmentPolicy::CheckpointFreeFixture)
        }
        "dry_run" | "fixture" => Some(EnvironmentPolicy::AnyValidated),
        _ => None,
    }
}

impl RunnerMode {
    pub const fn as_str(&self) -> &'static str {
        match self {
            Self::DryRun => "dry_run",
            Self::AdapterPreflight => "adapter_preflight",
            Self::CheckpointIdentity => "checkpoint_identity",
            Self::FixtureCheckpointIdentity => "fixture_checkpoint_identity",
            Self::Fixture { .. } => "fixture",
            Self::FixtureProjection { .. } => "fixture_projection",
            Self::RealProjection { .. } => "real_projection",
            Self::P1 => "p1",
        }
    }

    pub fn environment_policy(&self) -> EnvironmentPolicy {
        mode_environment_policy(self.as_str()).expect("all runner modes have an environment policy")
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Config {
    pub out: PathBuf,
    pub validation_mode: ValidationMode,
    pub stream_mode: StreamMode,
    pub memory_floor_bytes: u64,
    pub environment_manifest: PathBuf,
    pub repository_root: Option<PathBuf>,
    pub checkpoint_manifest: Option<PathBuf>,
    pub tokens: Vec<u32>,
    pub n_new: u32,
    pub expected_token: Option<u32>,
    pub numerical_mode: Option<NumericalMode>,
    pub mode: RunnerMode,
    pub execution_config: Option<ExecutionConfigBinding>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExecutionConfigBinding {
    pub path: PathBuf,
    pub sha256: String,
    pub attempt: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ParseOutcome {
    Run(Config),
    Help,
    Version,
}

pub fn parse_args<I>(args: I) -> Result<ParseOutcome, RunnerError>
where
    I: IntoIterator<Item = OsString>,
{
    let args = args.into_iter().collect::<Vec<_>>();
    if args.len() == 1 && args[0] == "--help" {
        return Ok(ParseOutcome::Help);
    }
    if args.len() == 1 && args[0] == "--version" {
        return Ok(ParseOutcome::Version);
    }
    if args.iter().any(|argument| {
        argument == "--m1d-execution-config" || argument == "--execution-config-sha256"
    }) {
        if args.len() != 4
            || args[0] != "--m1d-execution-config"
            || args[2] != "--execution-config-sha256"
        {
            return Err(cli_error(
                "m1d_config_only",
                "M1-D execution accepts exactly one config path and one config SHA-256 in canonical order",
            ));
        }
        let path = PathBuf::from(&args[1]);
        let expected = args[3]
            .to_str()
            .ok_or_else(|| cli_error("m1d_config_sha", "execution config SHA-256 must be UTF-8"))?;
        return crate::m1d_execution_config::load(&path, expected)
            .map(|loaded| ParseOutcome::Run(loaded.config));
    }

    let mut seen = HashSet::new();
    let mut out = None;
    let mut validation_mode = None;
    let mut stream_mode = None;
    let mut memory_floor_bytes = None;
    let mut environment_manifest = None;
    let mut repository_root = None;
    let mut checkpoint_manifest = None;
    let mut tokens = None;
    let mut n_new = None;
    let mut expected_token = None;
    let mut numerical_mode = None;
    let mut selected_mode = None;
    let mut index = 0;

    while index < args.len() {
        let flag = args[index]
            .to_str()
            .ok_or_else(|| cli_error("non_utf8_option", "option names must be UTF-8"))?;
        if !flag.starts_with("--") {
            return Err(cli_error(
                "unexpected_positional",
                format!("unexpected positional argument {flag:?}"),
            ));
        }
        if !seen.insert(flag.to_owned()) {
            return Err(cli_error(
                "duplicate_option",
                format!("duplicate option {flag}"),
            ));
        }
        match flag {
            "--out" => out = Some(path_value(&args, &mut index, flag)?),
            "--validation-mode" => {
                validation_mode = Some(match text_value(&args, &mut index, flag)?.as_str() {
                    "golden-strict" => ValidationMode::GoldenStrict,
                    "teacher-forced-validation" => ValidationMode::TeacherForcedValidation,
                    value => {
                        return Err(cli_error(
                            "invalid_validation_mode",
                            format!("unsupported validation mode {value:?}"),
                        ))
                    }
                });
            }
            "--stream-mode" => {
                stream_mode = Some(match text_value(&args, &mut index, flag)?.as_str() {
                    "default-gpu" => StreamMode::DefaultGpu,
                    "owned-device" => StreamMode::OwnedDevice,
                    value => {
                        return Err(cli_error(
                            "invalid_stream_mode",
                            format!("unsupported stream mode {value:?}"),
                        ))
                    }
                });
            }
            "--memory-floor-bytes" => {
                let value = parse_u64(&text_value(&args, &mut index, flag)?, flag)?;
                if value == 0 {
                    return Err(cli_error(
                        "invalid_memory_floor",
                        "memory floor must be nonzero",
                    ));
                }
                memory_floor_bytes = Some(value);
            }
            "--environment-manifest" => {
                environment_manifest = Some(path_value(&args, &mut index, flag)?)
            }
            "--repository-root" => repository_root = Some(path_value(&args, &mut index, flag)?),
            "--checkpoint-manifest" => {
                checkpoint_manifest = Some(path_value(&args, &mut index, flag)?)
            }
            "--tokens" => tokens = Some(parse_tokens(&text_value(&args, &mut index, flag)?)?),
            "--n-new" => {
                let value = parse_u64(&text_value(&args, &mut index, flag)?, flag)?;
                n_new = Some(
                    u32::try_from(value)
                        .map_err(|_| cli_error("invalid_n_new", "--n-new exceeds u32"))?,
                );
            }
            "--expected-token" => {
                let value = parse_u64(&text_value(&args, &mut index, flag)?, flag)?;
                expected_token = Some(u32::try_from(value).map_err(|_| {
                    cli_error("invalid_expected_token", "--expected-token exceeds u32")
                })?);
            }
            "--numerical-mode" => {
                numerical_mode = Some(match text_value(&args, &mut index, flag)?.as_str() {
                    "exact-qualification-scaffold" => NumericalMode::ExactQualificationScaffold,
                    "production-mlx-tier-b" => NumericalMode::ProductionMlxTierB,
                    value => {
                        return Err(cli_error(
                            "invalid_numerical_mode",
                            format!("unsupported numerical mode {value:?}"),
                        ))
                    }
                });
            }
            "--dry-run" => select_mode(&mut selected_mode, RunnerMode::DryRun)?,
            "--adapter-preflight-only" => {
                select_mode(&mut selected_mode, RunnerMode::AdapterPreflight)?
            }
            "--checkpoint-identity-only" => {
                select_mode(&mut selected_mode, RunnerMode::CheckpointIdentity)?
            }
            "--fixture-checkpoint-identity-only" => {
                select_mode(&mut selected_mode, RunnerMode::FixtureCheckpointIdentity)?
            }
            "--fixture-mode" => {
                let manifest = path_value(&args, &mut index, flag)?;
                select_mode(&mut selected_mode, RunnerMode::Fixture { manifest })?;
            }
            "--fixture-projection-boundary" => {
                let package = path_value(&args, &mut index, flag)?;
                select_mode(
                    &mut selected_mode,
                    RunnerMode::FixtureProjection { package },
                )?;
            }
            "--real-projection-boundary" => {
                let package = path_value(&args, &mut index, flag)?;
                select_mode(&mut selected_mode, RunnerMode::RealProjection { package })?;
            }
            "--help" | "--version" => {
                return Err(cli_error(
                    "mixed_meta_option",
                    format!("{flag} must be used alone"),
                ))
            }
            _ => {
                return Err(cli_error(
                    "unknown_option",
                    format!("unknown option {flag}"),
                ))
            }
        }
        index += 1;
    }

    let mode = selected_mode.unwrap_or(RunnerMode::P1);
    let config = Config {
        out: required(out, "--out")?,
        validation_mode: required(validation_mode, "--validation-mode")?,
        stream_mode: required(stream_mode, "--stream-mode")?,
        memory_floor_bytes: required(memory_floor_bytes, "--memory-floor-bytes")?,
        environment_manifest: required(environment_manifest, "--environment-manifest")?,
        repository_root,
        checkpoint_manifest,
        tokens: tokens.unwrap_or_default(),
        n_new: n_new.unwrap_or(0),
        expected_token,
        numerical_mode,
        mode,
        execution_config: None,
    };
    validate_combination(&config)?;
    Ok(ParseOutcome::Run(config))
}

fn validate_combination(config: &Config) -> Result<(), RunnerError> {
    let has_execution =
        !config.tokens.is_empty() || config.n_new != 0 || config.expected_token.is_some();
    match &config.mode {
        RunnerMode::DryRun | RunnerMode::AdapterPreflight => {
            if config.checkpoint_manifest.is_some()
                || has_execution
                || config.numerical_mode.is_some()
            {
                return Err(cli_error(
                    "incompatible_options",
                    "checkpoint and token options are forbidden in this mode",
                ));
            }
        }
        RunnerMode::CheckpointIdentity | RunnerMode::FixtureCheckpointIdentity => {
            if config.checkpoint_manifest.is_none() {
                return Err(cli_error(
                    "missing_option",
                    "checkpoint identity mode requires --checkpoint-manifest",
                ));
            }
            if has_execution || config.numerical_mode.is_some() {
                return Err(cli_error(
                    "incompatible_options",
                    "token execution options are forbidden in identity-only mode",
                ));
            }
        }
        RunnerMode::Fixture { .. } => {
            if config.checkpoint_manifest.is_some() || has_execution {
                return Err(cli_error(
                    "incompatible_options",
                    "fixture mode takes its model and expected token from the fixture manifest",
                ));
            }
            if config.numerical_mode.is_none() {
                return Err(cli_error(
                    "missing_option",
                    "fixture mode requires explicit --numerical-mode",
                ));
            }
        }
        RunnerMode::FixtureProjection { .. } | RunnerMode::RealProjection { .. } => {
            if config.repository_root.is_none() {
                return Err(cli_error(
                    "missing_option",
                    "projection boundary mode requires --repository-root",
                ));
            }
            if config.checkpoint_manifest.is_none() {
                return Err(cli_error(
                    "missing_option",
                    "projection boundary mode requires --checkpoint-manifest",
                ));
            }
            if has_execution || config.numerical_mode != Some(NumericalMode::ProductionMlxTierB) {
                return Err(cli_error(
                    "incompatible_options",
                    "projection boundary mode requires production-mlx-tier-b and forbids token execution options",
                ));
            }
        }
        RunnerMode::P1 => {
            if config.checkpoint_manifest.is_none()
                || config.tokens.is_empty()
                || config.n_new == 0
                || config.expected_token.is_none()
            {
                return Err(cli_error(
                    "missing_option",
                    "P1 requires checkpoint manifest, tokens, n-new, and expected-token",
                ));
            }
            if config.validation_mode != ValidationMode::GoldenStrict {
                return Err(cli_error(
                    "p1_validation_mode",
                    "P1 requires golden-strict validation",
                ));
            }
            if config.n_new != 1 {
                return Err(cli_error(
                    "p1_token_bound",
                    "the first F017 gate admits exactly one new token",
                ));
            }
            if config.numerical_mode != Some(NumericalMode::ProductionMlxTierB) {
                return Err(cli_error(
                    "p1_numerical_mode",
                    "P1 requires explicit production-mlx-tier-b mode",
                ));
            }
        }
    }
    if !matches!(
        config.mode,
        RunnerMode::FixtureProjection { .. } | RunnerMode::RealProjection { .. }
    ) && config.repository_root.is_some()
    {
        return Err(cli_error(
            "incompatible_options",
            "--repository-root is only valid for projection boundary modes",
        ));
    }
    Ok(())
}

fn select_mode(target: &mut Option<RunnerMode>, value: RunnerMode) -> Result<(), RunnerError> {
    if target.is_some() {
        return Err(cli_error(
            "multiple_modes",
            "runner mode flags are mutually exclusive",
        ));
    }
    *target = Some(value);
    Ok(())
}

fn required<T>(value: Option<T>, flag: &'static str) -> Result<T, RunnerError> {
    value.ok_or_else(|| cli_error("missing_option", format!("missing required option {flag}")))
}

fn text_value(args: &[OsString], index: &mut usize, flag: &str) -> Result<String, RunnerError> {
    *index += 1;
    args.get(*index)
        .and_then(|value| value.to_str())
        .map(ToOwned::to_owned)
        .ok_or_else(|| {
            cli_error(
                "missing_option_value",
                format!("{flag} requires a UTF-8 value"),
            )
        })
}

fn path_value(args: &[OsString], index: &mut usize, flag: &str) -> Result<PathBuf, RunnerError> {
    *index += 1;
    args.get(*index)
        .map(PathBuf::from)
        .ok_or_else(|| cli_error("missing_option_value", format!("{flag} requires a path")))
}

fn parse_u64(value: &str, flag: &str) -> Result<u64, RunnerError> {
    value.parse().map_err(|_| {
        cli_error(
            "invalid_integer",
            format!("{flag} requires an unsigned integer"),
        )
    })
}

fn parse_tokens(value: &str) -> Result<Vec<u32>, RunnerError> {
    if value.is_empty() {
        return Err(cli_error("invalid_tokens", "--tokens cannot be empty"));
    }
    value
        .split(',')
        .map(|token| {
            token
                .parse::<u32>()
                .map_err(|_| cli_error("invalid_tokens", format!("invalid token ID {token:?}")))
        })
        .collect()
}

fn cli_error(code: &'static str, message: impl Into<String>) -> RunnerError {
    RunnerError::new(FailureClass::InfrastructureEvidence, code, message)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn common() -> Vec<OsString> {
        [
            "--out",
            "evidence.json",
            "--validation-mode",
            "golden-strict",
            "--stream-mode",
            "owned-device",
            "--memory-floor-bytes",
            "17179869184",
            "--environment-manifest",
            "environment.json",
        ]
        .into_iter()
        .map(OsString::from)
        .collect()
    }

    #[test]
    fn parses_dry_run_and_strict_p1() {
        let mut dry = common();
        dry.push("--dry-run".into());
        let ParseOutcome::Run(dry) = parse_args(dry).unwrap() else {
            panic!("run")
        };
        assert_eq!(dry.mode, RunnerMode::DryRun);

        let mut p1 = common();
        p1.extend(
            [
                "--checkpoint-manifest",
                "checkpoint.json",
                "--tokens",
                "9703",
                "--n-new",
                "1",
                "--expected-token",
                "21615",
                "--numerical-mode",
                "production-mlx-tier-b",
            ]
            .into_iter()
            .map(OsString::from),
        );
        let ParseOutcome::Run(p1) = parse_args(p1).unwrap() else {
            panic!("run")
        };
        assert_eq!(p1.mode, RunnerMode::P1);
        assert_eq!(p1.tokens, [9703]);
    }

    #[test]
    fn rejects_unknown_duplicate_and_mixed_modes() {
        let mut unknown = common();
        unknown.push("--mystery".into());
        assert_eq!(parse_args(unknown).unwrap_err().code, "unknown_option");

        let mut duplicate = common();
        duplicate.extend(
            ["--out", "second.json", "--dry-run"]
                .into_iter()
                .map(OsString::from),
        );
        assert_eq!(parse_args(duplicate).unwrap_err().code, "duplicate_option");

        let mut mixed = common();
        mixed.extend(
            ["--dry-run", "--adapter-preflight-only"]
                .into_iter()
                .map(OsString::from),
        );
        assert_eq!(parse_args(mixed).unwrap_err().code, "multiple_modes");
    }

    #[test]
    fn rejects_p1_without_exact_gate() {
        let mut p1 = common();
        p1.extend(
            [
                "--checkpoint-manifest",
                "checkpoint.json",
                "--tokens",
                "9703",
                "--n-new",
                "2",
                "--expected-token",
                "21615",
                "--numerical-mode",
                "production-mlx-tier-b",
            ]
            .into_iter()
            .map(OsString::from),
        );
        assert_eq!(parse_args(p1).unwrap_err().code, "p1_token_bound");
    }

    #[test]
    fn projection_requires_explicit_repository_root_and_other_modes_reject_it() {
        let projection = || {
            let mut args = common();
            args.extend(
                [
                    "--checkpoint-manifest",
                    "checkpoint.json",
                    "--fixture-projection-boundary",
                    "package.json",
                    "--numerical-mode",
                    "production-mlx-tier-b",
                ]
                .into_iter()
                .map(OsString::from),
            );
            args
        };
        assert_eq!(parse_args(projection()).unwrap_err().code, "missing_option");
        let mut admitted = projection();
        admitted.extend(
            ["--repository-root", "/reviewed/repository"]
                .into_iter()
                .map(OsString::from),
        );
        assert!(matches!(parse_args(admitted), Ok(ParseOutcome::Run(_))));

        let mut dry = common();
        dry.extend(
            ["--dry-run", "--repository-root", "/wrong"]
                .into_iter()
                .map(OsString::from),
        );
        assert_eq!(parse_args(dry).unwrap_err().code, "incompatible_options");
    }

    #[test]
    fn mode_environment_policy_is_explicit_for_every_mode() {
        assert_eq!(
            RunnerMode::AdapterPreflight.environment_policy(),
            EnvironmentPolicy::ProductionReviewed
        );
        assert_eq!(
            RunnerMode::CheckpointIdentity.environment_policy(),
            EnvironmentPolicy::ProductionReviewed
        );
        assert_eq!(
            RunnerMode::P1.environment_policy(),
            EnvironmentPolicy::ProductionReviewed
        );
        assert_eq!(
            RunnerMode::FixtureCheckpointIdentity.environment_policy(),
            EnvironmentPolicy::CheckpointFreeFixture
        );
        assert_eq!(
            RunnerMode::Fixture {
                manifest: PathBuf::from("fixture.json")
            }
            .environment_policy(),
            EnvironmentPolicy::AnyValidated
        );
        assert_eq!(
            RunnerMode::DryRun.environment_policy(),
            EnvironmentPolicy::AnyValidated
        );
        assert_eq!(mode_environment_policy("unknown"), None);
    }

    #[test]
    fn parses_explicit_fixture_checkpoint_identity_mode() {
        let mut args = common();
        args.extend(
            [
                "--fixture-checkpoint-identity-only",
                "--checkpoint-manifest",
                "checkpoint.json",
            ]
            .into_iter()
            .map(OsString::from),
        );
        let ParseOutcome::Run(config) = parse_args(args).unwrap() else {
            panic!("run")
        };
        assert_eq!(config.mode, RunnerMode::FixtureCheckpointIdentity);
    }

    #[test]
    fn m1d_config_only_entry_rejects_duplicate_conflicting_or_manual_options() {
        let cases = [
            vec!["--m1d-execution-config", "config.json"],
            vec![
                "--m1d-execution-config",
                "config.json",
                "--execution-config-sha256",
                "0",
                "--activation-fixture",
                "wrong.json",
            ],
            vec![
                "--m1d-execution-config",
                "config.json",
                "--m1d-execution-config",
                "other.json",
            ],
            vec![
                "--execution-config-sha256",
                "0",
                "--m1d-execution-config",
                "config.json",
            ],
        ];
        for case in cases {
            let error = parse_args(case.into_iter().map(OsString::from)).unwrap_err();
            assert_eq!(error.code, "m1d_config_only");
        }
    }
}
