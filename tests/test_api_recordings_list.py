"""Contract test for the proxy-launcher recordings list.

The console proxy launcher offers a "replay a recording" option; it needs a
plain JSON array of available recordings, each carrying at least an ``id``.
The pre-existing ``GET /recordings`` returns a ``{"recordings": [...]}``
envelope (consumed by the campaigns page) and keys items as ``recording_id``,
so the launcher uses the lean ``GET /recordings/list`` route which returns a
bare list keyed by ``id``. Both routes read the SAME recording store (I1
read-only, I4 pure given the store).
"""

import unittest

from fastapi.testclient import TestClient

from recette.api.app import create_app


class RecordingsListTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_recordings_list_returns_list(self) -> None:
        r = self.client.get("/recordings/list")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

    def test_each_item_has_id(self) -> None:
        r = self.client.get("/recordings/list")
        for item in r.json():
            self.assertIn("id", item)


if __name__ == "__main__":
    unittest.main()
