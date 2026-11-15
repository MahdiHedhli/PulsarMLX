//! `cnf_child`: the test-only child of the process harness (CNF-07).
//!
//! It stands in for a server under test, which does not exist yet in M1, so that the
//! harness in `console_conformance::process` can be proven: it binds a loopback port
//! (port 0 picks a free one), prints the ready line of `contracts/cli.md` with the port
//! it bound, and can fork a grandchild that stays in its process group, leaves it, or
//! ignores `SIGTERM`. It is never shipped and serves nothing but one fixed line per
//! connection.
//!
//! ```text
//! cnf_child serve [--port N] [--host H] [--context N] [--images] [--api-key-required]
//!                 [--ready-suffix TEXT] [--ready-port-zero] [--malformed-ready]
//!                 [--oracle-ready] [--no-ready] [--exit-before-ready CODE]
//!                 [--ready-host H] [--exit-after-ready CODE] [--spam-after-ready N]
//!                 [--close-stdout]
//!                 [--print-env NAME]... [--print-cwd] [--stderr TEXT]
//!                 [--on-term default|ignore|exit0] [--exit-on-stdin-eof]
//!                 [--grandchild in-group|escape] [--grandchild-on-term default|ignore]
//!                 [--grandchild-stdin-eof-exits]
//! cnf_child grandchild [--on-term default|ignore] [--stdin-eof-exits]
//! ```
//!
//! Before the ready line it prints, in this order: `env NAME=<value>` (or
//! `env NAME unset`) for each `--print-env`, `cwd <path>` for `--print-cwd`,
//! `grandchild pid=<n>` when it started one (once the grandchild has written `ok` to its
//! parent, after setting up its signal disposition), and the `--stderr` text on standard
//! error.
//!
//! `--ready-host H` prints `H` as the ready line's address while the child still binds
//! loopback. `--spam-after-ready N` prints `N` lines of 100 bytes after the ready line and
//! the browser hint; `--exit-after-ready CODE` then exits with `CODE`. `--close-stdout`
//! closes standard output where the ready line would come and keeps running.

use std::process::ExitCode;

#[cfg(unix)]
fn main() -> ExitCode {
    unix::main()
}

/// The child needs process groups and POSIX signals; elsewhere it only says so.
#[cfg(not(unix))]
fn main() -> ExitCode {
    eprintln!("cnf_child: Unix only");
    ExitCode::from(2)
}

#[cfg(unix)]
mod unix {
    use std::io::{Read, Write};
    use std::net::{IpAddr, SocketAddr, TcpListener};
    use std::process::{Command, ExitCode, Stdio};

    const USAGE: &str = "usage: cnf_child serve [options] | cnf_child grandchild [options]";

    #[derive(Default)]
    struct ServeArgs {
        port: u16,
        host: Option<String>,
        context: u64,
        images: bool,
        api_key_required: bool,
        ready_suffix: Option<String>,
        ready_port_zero: bool,
        malformed_ready: bool,
        oracle_ready: bool,
        no_ready: bool,
        exit_before_ready: Option<u8>,
        ready_host: Option<String>,
        exit_after_ready: Option<u8>,
        spam_after_ready: u32,
        close_stdout: bool,
        print_env: Vec<String>,
        print_cwd: bool,
        stderr: Option<String>,
        on_term: OnTerm,
        exit_on_stdin_eof: bool,
        grandchild: Option<Grandchild>,
        grandchild_on_term: OnTerm,
        grandchild_stdin_eof_exits: bool,
    }

    #[derive(Clone, Copy, Default, PartialEq)]
    enum OnTerm {
        #[default]
        Default,
        Ignore,
        Exit0,
    }

    #[derive(Clone, Copy, PartialEq)]
    enum Grandchild {
        InGroup,
        Escape,
    }

    pub(super) fn main() -> ExitCode {
        let args: Vec<String> = std::env::args().skip(1).collect();
        let result = match args.first().map(String::as_str) {
            Some("serve") => parse_serve(args.get(1..).unwrap_or_default()).and_then(serve),
            Some("grandchild") => grandchild(args.get(1..).unwrap_or_default()),
            _ => Err(USAGE.to_string()),
        };
        match result {
            Ok(code) => code,
            Err(message) => {
                eprintln!("cnf_child: {message}");
                ExitCode::from(2)
            }
        }
    }

    fn parse_on_term(v: &str) -> Result<OnTerm, String> {
        match v {
            "default" => Ok(OnTerm::Default),
            "ignore" => Ok(OnTerm::Ignore),
            "exit0" => Ok(OnTerm::Exit0),
            _ => Err(format!("unknown --on-term value {v:?}")),
        }
    }

    fn parse_serve(args: &[String]) -> Result<ServeArgs, String> {
        let mut a = ServeArgs {
            context: 32768,
            ..ServeArgs::default()
        };
        let mut it = args.iter();
        while let Some(flag) = it.next() {
            let mut value = || {
                it.next()
                    .cloned()
                    .ok_or_else(|| format!("{flag} needs a value"))
            };
            match flag.as_str() {
                "--port" => a.port = value()?.parse().map_err(|_| "bad --port".to_string())?,
                "--host" => a.host = Some(value()?),
                "--context" => {
                    a.context = value()?.parse().map_err(|_| "bad --context".to_string())?
                }
                "--images" => a.images = true,
                "--api-key-required" => a.api_key_required = true,
                "--ready-suffix" => a.ready_suffix = Some(value()?),
                "--ready-port-zero" => a.ready_port_zero = true,
                "--malformed-ready" => a.malformed_ready = true,
                "--oracle-ready" => a.oracle_ready = true,
                "--no-ready" => a.no_ready = true,
                "--exit-before-ready" => {
                    a.exit_before_ready = Some(
                        value()?
                            .parse()
                            .map_err(|_| "bad --exit-before-ready".to_string())?,
                    )
                }
                "--ready-host" => a.ready_host = Some(value()?),
                "--exit-after-ready" => {
                    a.exit_after_ready = Some(
                        value()?
                            .parse()
                            .map_err(|_| "bad --exit-after-ready".to_string())?,
                    )
                }
                "--spam-after-ready" => {
                    a.spam_after_ready = value()?
                        .parse()
                        .map_err(|_| "bad --spam-after-ready".to_string())?
                }
                "--close-stdout" => a.close_stdout = true,
                "--print-env" => a.print_env.push(value()?),
                "--print-cwd" => a.print_cwd = true,
                "--stderr" => a.stderr = Some(value()?),
                "--on-term" => a.on_term = parse_on_term(&value()?)?,
                "--exit-on-stdin-eof" => a.exit_on_stdin_eof = true,
                "--grandchild" => {
                    a.grandchild = Some(match value()?.as_str() {
                        "in-group" => Grandchild::InGroup,
                        "escape" => Grandchild::Escape,
                        other => return Err(format!("unknown --grandchild value {other:?}")),
                    })
                }
                "--grandchild-on-term" => a.grandchild_on_term = parse_on_term(&value()?)?,
                "--grandchild-stdin-eof-exits" => a.grandchild_stdin_eof_exits = true,
                other => return Err(format!("unknown option {other:?}; {USAGE}")),
            }
        }
        Ok(a)
    }

    extern "C" fn exit_zero(_sig: libc::c_int) {
        // SAFETY: _exit is async-signal-safe and ends the process at once.
        unsafe { libc::_exit(0) }
    }

    fn install_on_term(on: OnTerm) {
        let handler = match on {
            OnTerm::Default => return,
            OnTerm::Ignore => libc::SIG_IGN,
            OnTerm::Exit0 => exit_zero as extern "C" fn(libc::c_int) as libc::sighandler_t,
        };
        // SAFETY: the handler is SIG_IGN or a function that only calls the
        // async-signal-safe _exit; it is installed before any other thread starts.
        unsafe {
            libc::signal(libc::SIGTERM, handler);
        }
    }

    fn say(line: &str) {
        let mut out = std::io::stdout().lock();
        let _ = writeln!(out, "{line}");
        let _ = out.flush();
    }

    fn serve(a: ServeArgs) -> Result<ExitCode, String> {
        install_on_term(a.on_term);
        for name in &a.print_env {
            match std::env::var(name) {
                Ok(v) => say(&format!("env {name}={v}")),
                Err(_) => say(&format!("env {name} unset")),
            }
        }
        if a.print_cwd {
            let cwd = std::env::current_dir().map_err(|e| format!("cwd: {e}"))?;
            say(&format!("cwd {}", cwd.display()));
        }
        let _held_grandchild = match a.grandchild {
            Some(kind) => {
                let exe = std::env::current_exe().map_err(|e| format!("current_exe: {e}"))?;
                let mut cmd = Command::new(exe);
                cmd.arg("grandchild");
                if a.grandchild_on_term == OnTerm::Ignore {
                    cmd.args(["--on-term", "ignore"]);
                }
                if a.grandchild_stdin_eof_exits {
                    cmd.arg("--stdin-eof-exits");
                }
                cmd.stdin(Stdio::piped())
                    .stdout(Stdio::piped())
                    .stderr(Stdio::null());
                if kind == Grandchild::Escape {
                    use std::os::unix::process::CommandExt;
                    cmd.process_group(0);
                }
                let mut child = cmd.spawn().map_err(|e| format!("grandchild: {e}"))?;
                // wait until the grandchild has set up its signal disposition
                let mut ok = [0u8; 3];
                if let Some(out) = child.stdout.as_mut() {
                    out.read_exact(&mut ok)
                        .map_err(|e| format!("grandchild handshake: {e}"))?;
                }
                if &ok != b"ok\n" {
                    return Err("grandchild handshake: unexpected bytes".to_string());
                }
                say(&format!("grandchild pid={}", child.id()));
                // the grandchild's stdin pipe stays open while this process lives
                Some(child)
            }
            None => None,
        };
        if let Some(text) = &a.stderr {
            let mut err = std::io::stderr().lock();
            let _ = writeln!(err, "{text}");
            let _ = err.flush();
        }
        if let Some(code) = a.exit_before_ready {
            return Ok(ExitCode::from(code));
        }

        let host = a.host.clone().unwrap_or_else(|| "127.0.0.1".to_string());
        let ip: IpAddr = host.parse().map_err(|_| format!("bad --host {host:?}"))?;
        if !ip.is_loopback() {
            return Err("cnf_child binds loopback only".to_string());
        }
        let listener =
            TcpListener::bind(SocketAddr::new(ip, a.port)).map_err(|e| format!("bind: {e}"))?;
        let port = listener
            .local_addr()
            .map_err(|e| format!("local_addr: {e}"))?
            .port();
        std::thread::spawn(move || {
            for mut c in listener.incoming().flatten() {
                let _ = c.write_all(b"cnf_child\n");
            }
        });

        if a.close_stdout {
            // SAFETY: closing fd 1 has no memory-safety preconditions; nothing writes to
            // standard output afterwards.
            unsafe {
                libc::close(1);
            }
        } else if !a.no_ready {
            let shown = if a.ready_port_zero { 0 } else { port };
            let host = a.ready_host.clone().unwrap_or_else(|| host.clone());
            if a.oracle_ready {
                say(&format!("CNF-READY port={shown}"));
            } else if a.malformed_ready {
                say(&format!("ready: http://{host}:{shown}/v1 (no routes)"));
            } else {
                let mut line = format!(
                    "ready: http://{host}:{shown}/v1  (OpenAI: /v1/chat/completions, /v1/responses, Anthropic: /v1/messages, context {} tokens",
                    a.context
                );
                if a.images {
                    line.push_str(", images on");
                }
                if a.api_key_required {
                    line.push_str(", API key required");
                }
                line.push(')');
                if let Some(s) = &a.ready_suffix {
                    line.push_str("  ");
                    line.push_str(s);
                }
                say(&line);
                say(&format!(
                    "       open http://{host}:{shown}/ in a browser to chat; close this window to stop the model"
                ));
            }
        }

        if !a.close_stdout {
            for i in 0..a.spam_after_ready {
                say(&format!("spam {i:>8} {}", "x".repeat(85)));
            }
        }
        if let Some(code) = a.exit_after_ready {
            return Ok(ExitCode::from(code));
        }
        if a.exit_on_stdin_eof {
            drain_stdin();
            say("stdin closed");
            return Ok(ExitCode::SUCCESS);
        }
        loop {
            std::thread::park();
        }
    }

    fn drain_stdin() {
        let mut buf = [0u8; 4096];
        let mut stdin = std::io::stdin().lock();
        loop {
            match stdin.read(&mut buf) {
                Ok(0) => return,
                Ok(_) => {}
                Err(e) if e.kind() == std::io::ErrorKind::Interrupted => {}
                Err(_) => return,
            }
        }
    }

    fn grandchild(args: &[String]) -> Result<ExitCode, String> {
        let mut on_term = OnTerm::Default;
        let mut stdin_eof_exits = false;
        let mut it = args.iter();
        while let Some(flag) = it.next() {
            match flag.as_str() {
                "--on-term" => {
                    on_term = parse_on_term(it.next().ok_or("--on-term needs a value")?)?;
                }
                "--stdin-eof-exits" => stdin_eof_exits = true,
                other => return Err(format!("unknown option {other:?}; {USAGE}")),
            }
        }
        install_on_term(on_term);
        say("ok");
        if stdin_eof_exits {
            drain_stdin();
            return Ok(ExitCode::SUCCESS);
        }
        loop {
            std::thread::park();
        }
    }
}
