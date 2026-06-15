"""config_store: fqdn/aliases are optional, syntactic, and collision-free."""

from __future__ import annotations

import unittest

from recette.api.config_store import validate_server_netname


class TestServerNetnameValidation(unittest.TestCase):
    def test_accepts_server_without_fqdn(self) -> None:
        validate_server_netname({"id": "a", "mode": "mock_local", "port": 9101}, others=[])

    def test_accepts_valid_fqdn_and_aliases(self) -> None:
        validate_server_netname(
            {
                "id": "a",
                "mode": "mock_local",
                "port": 9101,
                "fqdn": "api.github.com",
                "aliases": ["gh.lab.internal"],
            },
            others=[],
        )

    def test_rejects_duplicate_fqdn(self) -> None:
        existing = [{"id": "a", "fqdn": "api.github.com"}]
        with self.assertRaises(ValueError):
            validate_server_netname(
                {"id": "b", "mode": "mock_local", "port": 9102, "fqdn": "api.github.com"},
                others=existing,
            )

    def test_rejects_alias_colliding_with_other_fqdn(self) -> None:
        existing = [{"id": "a", "fqdn": "api.github.com"}]
        with self.assertRaises(ValueError):
            validate_server_netname(
                {"id": "b", "mode": "mock_local", "port": 9102, "aliases": ["api.github.com"]},
                others=existing,
            )

    def test_rejects_malformed_fqdn(self) -> None:
        with self.assertRaises(ValueError):
            validate_server_netname(
                {"id": "a", "mode": "mock_local", "port": 9101, "fqdn": "not a host!"},
                others=[],
            )

    def test_same_server_id_does_not_collide_with_itself(self) -> None:
        existing = [{"id": "a", "fqdn": "api.github.com"}]
        # updating server "a" keeping its own fqdn must NOT raise
        validate_server_netname(
            {"id": "a", "mode": "mock_local", "port": 9101, "fqdn": "api.github.com"},
            others=existing,
        )

    def test_rejects_non_list_aliases(self) -> None:
        with self.assertRaises(ValueError):
            validate_server_netname(
                {"id": "a", "mode": "mock_local", "port": 9101, "aliases": "gh.lab.internal"},
                others=[],
            )

    def test_other_server_with_malformed_aliases_is_ignored(self) -> None:
        # a different server with a non-list aliases must not poison collision detection
        existing = [{"id": "a", "aliases": "api.github.com"}]
        validate_server_netname(
            {"id": "b", "mode": "mock_local", "port": 9102, "fqdn": "api.github.com"},
            others=existing,
        )


if __name__ == "__main__":
    unittest.main()
