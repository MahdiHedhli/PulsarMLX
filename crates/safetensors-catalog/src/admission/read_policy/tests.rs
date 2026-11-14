use super::*;
use std::{fs, os::fd::AsRawFd, os::unix::fs::symlink};
struct Temp(std::path::PathBuf);
impl Drop for Temp {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}
fn fixture() -> (Temp, RootDirectory, File) {
    static NEXT: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
    let path = std::env::temp_dir().join(format!(
        "policy-catalog-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
    ));
    fs::create_dir(&path).unwrap();
    fs::write(path.join("part"), b"synthetic").unwrap();
    let root = RootDirectory::open(&path).unwrap();
    let old = root.open_file("part").unwrap().file;
    (Temp(path), root, old)
}
fn mock(arg: i32, ret: i32) -> Setter {
    Setter {
        command: "mock-F_NOCACHE",
        number: -1,
        argument: arg,
        returned: ret,
        errno: (ret < 0).then_some(libc::EINTR),
    }
}

#[test]
fn fresh_open_receives_one_setter_and_preserves_interruption_or_mutation() {
    let (dir, root, old) = fixture();
    for (p, ret, mutate) in [
        (Policy::BufferedRequested, 0, false),
        (Policy::NoCacheRequested, 0, false),
        (Policy::NoCacheRequested, -1, false),
        (Policy::BufferedRequested, 0, true),
    ] {
        let mut calls = 0;
        let r = FixedDescriptor::open_with(&root, "part", &old, p, |f, arg| {
            assert_ne!(f.as_raw_fd(), old.as_raw_fd());
            assert_eq!(arg, p.argument());
            calls += 1;
            if mutate {
                fs::write(dir.0.join("part"), b"changed length").unwrap();
            }
            mock(arg, ret)
        });
        assert_eq!(calls, 1);
        let s = if mutate || ret < 0 {
            let fail = r.err().unwrap();
            assert_eq!(
                fail.reason,
                if mutate { "MUTATION" } else { "POLICY_SETTER" }
            );
            fail.observation
        } else {
            let f = r.unwrap();
            f.check().unwrap();
            let mut bytes = [0; 9];
            f.read_exact_at(&mut bytes, 0).unwrap();
            assert_eq!(&bytes, b"synthetic");
            f.setup()
        };
        assert!(s.fresh_owned);
        assert_eq!(s.matched, Some(true));
        assert_eq!(s.original_stamp, s.fresh_stamp);
        assert_eq!(s.setter.unwrap().returned, ret);
        assert_eq!(s.setter.unwrap().errno, (ret < 0).then_some(libc::EINTR));
    }
}
#[test]
fn names_and_complete_file_identity_precede_configuration() {
    let (dir, root, old) = fixture();
    fs::write(dir.0.join("other"), b"synthetic").unwrap();
    symlink("part", dir.0.join("link")).unwrap();
    for n in [
        "other", "missing", "link", "../part", "/part", ".", "..", "",
    ] {
        let err = FixedDescriptor::open_with(&root, n, &old, Policy::NoCacheRequested, |_, _| {
            panic!("unexpected setter")
        })
        .err()
        .unwrap();
        assert!(err.observation.setter.is_none());
        assert_eq!(
            err.observation.matched,
            if n == "other" { Some(false) } else { None }
        );
    }
    fs::rename(dir.0.join("part"), dir.0.join("original")).unwrap();
    fs::write(dir.0.join("part"), b"synthetic").unwrap();
    assert_eq!(
        FixedDescriptor::open_with(
            &root,
            "part",
            &old,
            Policy::NoCacheRequested,
            |_, _| panic!()
        )
        .err()
        .unwrap()
        .reason,
        "IDENTITY"
    );
    let stamp = Stamp::read(&old).unwrap();
    for i in 0..7 {
        let mut b = stamp;
        match i {
            0 => b.dev ^= 1,
            1 => b.ino ^= 1,
            2 => b.len ^= 1,
            3 => b.modified[0] ^= 1,
            4 => b.modified[1] ^= 1,
            5 => b.changed[0] ^= 1,
            _ => b.changed[1] ^= 1,
        };
        assert_ne!(b, stamp);
        assert_ne!(b.digest(), stamp.digest());
    }
}
