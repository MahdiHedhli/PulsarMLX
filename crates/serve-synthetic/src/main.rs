use pulsar_serve_synthetic::{bind_loopback, read_token_file, serve, AppState};
use std::path::PathBuf;

#[tokio::main]
async fn main() {
    if let Err(error) = run().await {
        eprintln!("pulsar-serve-synthetic: {error}");
        std::process::exit(1);
    }
}

async fn run() -> Result<(), String> {
    let mut token_file: Option<PathBuf> = None;
    let mut port = 0_u16;
    let mut args = std::env::args_os().skip(1);
    while let Some(arg) = args.next() {
        match arg.to_str() {
            Some("--token-file") => {
                token_file = Some(PathBuf::from(
                    args.next().ok_or("--token-file requires a path")?,
                ))
            }
            Some("--port") => {
                let value = args.next().ok_or("--port requires a value")?;
                port = value
                    .to_str()
                    .ok_or("port must be UTF-8")?
                    .parse()
                    .map_err(|_| "invalid port")?;
            }
            Some("--help") => {
                println!("Usage: pulsar-serve-synthetic --token-file PATH [--port PORT]");
                return Ok(());
            }
            _ => return Err("unknown argument".into()),
        }
    }
    let token_path = token_file.ok_or("missing --token-file")?;
    let token = read_token_file(&token_path)?;
    let state = AppState::new(token).map_err(str::to_owned)?;
    let listener = bind_loopback(port)
        .await
        .map_err(|_| "failed to bind IPv4 loopback")?;
    let address = listener
        .local_addr()
        .map_err(|_| "failed to read listener address")?;
    eprintln!("pulsar-serve-synthetic: listening on {address}");
    serve(listener, state, async {
        let _ = tokio::signal::ctrl_c().await;
    })
    .await
    .map_err(|_| "server failed".to_owned())
}
