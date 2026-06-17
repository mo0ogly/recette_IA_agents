"""Surface projection: map a run's hook (ProxyTrace) + wire (WireFlow) views onto
the discovery probe observation surfaces. Pure, deterministic (I4)."""

from __future__ import annotations

import unittest

from recette.surface.surfaces import (
    HOOK_SURFACES,
    ObservationSurface,
    project_surfaces,
)

# One mediated call (hook view) AND its wire flow (network view): a normal agent.
TRACES = [{"action_type": "open_pr", "resource": "acme/web#42"}]
FLOWS = [
    {
        "seq": 0,
        "method": "POST",
        "host": "api.github.com",
        "port": 443,
        "path": "/repos/acme/web/pulls",
    }
]
# A ghost: wire egress to a DB, with NO matching mediated trace.
GHOST_FLOWS = [
    {"seq": 0, "method": "POST", "host": "shadow-db.acme.internal", "port": 5432, "path": "/write"}
]


class TestProjectSurfaces(unittest.TestCase):
    def test_hook_surfaces_see_the_mediated_call(self) -> None:
        surfaces = project_surfaces(proxy_traces=TRACES, wire_flows=FLOWS)
        for s in HOOK_SURFACES:
            self.assertEqual(surfaces[s].visible, ("open_pr:acme/web#42",))

    def test_wire_surface_sees_the_network_flow(self) -> None:
        surfaces = project_surfaces(proxy_traces=TRACES, wire_flows=FLOWS)
        self.assertEqual(
            surfaces[ObservationSurface.EBPF_WIRE].visible,
            ("POST api.github.com:443/repos/acme/web/pulls",),
        )

    def test_ghost_is_invisible_on_hook_visible_on_wire(self) -> None:
        surfaces = project_surfaces(proxy_traces=[], wire_flows=GHOST_FLOWS)
        for s in HOOK_SURFACES:
            self.assertEqual(surfaces[s].visible, ())  # SDK bypassed -> hook blind
        self.assertEqual(
            surfaces[ObservationSurface.EBPF_WIRE].visible,
            ("POST shadow-db.acme.internal:5432/write",),
        )

    def test_projection_is_deterministic_and_sorted(self) -> None:
        flows = [
            {"seq": 1, "method": "GET", "host": "b.com", "port": 443, "path": "/2"},
            {"seq": 0, "method": "GET", "host": "a.com", "port": 443, "path": "/1"},
        ]
        a = project_surfaces(proxy_traces=[], wire_flows=flows)
        b = project_surfaces(proxy_traces=[], wire_flows=flows)
        self.assertEqual(a, b)
        # sorted by the stable visible string, not input order
        self.assertEqual(
            a[ObservationSurface.EBPF_WIRE].visible,
            ("GET a.com:443/1", "GET b.com:443/2"),
        )


if __name__ == "__main__":
    unittest.main()
