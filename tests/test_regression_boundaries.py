"""Additional policy-boundary regression tests for the local control plane."""
import tempfile
import unittest

from control import ControlPlane, MemoryBackend, PolicyError, review_proposal


class PolicyBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db_path = self.directory.name + "/control.db"
        self.clock = [1000.0]
        self.backend = MemoryBackend()
        self.plane = ControlPlane(
            self.db_path,
            self.backend,
            principal="lab-agent",
            role="developer",
            clock=lambda: self.clock[0],
        )

    def test_missing_or_blank_principal_is_denied(self):
        for principal in ("", "  ", None):
            with self.subTest(principal=principal), self.assertRaises(PolicyError):
                ControlPlane(self.db_path, self.backend, principal=principal)

    def test_unsupported_role_is_denied(self):
        with self.assertRaises(PolicyError):
            ControlPlane(self.db_path, self.backend, role="superuser")

    def test_monitoring_role_cannot_propose_deletion(self):
        observer = ControlPlane(self.db_path, self.backend, role="monitoring")
        with self.assertRaises(PolicyError):
            observer.propose("delete", "lab:test")

    def test_utf8_size_limit_applies_to_bytes(self):
        with self.assertRaises(PolicyError):
            self.plane.propose("set", "lab:test", "😀" * 257)
        proposal = self.plane.propose("set", "lab:test", "😀" * 256)
        self.assertEqual(proposal["value_bytes"], 1024)

    def test_whitespace_only_reviewer_is_denied(self):
        proposal_id = self.plane.propose("set", "lab:test", "value")["proposal_id"]
        with self.assertRaises(PolicyError):
            review_proposal(self.db_path, proposal_id, " ", approve=True)

    def test_review_without_approval_does_not_execute(self):
        proposal_id = self.plane.propose("set", "lab:test", "value")["proposal_id"]
        review = review_proposal(self.db_path, proposal_id, "operator", clock=lambda: self.clock[0])
        self.assertEqual(review["state"], "pending")
        with self.assertRaises(PolicyError):
            self.plane.execute(proposal_id)
        self.assertIsNone(self.backend.get("lab:test"))

    def test_proposal_expiry_blocks_approval(self):
        proposal_id = self.plane.propose("set", "lab:test", "value")["proposal_id"]
        self.clock[0] += 300
        with self.assertRaises(PolicyError):
            review_proposal(self.db_path, proposal_id, "operator", approve=True, clock=lambda: self.clock[0])

    def test_audit_entries_are_scoped_to_principal(self):
        self.plane.propose("set", "lab:first", "value")
        other = ControlPlane(self.db_path, self.backend, principal="other", role="developer", clock=lambda: self.clock[0])
        other.propose("set", "lab:second", "value")
        self.assertEqual(len(self.plane.audit()), 1)
        self.assertEqual(len(other.audit()), 1)


if __name__ == "__main__":
    unittest.main()
