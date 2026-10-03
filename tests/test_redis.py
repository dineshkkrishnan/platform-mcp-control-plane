import os
import secrets
import tempfile
import unittest
from control import ControlPlane,RedisBackend,PolicyError,review_proposal

@unittest.skipUnless(os.environ.get('LAB_TEST_REDIS_URL'),'Set LAB_TEST_REDIS_URL for real Redis integration')
class RedisIntegrationTests(unittest.TestCase):
    def test_atomic_set_stale_and_delete(self):
        backend=RedisBackend(os.environ['LAB_TEST_REDIS_URL']);self.assertTrue(backend.ping())
        key='lab:integration:'+secrets.token_hex(6)
        try:
            with tempfile.TemporaryDirectory() as directory:
                plane=ControlPlane(directory+'/control.db',backend,role='admin')
                p=plane.propose('set',key,'demo')['proposal_id'];review_proposal(plane.db_path,p,'operator',True)
                self.assertTrue(plane.execute(p)['verified']);self.assertEqual(backend.get(key),'demo')
                stale=plane.propose('set',key,'next')['proposal_id'];review_proposal(plane.db_path,stale,'operator',True)
                backend.client.set(key,'out-of-band')
                with self.assertRaises(PolicyError):plane.execute(stale)
                self.assertEqual(backend.get(key),'out-of-band')
                p=plane.propose('delete',key)['proposal_id'];review_proposal(plane.db_path,p,'operator',True)
                self.assertTrue(plane.execute(p)['verified']);self.assertIsNone(backend.get(key))
        finally:backend.client.delete(key)
