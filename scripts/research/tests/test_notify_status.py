"""Offline checks for explicit notification configuration; never sends a request."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "notify_status.sh"

class NotificationConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.args = self.root / "args"
        self.body = self.root / "body"
        curl = self.root / "curl"
        curl.write_text("#!/bin/bash\nprintf '%s\\0' \"$@\" > \"$CAPTURE_ARGS\"\n/bin/cat > \"$CAPTURE_BODY\"\nexit \"${FAKE_CURL_EXIT:-0}\"\n")
        curl.chmod(0o700)
        self.env = dict(os.environ)
        self.env.pop("PULSAR_NTFY_URL", None)
        self.env.update(PATH=str(self.root) + os.pathsep + "/usr/bin:/bin", CAPTURE_ARGS=str(self.args), CAPTURE_BODY=str(self.body))

    def run_script(self, *args):
        return subprocess.run(["/bin/bash", str(SCRIPT), *args], env=self.env, capture_output=True, timeout=5)

    def test_missing_destination_never_calls_curl(self):
        self.assertEqual(self.run_script().returncode, 2)
        self.assertFalse(self.args.exists())

    def test_non_https_destination_never_calls_curl(self):
        self.env["PULSAR_NTFY_URL"] = "http://notifications.invalid/topic"
        self.assertEqual(self.run_script().returncode, 2)
        self.assertFalse(self.args.exists())

    def test_topic_path_required(self):
        self.env["PULSAR_NTFY_URL"] = "https://notifications.invalid"
        self.assertEqual(self.run_script().returncode, 2)
        self.assertFalse(self.args.exists())

    def test_destination_newline_rejected(self):
        self.env["PULSAR_NTFY_URL"] = "https://notifications.invalid/topic\nextra"
        self.assertEqual(self.run_script().returncode, 2)
        self.assertFalse(self.args.exists())

    def test_header_newline_rejected(self):
        self.env["PULSAR_NTFY_URL"] = "https://notifications.invalid/topic"
        self.assertEqual(self.run_script("title\nextra", "body").returncode, 2)
        self.assertFalse(self.args.exists())

    def test_explicit_url_tls_bounds_and_literal_body(self):
        self.env["PULSAR_NTFY_URL"] = "https://notifications.invalid/topic"
        result = self.run_script("test", "@literal-body\nsecond line")
        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.args.read_bytes().split(b"\0")[:-1]
        self.assertEqual(args[0], b"-q")
        for option, value in [(b"--proto", b"=https"), (b"--connect-timeout", b"5"), (b"--max-time", b"12"), (b"--data-binary", b"@-"), (b"--url", self.env["PULSAR_NTFY_URL"].encode())]:
            self.assertEqual(args[args.index(option) + 1], value)
        self.assertIn(b"--tlsv1.2", args)
        self.assertNotIn(b"--insecure", args)
        self.assertEqual(self.body.read_bytes(), b"@literal-body\nsecond line")
        self.assertNotIn(self.env["PULSAR_NTFY_URL"].encode(), result.stdout + result.stderr)

    def test_transport_failure_is_not_success(self):
        self.env["PULSAR_NTFY_URL"] = "https://notifications.invalid/topic"
        self.env["FAKE_CURL_EXIT"] = "22"
        result = self.run_script()
        self.assertEqual(result.returncode, 22)
        self.assertNotIn(b"completed", result.stdout)

if __name__ == "__main__":
    unittest.main()
