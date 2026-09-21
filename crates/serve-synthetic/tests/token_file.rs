#[cfg(unix)]
#[test]
fn token_file_requires_regular_0600_input() {
    use pulsar_serve_synthetic::read_token_file;
    use std::fs::{self, OpenOptions};
    use std::io::Write;
    use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};

    let root = std::env::temp_dir().join(format!(
        "pulsar-synthetic-token-test-{}-{}",
        std::process::id(),
        std::thread::current().name().unwrap_or("test")
    ));
    fs::create_dir(&root).expect("create root");
    fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).expect("root mode");
    let token_path = root.join("token");
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&token_path)
        .expect("create token");
    file.write_all(format!("test-token-{}-runtime", std::process::id()).as_bytes())
        .expect("write token");
    drop(file);
    assert!(read_token_file(&token_path).is_ok());

    fs::set_permissions(&token_path, fs::Permissions::from_mode(0o644)).expect("bad mode");
    assert_eq!(
        read_token_file(&token_path).unwrap_err(),
        "token file permissions must be 0600"
    );
    fs::set_permissions(&token_path, fs::Permissions::from_mode(0o600)).expect("restore mode");
    let link = root.join("link");
    std::os::unix::fs::symlink(&token_path, &link).expect("symlink");
    assert_eq!(
        read_token_file(&link).unwrap_err(),
        "token file must be a regular non-symlink file"
    );

    fs::remove_file(link).expect("remove link");
    fs::remove_file(token_path).expect("remove token");
    fs::remove_dir(root).expect("remove root");
}
