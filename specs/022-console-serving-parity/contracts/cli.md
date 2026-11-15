# Command Line and Ready Line Contract

**Status**: draft. CNF-07 wrote the ready-line contract (section 2) and the process
harness contract (section 5) on 2026-11-15. The command line itself (section 1), the
port-in-use error (section 3) and the exit codes (section 4) are restated from the API-17
detail and are settled by API-08 (the minimal M1 entry point, lead decision LD31) and
API-17 (the full command line, M4), which update this file in the same change.

**Scope**: how `pulsar-console` is started, how it says it is ready, how it ends, and how
the conformance harness (`console_conformance::process`) starts and stops it. Like every
contract of this feature, it describes a server qualified on synthetic backends only.

**Donor reference**: project-maya at `7e68a30f`, `serve/server.py:7115-7452` (`main`),
`serve/server.py:7385-7390` (the ready line), `serve/server.py:7166-7171` (the port check),
and `serve/test_stop.py:70-145` (the donor's process helpers).

## 1. Command line (restated; API-17 settles)

The command line follows Python `argparse` conventions, as the donor's does: long options,
the `--opt=value` form, unique-prefix abbreviations (`allow_abbrev` stays on), a repeatable
`--script`, usage errors that exit with status 2 after `usage: ...` and `error: ...` on
standard error, and `--help`. The options planned by API-17 are `--engine`, `--config`,
`--host`, `--port` (default 8095), `--script`, `--gpu`, `--tokenizer`, `--open`,
`--idle-unload SECONDS`, `--fit-max-tokens`, `--api-key` (default from the environment),
`--mcp-config`, `--parent-pipe` and a development flag for the asset directory. The engine
names, and how the donor's `maya` and `strata` names are treated, are API-17's
(BRAND-1.6). API-08's minimal entry point offers the subset M1 needs: the scripted engine,
the listen address and the port.

The harness depends on two options only: `--port` (it always passes `--port 0`) and
`--config` (it passes the run config it generated, when there is one).

## 2. The ready line

### 2.1 Form

Once the server accepts connections, it prints exactly one ready line on standard output,
flushed, in the donor's form:

```text
ready: http://<here>:<port>/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context <N> tokens[, images on][, API key required])
```

- There are two spaces between `/v1` and `(`.
- `<here>` is `127.0.0.1` when the bind address is `0.0.0.0`, the empty string or `::`;
  otherwise it is the bind address as given, printed bare: an IPv6 address has no
  brackets (`http://::1:8095/v1`), as in the donor.
- `<N>` is the engine's context size in tokens, a decimal integer.
- `, images on` is present when picture input is on, and `, API key required` when an API
  key is set; when both are present they come in that order.
- The line has no `[console]` prefix and no time stamp: the donor prints it with a plain
  `print`, and the time stamp is written only before lines that start with the log prefix
  (API-16).

The next line is the browser hint, in the donor's text:

```text
       open http://<here>:<port>/ in a browser to chat; close this window to stop the model
```

When the bind address is not a loopback name, one line per LAN address follows
(`       from other devices: http://<ip>:<port>/   (API: http://<ip>:<port>/v1)`), as the
API-17 detail describes. Whether the hint's wording changes under BRAND-1 or PLAN-1 is
API-17's to settle; the harness does not read it.

### 2.2 The port

The ready line names the port the server is listening on. For any port other than 0 this
is the port of `--port`, as in the donor. Under `--port 0` the server must print the port
the operating system chose. The donor prints the requested port (`a.port`,
`serve/server.py:7387`), so under `--port 0` its line would say `:0`; the donor's own
tests never start `main` with port 0 (they probe a free port first), and the donor already
keeps the bound port as `svc.listen` (`serve/server.py:6798`). Printing the bound port is
needed by the harness, which never probes for a free port (tasks/conformance.md,
"Determinism rules"). It differs from the donor only when the port is 0, and it is
proposal P-25 in [deviations.md](deviations.md), awaiting the owner's decision. The
harness refuses a ready line that names port 0.

### 2.3 Proposed synthetic marker (not approved)

A synthetic-backend marker on the ready line is a proposal recorded with PLAN-1 in the
deviation register; its text is open (OPEN-35), and FR-050 does not require it unless the
owner approves it. If it is approved, it is a suffix after the closing parenthesis,
separated from it by whitespace. Until then the server prints the line without it, and the
harness accepts the line with or without a suffix and records the suffix's text without
judging it (`ReadyLine::suffix`). The marker is not the synthetic-provenance declaration
of a line-protocol engine, which is a separate matter (R29, OPEN-58).

### 2.4 The oracle form

The oracle driver of CNF-08 (M10) does not run the donor's `main`; it prints
`CNF-READY port=<n>` once its server listens. The harness accepts this form only when the
caller asks for it (`ReadyExpect::Oracle` or `ReadyExpect::Either`).

### 2.5 What the harness checks

- A line on standard output that starts with `ready:` (or `CNF-READY` when that form is
  accepted) must parse in full; one that does not is an error, not a line to skip.
- The port must not be 0, and the address must be a loopback address (or `localhost`);
  the harness talks to nothing else. A line that breaks either rule is an error.
- These rules hold whichever comes first, the line or the process's exit.
- The line must come within the ready deadline (section 5.3). A process that ends, or
  closes its standard output, before it is an error that carries the output seen; it
  is reported as soon as it is known, not at the deadline.

## 3. Port in use (restated; API-17 settles)

Before any model or engine work, the server binds and closes the address once. When that
fails it exits through the usage-error path (status 2, `usage: ...` then `error: ...` on
standard error) with the donor's message, rebranded under BRAND-1:
`port <N> is already in use - is Maya (or another server) already running? Close it, or
start this one with a different --port` (`serve/server.py:7170-7171`). The product's
wording of the server's name in that message is API-17's to fix.

## 4. Exit codes (restated; API-16, API-17 and API-08 settle)

| Status | When |
| --- | --- |
| 0 | A requested stop (signal, parent pipe) that completed: the line `[console] stopping (<why>): the engine ends` was printed and the engine closed. |
| 2 | A usage error, including the port-in-use error. |
| 76 | A restart requested through the admin routes (API-13, API-14). |
| 130 | A second `SIGINT` while stopping (`[console] stopped at once: ...`). |
| non-zero | At process start, an engine that does not report synthetic provenance is refused after one line on standard error that names the engine kind, what the engine reported and `docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md` (R29, LD28; API-08 pins it). |

## 5. Process harness contract (CNF-07)

`console_conformance::process` starts the server, the fake engines, or any synthetic
program, from outside.

### 5.1 Start

- The program runs in a new process group (its pid is its group id).
- The environment is cleared and filled from an allowlist: `PATH` (the harness's own, or
  `/usr/bin:/bin`), `TZ=UTC`, `LC_ALL=C.UTF-8`, `LANG=C.UTF-8`, `HOME`,
  `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_CACHE_HOME`, `XDG_STATE_HOME`,
  `XDG_RUNTIME_DIR` and `TMPDIR` inside a fresh run directory, `PULSAR_CONSOLE_VENDOR_DIR`
  and `FAKE_ENGINE_GATE` when the caller gives them, and then the scenario's variables.
  A scenario variable may not use a reserved name: `PATH`, `HOME`, `TZ`, `LC_ALL`,
  `LANG`, `TMPDIR`, `PULSAR_CONSOLE_VENDOR_DIR`, `FAKE_ENGINE_GATE`, or a name that starts
  with `XDG_`, `LD_`, `DYLD_` or `PYTHON` (the CNF-02 rule). No `PULSAR_CONSOLE_*`,
  `MAYA_*` or `STRATA_*` setting and no proxy variable is inherited.
- The `env` block of a run config the harness writes is held to the same rule, because
  the server passes that block to its engine child.
- The working directory is the run's data directory, which also holds the generated run
  config (`pulsar-scenario.json`), the generated `bpe-bytes` tokenizer directory
  (`tokenizer/`) and the scenario's data files.
- Standard input is `/dev/null`, or a pipe the harness holds (for `--parent-pipe`).
- Standard output and standard error are captured, separately, to `stdout.txt` and
  `stderr.txt` in the run directory (up to 64 MiB each). The lines are also kept in
  memory, both streams together, up to 16 MiB and 100 000 lines by default; later lines
  are only counted, the pipes are always read to their end, and a transcript carried by
  an error holds at most its last 1 MiB. A run directory is removed after a clean run,
  and kept when a start fails (the error names it), when a test panics, when a process
  outlives `SIGKILL`, or when a drop finds a stop that was not clean.

### 5.2 Stop

1. The harness notes the program's descendants and the members of its group.
2. It sends `SIGTERM` to the group.
3. It waits up to the grace period for the program and every noted or group process to
   end. A zombie counts as ended; a reused pid is never taken for the process seen.
4. It sends `SIGKILL` to the group, and by pid to any leftover that left the group.
5. It waits up to the kill deadline and reads the remaining output.

A stop is clean when everything ended within the grace period. A process still running
after it is reported (`StopReport::after_term`, with whether it was still in the group),
and one still running after `SIGKILL` is left behind (`StopReport::after_kill`). Dropping
the harness's handle stops the program, so a failing test leaves nothing behind. A test
that calls the stop itself receives the report and judges it; when a handle is dropped
without that call (the implicit stop), a stop that was not clean fails the test: the
drop panics with the leak and keeps the run directory. While a test is already
panicking, the drop only prints, so the first failure stays the one reported.

For a server under test this means: on `SIGTERM` it must end its engine children within
the grace period, whether they stayed in its process group or not. An engine that leaves
the group must still end on its own, for example when its standard input closes, as the
donor's fake engines do.

Where the process table can be read, the harness learns that the program ended without
reaping it, and keeps it unreaped (a zombie) until the handle is dropped. Its pid, and so
the run's process-group id, therefore cannot be reused while the harness signals and
inspects the group. Where `waitid` is unavailable the program is reaped at once; the
harness then signals group members by pid after checking each one, and ignores the
group when the table shows its id taken by a new group leader. A signal sent to the
program alone (a scenario step, or the donor's `send_signal`) is sent only while the
program has not ended, so it never reaches a reused pid.

### 5.3 Deadlines

Every wait is a deadline, multiplied by `PULSAR_CONSOLE_TEST_TIME_SCALE` (a number above 0
and at most 1000; 1 when unset; any other value is an error, never ignored). The base
values are: ready line 20 s, grace period 10 s, kill deadline 10 s. Tests that must wait a
deadline out use a shorter base value.

### 5.4 Platforms

Descendants are found without `ps`: on Darwin through `proc_listallpids` and
`proc_pidinfo`, on Linux by reading `/proc/<pid>/stat`. Elsewhere only the process group is
checked, with `killpg(pgid, 0)`, and a process that left the group cannot be seen. The
Darwin behavior is exercised by the CNF-07 tests on a macOS host. The Linux behavior
(the `/proc` walk, `waitid` with `WNOWAIT` and the exit status read from it, the
unreaped program holding the group id, process groups) is written for Linux and its
`/proc` parser is unit-tested on every platform, but it is unverified on Linux until the
Linux CI job runs the CNF-07 tests.

### 5.5 Lifecycle tests

Process-lifecycle tests of one test binary hold `lifecycle_lock()` for their whole run,
so they run one at a time; other tests run in parallel on port 0, each in its own run
directory.
