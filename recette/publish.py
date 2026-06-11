"""Publish a corpus repo tree to a real GitHub repository (developer-facing tool).

Turns `corpus/repos/<slug>/repo/` into a real GitHub repo the colleague's GitHubScanner
can scan. Side-effecting -- so it is dry-run by default and the real creation requires an
explicit `apply=True` / `--apply`.

Safety:
- dry-run by default: computes and returns the plan, touches nothing.
- token from the environment / gh auth, never hardcoded.
- never force-push; refuses to touch a repo it did not just create (existence check).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPO_CORPUS = _REPO_ROOT / "corpus" / "repos"


@dataclass
class PublishPlan:
    slug: str
    owner: str
    repo_name: str
    remote_url: str
    visibility: str
    files: list[str]
    applied: bool = False
    steps: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"publish plan for '{self.slug}':",
            f"  target   : {self.owner}/{self.repo_name} ({self.visibility})",
            f"  remote   : {self.remote_url}",
            f"  files    : {len(self.files)}",
        ]
        lines += [f"    - {f}" for f in self.files]
        lines.append("  steps    :")
        lines += [f"    {i + 1}. {s}" for i, s in enumerate(self.steps)]
        lines.append(f"  applied  : {self.applied}")
        return "\n".join(lines)


def _repo_tree(slug: str, corpus_root: Path) -> Path:
    tree = Path(corpus_root) / slug / "repo"
    if not tree.is_dir():
        raise FileNotFoundError(f"no repo tree at {tree}")
    return tree


def _list_files(tree: Path) -> list[str]:
    return sorted(str(p.relative_to(tree)) for p in tree.rglob("*") if p.is_file())


def build_plan(
    slug: str,
    owner: str,
    *,
    visibility: str = "private",
    corpus_root: Path | str = DEFAULT_REPO_CORPUS,
) -> PublishPlan:
    tree = _repo_tree(slug, Path(corpus_root))
    repo_name = slug
    remote_url = f"https://github.com/{owner}/{repo_name}.git"
    files = _list_files(tree)
    steps = [
        f"gh repo view {owner}/{repo_name}  (must NOT exist)",
        f"git init {tree}  + add + commit",
        f"gh repo create {owner}/{repo_name} --{visibility} --source <tree> --remote origin",
        "git push -u origin main  (never --force)",
    ]
    return PublishPlan(
        slug=slug,
        owner=owner,
        repo_name=repo_name,
        remote_url=remote_url,
        visibility=visibility,
        files=files,
        steps=steps,
    )


def publish_repo(
    slug: str,
    owner: str,
    *,
    visibility: str = "private",
    dry_run: bool = True,
    corpus_root: Path | str = DEFAULT_REPO_CORPUS,
    runner: Callable[[list[str]], str] | None = None,
) -> PublishPlan:
    """Build the plan; if not dry_run, create + push the repo. Returns the plan."""
    plan = build_plan(slug, owner, visibility=visibility, corpus_root=corpus_root)
    if dry_run:
        return plan

    run = runner or _default_runner
    tree = _repo_tree(slug, Path(corpus_root))

    # Existence guard: never touch a repo we did not just create.
    if _repo_exists(plan.owner, plan.repo_name, run):
        raise RuntimeError(
            f"{plan.owner}/{plan.repo_name} already exists -- refusing to touch a repo we did not create"
        )

    run(["git", "-C", str(tree), "init", "-q", "-b", "main"])
    run(["git", "-C", str(tree), "add", "-A"])
    run(["git", "-C", str(tree), "commit", "-q", "-m", f"chore: seed recette test agent {slug}"])
    run(
        [
            "gh", "repo", "create", f"{plan.owner}/{plan.repo_name}",
            f"--{visibility}", "--source", str(tree), "--remote", "origin", "--push",
        ]
    )
    plan.applied = True
    return plan


def _repo_exists(owner: str, repo: str, run: Callable[[list[str]], str]) -> bool:
    try:
        run(["gh", "repo", "view", f"{owner}/{repo}"])
        return True
    except subprocess.CalledProcessError:
        return False


def _default_runner(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
