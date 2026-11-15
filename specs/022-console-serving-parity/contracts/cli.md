# Command Line and Ready Line Contract

**Status**: draft. CNF-07 wrote the ready-line contract (section 2) and the process
harness contract (section 5) on 2026-11-15. API-08 (the minimal M1 entry point, lead
decision LD31) settled on 2026-11-15 what M1 builds: the M1 options and their argparse
conventions (section 1.1), the start-up order up to the ready line (section 1.2), the
line before the ready line (section 2.1), the port-in-use error (section 3) and the exit
codes of M1 (section 4). What is marked "API-17 settles" is still restated from the
API-17 detail and is settled by API-17 (the full command line, M4), which updates this
file in the same change.

**Scope**: how `pulsar-console` is started, how it says it is ready, how it ends, and how
the conformance harness (`console_conformance::process`) starts and stops it. Like every
contract of this feature, it describes a server qualified on synthetic backends only.

**Donor reference**: project-maya at `7e68a30f`, `serve/server.py:7115-7452` (`main`),
`serve/server.py:7385-7390` (the ready line), `serve/server.py:7166-7171` (the port check),
and `serve/test_stop.py:70-145` (the donor's process helpers).

## 1. Command line

The command line follows Python `argparse` conventions, as the donor's does: long options,
the `--opt=value` form, unique-prefix abbreviations (`allow_abbrev` stays on), a repeatable
`--script`, usage errors that exit with status 2 after `usage: ...` and `error: ...` on
standard error, and `--help`. The options planned by API-17 are `--engine`, `--config`,
`--host`, `--port` (default 8095), `--script`, `--gpu`, `--tokenizer`, `--open`,
`--idle-unload SECONDS`, `--fit-max-tokens`, `--api-key` (default from the environment),
`--mcp-config`, `--parent-pipe` and a development flag for the asset directory. The engine
names, and how the donor's `maya` and `strata` names are treated, are API-17's
(BRAND-1.6). API-08's minimal entry point offers the subset M1 needs (section 1.1); the
rest of the list above is API-17's to build and settle.

The harness depends on two options only: `--port` (it always passes `--port 0`) and
`--config` (it passes the run config it generated, when there is one).

### 1.1 The M1 options (settled by API-08)

`pulsar-console` of M1 (`console/crates/pulsar-console`: `pulsar_console::run`, with the
parser in `pulsar_console::cli`) takes, in the donor's order: `--config CONFIG`, `--host
HOST`, `--script SCRIPT` (repeatable: each request takes the next script and the last one
repeats; none gives the donor's default greeting), `--port PORT` (an integer as Python's
`int()` reads it, default 8095) and `--api-key API_KEY` (absent: the environment's
`PULSAR_CONSOLE_API_KEY`, then the run config's `api_key`), and `-h`/`--help`.

The argparse conventions built, following CPython 3.14 (LD38): `--opt value` and
`--opt=value`; unique prefixes of a long option (`--po 0`), and `ambiguous option: --h could
match --help, --host` for a prefix that is not unique; the last of a repeated option wins,
except `--script`, which appends; a value that looks like an option is refused (`argument
--host: expected one argument`), while an argument that starts with `-` and a digit, or
`-.` and a digit, is a value (`--host -1x` is accepted; `--port -5x` is `argument --port:
invalid int value: '-5x'`); an ambiguous prefix is refused only when the parse reaches it
(`-h --h` prints the help; `--port z --h` is the `--port` error); `-h` with text attached
is read as combined short flags (`-hh` and `-hx` print the help), while `-h=1`, `-h-x` and
`--help=1` are `argument -h/--help: ignored explicit argument '...'`; this command line has
no positional arguments, so `--` and everything after it are unrecognized arguments,
listed with the `--` (`--port 0 --` exits 2 with `unrecognized arguments: --`; `-- --port`
gives `unrecognized arguments: -- --port`), and an unknown option or extra argument is
`unrecognized arguments: ...`; a bad integer is `argument --port: invalid int value:
'<text>'`. Every usage error prints the usage on standard error, wrapped as argparse wraps
it at `COLUMNS` (80 when unset; below 30 columns the program name stands alone on the
first line and the options follow, indented by seven spaces), then `pulsar-console: error:
<message>`, and exits 2. `--help` prints the usage and the options on standard output and
exits 0. Not reproduced: the colors Python 3.14 gives a terminal's usage errors, the
terminal width read from the terminal itself (only `COLUMNS` is read), the wrapping of the
`--help` option list at `COLUMNS` (it is laid out for 80 columns; its usage line does follow
`COLUMNS`), and non-ASCII decimal digits in `--port` and in the negative-number test.
These four differences are proposal P-27 in [deviations.md](deviations.md), awaiting the
owner's decision.

The other options of the donor (`--engine`, `--gpu`, `--tokenizer`, `--open`,
`--idle-unload`, `--fit-max-tokens`, `--mcp-config`, `--parent-pipe` and the dashboard's
development flag) are API-17's; until it lands they are unrecognized arguments. The M1
binary has one engine, the scripted engine (`pulsar_console::scripted_factory`, the only
factory `main` names), with the model name `pulsar-console-synthetic` unless the run config
names one (`model_name`); no flag, environment variable or configuration key selects
another engine.

### 1.2 Start-up order of M1 (settled by API-08)

In the donor's order (`serve/server.py:7115-7392`), up to the ready line:

1. the command line (usage errors, exit 2);
2. the run config of `--config` and the environment with the config's server entries laid
   over it (API-15); an unreadable or invalid config prints `config: <message>` on standard
   error and exits 1;
3. the host (`--host`, else the config's `host`, else `127.0.0.1`), then the port probe
   (section 3), before anything is started;
4. the server settings: API key, CORS origins and `allowed_hosts` (`config: <message>` and
   exit 1 for a bad value); an `allowed_hosts` entry that can never match stops the start
   with `config: allowed_hosts: '<entry>' is not a host name the server can match; the
   accepted forms are name, name:port, [v6] or [v6]:port` and exit 1 (LD40); the
   transport's backlog, body limit and socket timeout come from the same environment;
5. the byte tokenizer and the scripted engine (a bad `PULSAR_CONSOLE_MOCK_TOK_S` prints the
   engine's message and exits 1);
6. the turn driver, which admits the engine through the synthetic-only guard (section 4,
   last row); then, when the run config lists CORS origins, the donor's line
   `[console] browser pages allowed to call /v1/* (CORS): <origin>, <origin>` on standard
   output (`serve/server.py:7330-7331`, with the product's prefix under BRAND-1);
7. the router with its guards, the inference driver and the OpenAI Chat Completions
   dialect on `/v1/chat/completions` (the only route M1 serves);
8. the listener, then the lines of section 2.1, on standard output, each flushed.

Signals keep their default behavior in M1; the shutdown order, the second `SIGINT`, the
parent pipe, the log tee and its time stamps are API-17's and API-16's (M4). The scripted
engine's start reads no `sampling` block from the run config, as the donor's mock path
does not (`serve/server.py:7285-7289`). A refused `sampling` block, which prints its notes
on standard output and its message on standard error before a non-zero exit, therefore
belongs to the line engine's start of API-17 (lead decision LD52, 2026-11-15); the helper
`pulsar_console::report_sampling_error` exists for it and has no caller in M1.

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
API-17's to settle; the harness does not read it. The M1 entry point prints the ready line
and the hint only: the LAN addresses, the no-API-key warning and the firewall hint of a
non-loopback bind are API-17's.

Right before the ready line, the M1 entry point prints one line that says the engine is
synthetic and that no real model is served (lead decision LD46):

```text
[console] engine: scripted, synthetic provenance - no real model is served
```

It is a log line of the server (with the `[console]` prefix), not part of the ready line,
and it is not the proposed synthetic marker of section 2.3. In M1 the ready line names
`/v1/responses` and `/v1/messages`, as the donor's does, although only
`/v1/chat/completions` is served until those packages land.

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

## 3. Port in use (settled by API-08)

Before any model or engine work, the server binds and closes the address once. When that
fails (for any operating-system error, as the donor catches `OSError`), it exits through
the usage-error path (status 2, the usage then `pulsar-console: error: ...` on standard
error) with the donor's message, rebranded under BRAND-1:

```text
port <N> is already in use - is PulsarMLX Console (or another server) already running? Close it, or start this one with a different --port
```

(`serve/server.py:7166-7171`). A port outside 0 to 65535 is not a usage error: the donor's
`bind` raises an `OverflowError` it does not catch, so the M1 entry point prints
`OverflowError: bind(): port must be 0-65535.` on standard error and exits 1. API-17 keeps
this wording unless it changes this section.

## 4. Exit codes (API-08 settles the M1 rows; API-16 and API-17 the others)

| Status | When |
| --- | --- |
| 0 | `--help` (M1). A requested stop (signal, parent pipe) that completed: the line `[console] stopping (<why>): the engine ends` was printed and the engine closed (API-17; in M1 a signal ends the process with the operating system's default behavior). |
| 1 | A start-up failure before the ready line (M1): a run config or setting the server refuses (`config: ...`), an `allowed_hosts` entry that can never match, a port outside 0 to 65535, an engine that did not start, a listener that could not be bound after the probe, and the synthetic-only refusal below. |
| 2 | A usage error, including the port-in-use error (M1). |
| 76 | A restart requested through the admin routes (API-13, API-14). |
| 130 | A second `SIGINT` while stopping (`[console] stopped at once: ...`; API-17). |
| 1 | At process start, an engine that does not report synthetic provenance is refused after one line on standard error that names the engine kind, what the engine reported and `docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md`, and nothing is served (R29, LD28). The line is the `Display` of `ProvenanceRefused`: `[console] refusing to start: engine <kind> reports provenance <reported>; this build serves synthetic engines only. See docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md`. Pinned by `pulsar-console::api08_refusal::process_start_refuses_an_engine_that_is_not_synthetic` and `::process_start_refuses_an_engine_that_declares_no_provenance` (API-08; API-17 keeps them). |

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
