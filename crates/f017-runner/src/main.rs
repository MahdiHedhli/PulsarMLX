use f017_runner::cli::{parse_args, ParseOutcome, USAGE};

fn main() {
    let config = match parse_args(std::env::args_os().skip(1)) {
        Ok(ParseOutcome::Run(config)) => config,
        Ok(ParseOutcome::Help) => {
            println!("{USAGE}");
            return;
        }
        Ok(ParseOutcome::Version) => {
            println!("f017-glm52-runner {}", env!("CARGO_PKG_VERSION"));
            return;
        }
        Err(error) => {
            eprintln!("f017-glm52-runner failed: {error}\n\n{USAGE}");
            std::process::exit(error.class.exit_code());
        }
    };

    match f017_runner::execute(config) {
        Ok(evidence) => {
            println!(
                "f017-glm52-runner completed: mode={} result={:?} progress={}",
                evidence.input.mode,
                evidence.result.classification,
                evidence.execution.progress_state
            );
        }
        Err(error) => {
            eprintln!("f017-glm52-runner failed: {error}");
            std::process::exit(error.class.exit_code());
        }
    }
}
