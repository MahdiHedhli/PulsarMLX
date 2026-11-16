"""Pure binding controls: no file publication, local claim, or stage invocation."""
import unittest
import studio017_supervise as s


class GrantBoundary(unittest.TestCase):
    def test_swapped_roles_cannot_share_a_pointer_binding(self):
        run = "0" * 64
        body = b"synthetic binding sample; no execution authority"
        p = dict(commit="1" * 40, path=s.request_name(run, "reference"), sha256=s.sha(body))
        s.pointer_matches_role(p, run, "reference", body)
        with self.assertRaisesRegex(ValueError, "pointer fields"):
            s.pointer_matches_role(p, run, "native", body)
        with self.assertRaisesRegex(ValueError, "pointer fields"):
            s.pointer_matches_role(p, run, "reference", body + b"x")

    def test_both_real_roles_require_external_authority(self):
        for role in ("reference", "native"):
            with self.assertRaisesRegex(ValueError, "independent spend registry"):
                s.require_external_spend_authority(role)
