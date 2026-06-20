import unittest

from fastapi.testclient import TestClient

from recette.api.app import create_app


class ProxyDebugToggleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_post_debug_flips_state_and_proxy(self) -> None:
        r = self.client.post("/proxy/debug", json={"enabled": True})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["debug_enabled"])
        self.assertTrue(self.client.get("/proxy/debug").json()["debug_enabled"])

        r = self.client.post("/proxy/debug", json={"enabled": False})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["debug_enabled"])
        self.assertFalse(self.client.get("/proxy/debug").json()["debug_enabled"])

    def test_post_debug_rejects_non_bool(self) -> None:
        r = self.client.post("/proxy/debug", json={"enabled": "yes"})
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
