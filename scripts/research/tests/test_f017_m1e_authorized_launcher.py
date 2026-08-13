import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LAUNCHER_PATH = ROOT / "scripts/research/run_f017_m1e_authorized.py"
SPEC = importlib.util.spec_from_file_location("m1e_authorized_launcher", LAUNCHER_PATH)
LAUNCHER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(LAUNCHER)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AuthorizedLauncherTests(unittest.TestCase):
    def test_reviewed_native_loader_environment_is_constructed_from_bound_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prefix = root / "native"
            library = prefix / "lib"
            library.mkdir(parents=True)
            mlx = library / "libmlx.dylib"
            mlxc = library / "libmlxc.dylib"
            mlx.write_bytes(b"mlx")
            mlxc.write_bytes(b"mlxc")
            manifest = root / "environment.json"
            manifest.write_text(json.dumps({
                "pinned_installation": {
                    "prefix": str(prefix),
                    "mlx": {"library_sha256": digest(mlx)},
                    "mlx_c": {"library_sha256": digest(mlxc)},
                }
            }))
            document = {"local_artifacts": {"environment_manifest": {
                "path_kind": "absolute_private_local",
                "path": str(manifest),
                "content_sha256": digest(manifest),
            }}}
            previous = os.environ.get("DYLD_LIBRARY_PATH")
            os.environ["DYLD_LIBRARY_PATH"] = "/unreviewed/override"
            try:
                environment = LAUNCHER.native_loader_environment(document)
            finally:
                if previous is None:
                    os.environ.pop("DYLD_LIBRARY_PATH", None)
                else:
                    os.environ["DYLD_LIBRARY_PATH"] = previous
            self.assertEqual(environment["DYLD_LIBRARY_PATH"], str(library))

    def test_wrong_native_library_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library = root / "native/lib"
            library.mkdir(parents=True)
            (library / "libmlx.dylib").write_bytes(b"mlx")
            (library / "libmlxc.dylib").write_bytes(b"mlxc")
            manifest = root / "environment.json"
            manifest.write_text(json.dumps({
                "pinned_installation": {
                    "prefix": str(library.parent),
                    "mlx": {"library_sha256": "0" * 64},
                    "mlx_c": {"library_sha256": digest(library / "libmlxc.dylib")},
                }
            }))
            document = {"local_artifacts": {"environment_manifest": {
                "path_kind": "absolute_private_local",
                "path": str(manifest),
                "content_sha256": digest(manifest),
            }}}
            with self.assertRaisesRegex(ValueError, "native MLX library identity mismatch"):
                LAUNCHER.native_loader_environment(document)


if __name__ == "__main__":
    unittest.main()
