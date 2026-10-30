import io
import unittest
from unittest.mock import patch
from api import plan

class TransferTests(unittest.TestCase):
    def request(self, tag=None, data=None):
        h = object.__new__(plan.handler)
        h.headers = {'If-None-Match': tag} if tag else {}
        h.wfile = io.BytesIO()
        h.response_headers = {}
        h.send_response = lambda status: setattr(h, 'status', status)
        h.send_header = lambda key, value: h.response_headers.update({key: value})
        h.end_headers = lambda: None
        with patch.object(plan, 'supabase_request', return_value=[{'data': data or {'updatedAt':'one','items':{}}}]):
            h.do_GET()
        return h

    def test_unchanged_has_no_body_and_changed_is_sent(self):
        first = self.request()
        self.assertEqual(first.status, 200)
        self.assertGreater(len(first.wfile.getvalue()), 0)
        second = self.request(first.response_headers['ETag'])
        self.assertEqual(second.status, 304)
        self.assertEqual(second.wfile.getvalue(), b'')
        third = self.request(first.response_headers['ETag'], {'updatedAt':'two'})
        self.assertEqual(third.status, 200)
        self.assertNotEqual(first.response_headers['ETag'], third.response_headers['ETag'])
