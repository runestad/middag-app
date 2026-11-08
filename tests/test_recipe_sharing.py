import hashlib
import http.client
import importlib
import json
import os
import pathlib
import threading
import unittest
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from api import health, recipes
from api._access import OwnerRequestHandler, owner_cookie


@contextmanager
def serve(handler):
    class Quiet(handler):
        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Quiet) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_address
        finally:
            server.shutdown()
            thread.join()


def call(address, method, path, headers=None, body=None):
    conn = http.client.HTTPConnection(*address, timeout=5)
    try:
        conn.request(method, path, body, headers or {})
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), json.loads(response.read())
    finally:
        conn.close()


class SharingTests(unittest.TestCase):
    def setUp(self):
        self.key = "a" * 64
        access = patch.dict(os.environ, {"SUPABASE_SERVICE_ROLE_KEY": "local-test-signing-key",
                            "SULT_OWNER_LINK_SHA256": hashlib.sha256(self.key.encode()).hexdigest()})
        access.start()
        self.addCleanup(access.stop)
        self.owner = {"Cookie": owner_cookie().split(";")[0]}

    def test_activation_and_owner_boundary(self):
        with serve(health.handler) as addr:
            self.assertEqual(call(addr, "GET", "/api/health")[0], 401)
            headers = {"Content-Type": "application/json"}
            for key, status in [("wrong", 401), (self.key, 200)]:
                response, out, _ = call(addr, "POST", "/api/health", headers, json.dumps({"ownerKey": key}))
                self.assertEqual(response, status)
            for flag in ("HttpOnly", "Secure", "SameSite=Lax"):
                self.assertIn(flag, out["Set-Cookie"])
            self.assertEqual(call(addr, "GET", "/api/health", {"Cookie": out["Set-Cookie"].split(";")[0]})[0], 200)
        for p in pathlib.Path("api").glob("*.py"):
            module = importlib.import_module("api." + p.stem)
            if hasattr(module, "handler"):
                self.assertTrue(issubclass(module.handler, OwnerRequestHandler), p.name)

    def test_guest_scopes_reads_and_denied_mutations(self):
        r = {"id":"1", "name":"Ris", "category":"Middag", "source":"Egen",
             "instructions":"1. Kok risen", "ingredientsText":"2 dl ris", "servings":2,
             "link":"https://example.com/ris", "caption":"PRIVATE", "comment":"PRIVATE"}
        with serve(recipes.handler) as addr, patch.object(recipes, "recipe_exists", return_value=True), \
             patch.object(recipes, "recipe_row", return_value=r) as lookup, \
             patch.object(recipes, "library_rows", return_value=[r]) as library:
            def issue(scope, id_query=""):
                status, _, data = call(addr, "GET", "/api/recipes?shareLink=" + scope + id_query, self.owner)
                self.assertEqual(status, 200)
                return {"X-Sult-Share": parse_qs(urlsplit(data["path"]).fragment)["key"][0]}
            one, book = issue("recipe", "&id=1"), issue("book")
            self.assertEqual(call(addr, "GET", "/api/recipes?shared=recipe&id=2", one)[0], 403)
            self.assertEqual(call(addr, "GET", "/api/recipes?shared=book", one)[0], 403)
            self.assertEqual(call(addr, "GET", "/api/recipes?sharedPhoto=1&proof=" + one["X-Sult-Share"])[0], 403)
            for method, path in [("GET", "?shareLink=book"), ("GET","?backup=1"), ("GET","?imagePath=1"),
                                 ("POST","?shared=book"), ("DELETE","?shared=recipe&id=1")]:
                self.assertEqual(call(addr, method, "/api/recipes" + path, one)[0], 401)
            lookup.assert_not_called()
            library.assert_not_called()
            for mode, headers in [("recipe", one), ("book", book)]:
                status, _, data = call(addr, "GET", "/api/recipes?shared=" + mode + "&id=1", headers)
                self.assertEqual(status, 200)
                self.assertEqual(data["recipe"]["ingredients"], ["2 dl ris"])
                self.assertEqual(data["recipe"]["steps"], ["1. Kok risen"])
                self.assertNotIn("PRIVATE", str(data))
            status, _, data = call(addr, "GET", "/api/recipes?shared=book", book)
            self.assertEqual(status, 200)
            self.assertEqual(data["recipes"][0]["category"], "Middag")
            self.assertNotIn("ingredients", data["recipes"][0])
            lookup.return_value = None
            self.assertEqual(call(addr, "GET", "/api/recipes?shared=recipe&id=1", one)[0], 404)
            self.assertEqual(call(addr, "POST", "/api/recipes", {**self.owner, "Sec-Fetch-Site":"cross-site"})[0], 403)


if __name__ == "__main__":
    unittest.main()
