# Security Policy

## Supported status

PulsarMLX is experimental software and does not yet publish stable, supported
release lines or a security-response service-level agreement. Security reports
for the current default branch are welcome. Older commits and downstream builds
may not receive fixes.

The inherited Linux/CUDA runtime and the experimental Apple Silicon/MLX work
have different maturity levels. Documentation of a capability does not imply
that it has received a security audit.

## Reporting a vulnerability

Report suspected vulnerabilities privately through this repository's GitHub
Security Advisory form:

<https://github.com/MahdiHedhli/PulsarMLX/security/advisories/new>

In GitHub, this is available from **Security** > **Advisories** > **Report a
vulnerability** when private vulnerability reporting is enabled. Include:

- the affected revision and platform;
- the impact and required preconditions;
- concise reproduction steps or a minimal proof of concept;
- suggested mitigations, if known; and
- whether the issue also appears in upstream Pulsar.

Do not disclose vulnerability details, exploit code, credentials, tokens,
private keys, model access secrets, or other sensitive data in a public issue,
discussion, pull request, log, or test fixture. If GitHub's private reporting
form is unavailable, open a minimal public issue asking the maintainers to
enable a private reporting channel, without including sensitive details.

Maintainers should acknowledge and assess reports through the private advisory,
coordinate a fix and disclosure when warranted, and credit reporters who wish
to be credited. Response and remediation timing depends on severity and
maintainer availability; no fixed deadline is promised for this experimental
project.

## Model and data safety

Treat model files, tokenizer files, prompts, benchmark corpora, and generated
metadata as untrusted local inputs. Obtain them from known sources, verify
checksums when available, and avoid running the inference process with elevated
privileges. Do not commit model weights or private datasets. A parser crash or
malformed-model failure should be reported when it crosses a security boundary
or creates a meaningful denial-of-service risk.

## Upstream and fork scope

Report vulnerabilities introduced by PulsarMLX changes here. If a vulnerability
is reproducible in unmodified Pulsar, also follow the upstream project's
preferred private reporting process when one is available. Do not publicly
cross-post sensitive details. The upstream author and contributors do not
endorse, maintain, or bear responsibility for PulsarMLX modifications.
