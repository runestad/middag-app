"""Exercise real HTTP requests with a measured, in-memory Supabase transport."""
import copy
import http.client
import json
import threading
import unittest
import urllib.parse
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from api import plan


class QuietHandler(plan.handler):
    def log_message(self, *args):
        pass


class PlanEgressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.row = {
            "updated_at": "2026-10-31T21:00:00.000001+00:00",
            "data": {"updatedAt": "client-version", "shoppingItems": [],
                     "meta": {"preserved": "x" * 520000}},
        }
        self.reads = []
        self.bytes_received = 0
        self.after_probe = None
        self.transport = patch.object(plan, "supabase_request", side_effect=self.supabase)
        self.transport.start()
        self.addCleanup(self.transport.stop)

    def supabase(self, method, table, query=None, **kwargs):
        self.assertEqual((method, table), ("GET", "app_state"))
        params = urllib.parse.parse_qs(query)
        self.assertEqual(params["key"], [f"eq.plan:{plan.APP_ID}"])
        self.assertEqual(params["limit"], ["1"])
        fields = params["select"][0].split(",")
        self.reads.append(fields)
        result = [{k: self.row.get(k) for k in fields}] if self.row else []
        result = copy.deepcopy(result)
        self.bytes_received += len(json.dumps(result).encode())
        if fields == ["updated_at"] and self.after_probe:
            self.after_probe()
        return result

    def get(self, etag=None, since=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        headers = {"If-None-Match": etag} if etag else {}
        try:
            path = "/api/plan" + ("?" + urllib.parse.urlencode({"since": since}) if since else "")
            connection.request("GET", path, headers=headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_initial_load_preserves_entire_document(self):
        status, headers, body = self.get()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["plan"], self.row["data"])
        self.assertEqual(self.reads, [["data", "updated_at"]])
        self.assertTrue(headers["ETag"].startswith('W/"plan-v2-'))

    def test_unchanged_poll_reads_under_100_bytes_from_supabase(self):
        _, headers, _ = self.get()
        self.reads.clear()
        self.bytes_received = 0
        status, response_headers, body = self.get(headers["ETag"])
        self.assertEqual(status, 304)
        self.assertEqual(body, b"")
        self.assertEqual(response_headers["ETag"], headers["ETag"])
        self.assertEqual(self.reads, [["updated_at"]])
        self.assertLess(self.bytes_received, 100)

    def test_compressed_and_list_validators_avoid_full_read(self):
        _, headers, _ = self.get()
        etag = headers["ETag"]
        for validator in (etag, etag[2:], '"other", ' + etag, "*"):
            with self.subTest(validator=validator):
                self.reads.clear()
                self.assertEqual(self.get(validator)[0], 304)
                self.assertEqual(self.reads, [["updated_at"]])

    def test_explicit_revision_works_without_any_http_validator_headers(self):
        _, _, initial = self.get()
        revision = json.loads(initial)["revision"]
        self.reads.clear()
        self.bytes_received = 0
        status, _, body = self.get(since=revision)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"ok": True, "unchanged": True, "revision": revision})
        self.assertLess(len(body), 200)
        self.assertLess(self.bytes_received, 100)
        self.assertEqual(self.reads, [["updated_at"]])

    def test_explicit_revision_detects_another_device_update(self):
        _, _, initial = self.get()
        revision = json.loads(initial)["revision"]
        self.row["updated_at"] = "2026-10-31T21:03:00.000004+00:00"
        self.row["data"]["shoppingItems"] = [{"id": "new-item"}]
        status, _, body = self.get(since=revision)
        result = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(result["plan"], self.row["data"])
        self.assertNotEqual(result["revision"], revision)
        self.assertNotIn("unchanged", result)

    def test_other_phone_update_is_returned_even_with_same_client_timestamp(self):
        _, headers, _ = self.get()
        self.row["updated_at"] = "2026-10-31T21:01:00.000002+00:00"
        self.row["data"]["shoppingItems"] = [{"id": "milk", "text": "Melk"}]
        self.reads.clear()
        status, changed_headers, body = self.get(headers["ETag"])
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["plan"], self.row["data"])
        self.assertNotEqual(headers["ETag"], changed_headers["ETag"])
        self.assertEqual(self.reads, [["updated_at"], ["data", "updated_at"]])

    def test_update_between_probe_and_fetch_uses_fetched_snapshot_validator(self):
        def save_between_reads():
            self.row["updated_at"] = "2026-10-31T21:02:00.000003+00:00"
            self.row["data"]["shoppingItems"] = [{"id": "new", "text": "Brød"}]
        self.after_probe = save_between_reads
        status, headers, body = self.get('"older-version"')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["plan"], self.row["data"])
        self.after_probe = None
        self.reads.clear()
        self.assertEqual(self.get(headers["ETag"])[0], 304)
        self.assertEqual(self.reads, [["updated_at"]])

    def test_missing_revision_falls_back_without_hiding_changes(self):
        self.row.pop("updated_at")
        _, headers, _ = self.get()
        self.row["data"]["shoppingItems"] = [{"id": "changed"}]
        status, _, body = self.get(headers["ETag"])
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["plan"], self.row["data"])

    def test_missing_row_returns_empty_plan_instead_of_stale_304(self):
        _, headers, _ = self.get()
        self.row = None
        status, _, body = self.get(headers["ETag"])
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["plan"], {})

    def test_database_error_does_not_claim_unchanged(self):
        with patch.object(plan, "supabase_request", side_effect=RuntimeError("offline")):
            status, _, body = self.get('"some-validator"')
        self.assertEqual(status, 500)
        self.assertFalse(json.loads(body)["ok"])


class PlanSaveEgressTests(unittest.TestCase):
    def test_update_returns_only_key_without_losing_merged_data(self):
        stored = {"updatedAt": "old", "shoppingItems": [{"id": "a", "updatedAt": "1"}]}
        incoming = {"updatedAt": "new", "shoppingItems": [{"id": "b", "updatedAt": "2"}]}
        with patch.object(plan, "supabase_request", side_effect=[[{"data": stored}], [{"key": "plan:test"}]]) as request:
            result = plan._persist_plan_with_retry("plan:test", incoming)
        self.assertEqual({item["id"] for item in result["shoppingItems"]}, {"a", "b"})
        params = urllib.parse.parse_qs(request.call_args.kwargs["query"])
        self.assertEqual(params["select"], ["key"])
        self.assertEqual(params["data->>updatedAt"], ["eq.old"])

    def test_first_save_returns_only_key(self):
        incoming = {"updatedAt": "new", "shoppingItems": []}
        with patch.object(plan, "supabase_request", side_effect=[[], [{"key": "plan:test"}]]) as request:
            self.assertEqual(plan._persist_plan_with_retry("plan:test", incoming), incoming)
        self.assertEqual(request.call_args.args[0], "POST")
        self.assertEqual(request.call_args.kwargs["query"], "select=key")


if __name__ == "__main__":
    unittest.main()
