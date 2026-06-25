import unittest

from recette.behavior.links import Link, load_links


class TestAgentLinks(unittest.TestCase):
    def test_load_links_returns_parsed_entries(self):
        links = load_links()
        self.assertTrue(links, "agent_links.json must declare at least one link")
        first = links[0]
        self.assertIsInstance(first, Link)
        self.assertTrue(first.agent_id)
        # every link names at least a discovery subject OR a runtime subject
        for ln in links:
            self.assertTrue(ln.discovery_subject or ln.runtime_subject)

    def test_links_have_unique_agent_ids(self):
        ids = [ln.agent_id for ln in load_links()]
        self.assertEqual(len(ids), len(set(ids)), "agent_id must be unique")
