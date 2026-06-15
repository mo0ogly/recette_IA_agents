"""netname resolver: pure name -> server entry, fqdn/alias/id, containment (I4)."""

from __future__ import annotations

import unittest

from recette.platform.netname.resolver import ResolutionDenied, resolve_name

SERVERS = [
    {
        "id": "gh-mock",
        "system": "github",
        "mode": "mock_local",
        "port": 9101,
        "fqdn": "api.github.com",
        "aliases": ["github.lab.internal"],
    },
    {"id": "finance-mock", "system": "finance", "mode": "mock_local", "port": 9103},
]


class TestResolveName(unittest.TestCase):
    def test_resolves_by_fqdn(self) -> None:
        self.assertEqual(resolve_name("api.github.com", SERVERS, containment=True)["id"], "gh-mock")

    def test_resolves_by_alias(self) -> None:
        self.assertEqual(
            resolve_name("github.lab.internal", SERVERS, containment=True)["id"], "gh-mock"
        )

    def test_resolves_by_id_when_no_fqdn(self) -> None:
        self.assertEqual(
            resolve_name("finance-mock", SERVERS, containment=True)["id"], "finance-mock"
        )

    def test_unknown_name_denied_when_containment_on(self) -> None:
        with self.assertRaises(ResolutionDenied) as ctx:
            resolve_name("evil.com", SERVERS, containment=True)
        self.assertEqual(ctx.exception.name, "evil.com")

    def test_unknown_name_falls_back_to_id_when_containment_off(self) -> None:
        self.assertIsNone(resolve_name("evil.com", SERVERS, containment=False))

    def test_resolution_is_deterministic(self) -> None:
        a = resolve_name("api.github.com", SERVERS, containment=True)
        b = resolve_name("api.github.com", SERVERS, containment=True)
        self.assertEqual(a, b)


class TestResolveReplay(unittest.TestCase):
    """I4: same (name, table) yields the same result across replays, incl. denial."""

    def test_denied_name_is_stable_across_replays(self) -> None:
        for _ in range(3):
            with self.assertRaises(ResolutionDenied) as ctx:
                resolve_name("nope.example", SERVERS, containment=True)
            self.assertEqual(ctx.exception.name, "nope.example")

    def test_alias_resolves_to_same_entry_as_fqdn(self) -> None:
        self.assertEqual(
            resolve_name("api.github.com", SERVERS, containment=True),
            resolve_name("github.lab.internal", SERVERS, containment=True),
        )


if __name__ == "__main__":
    unittest.main()
