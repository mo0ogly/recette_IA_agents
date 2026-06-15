"""gitlab domain tests: git-family lab handler, GitLab-flavoured + deterministic."""

from __future__ import annotations

import unittest

from recette.lab.domains import _entities
from recette.lab.domains import gitlab as gitlab_lab
from recette.lab.errors import LabActionError

_CANONICAL = (
    "read_repo",
    "list_repos",
    "open_issue",
    "comment_issue",
    "open_pr",
    "merge_pr",
    "push",
    "manage_webhook",
)


class TestGitlabLabHandler(unittest.TestCase):
    def test_handles_every_canonical_git_action(self) -> None:
        for action_type in _CANONICAL:
            with self.subTest(action_type=action_type):
                response = gitlab_lab.handle(action_type, "group/project", {"k": "v"})
                self.assertIsInstance(response, dict)
                assert response is not None
                self.assertEqual(response["action"], action_type)
                self.assertEqual(response["resource"], "group/project")
                self.assertEqual(len(response["result_id"]), 12)
                self.assertNotEqual(response["status"], "simulated")

    def test_gitlab_flavoured_shapes(self) -> None:
        repo = gitlab_lab.handle("read_repo", "group/project", {})
        assert repo is not None
        self.assertEqual(repo["project"]["path_with_namespace"], "group/project")
        mr = gitlab_lab.handle("open_pr", "group/project", {})
        assert mr is not None
        self.assertEqual(mr["merge_request"]["state"], "opened")
        self.assertIsInstance(mr["merge_request"]["iid"], int)

    def test_handler_is_deterministic(self) -> None:
        for action_type in _CANONICAL:
            with self.subTest(action_type=action_type):
                a = gitlab_lab.handle(action_type, "g/p", {"b": 2, "a": 1})
                b = gitlab_lab.handle(action_type, "g/p", {"b": 2, "a": 1})
                self.assertEqual(a, b)

    def test_result_id_varies_with_resource(self) -> None:
        a = gitlab_lab.handle("read_repo", "g/a", {})
        b = gitlab_lab.handle("read_repo", "g/b", {})
        assert a is not None and b is not None
        self.assertNotEqual(a["result_id"], b["result_id"])

    def test_unknown_action_returns_none(self) -> None:
        self.assertIsNone(gitlab_lab.handle("delete_repository", "g/p", {}))
        self.assertIsNone(gitlab_lab.handle("", "g/p", {}))


class TestGitlabEntityModel(unittest.TestCase):
    """Entity model: a project is a pure function of its path; an ARCHIVED project
    (blocking seed) cannot be pushed to/merged; discovery lists the seed projects.
    Deterministic (I4)."""

    ARCHIVED = "gitlab/project/archived-1"

    def test_push_to_archived_project_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            gitlab_lab.handle("push", self.ARCHIVED, {})
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.code, "project_archived")
        assert ctx.exception.detail is not None
        self.assertTrue(ctx.exception.detail["archived"])

    def test_read_repo_keeps_private_visibility(self) -> None:
        repo = gitlab_lab.handle("read_repo", "group/project", {})
        assert repo is not None
        self.assertEqual(repo["project"]["path_with_namespace"], "group/project")
        self.assertEqual(repo["project"]["visibility"], "private")
        self.assertFalse(repo["project"]["archived"])

    def test_discovery_lists_seed_projects(self) -> None:
        listing = gitlab_lab.handle("read_repo", "", {})
        assert listing is not None
        paths = [p["path_with_namespace"] for p in listing["projects_list"]]
        self.assertEqual(paths, list(_entities.SEED_PROJECTS))

    def test_entity_derivation_is_deterministic(self) -> None:
        self.assertEqual(
            _entities.derive_project("gitlab/project/z"),
            _entities.derive_project("gitlab/project/z"),
        )


if __name__ == "__main__":
    unittest.main()
