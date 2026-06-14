# R21 No Work Loss -- merge across concurrent sessions without losing anything

> Several Claude/operator sessions run against the SAME checkout (one `.git`,
> one working tree). A `checkout` / `merge` / `pull` / `reset` in session A can
> clobber session B's uncommitted edits, and a dirty file you did not create can
> be silently reverted under you. This rule makes "merge without losing work"
> the default and gives the exact recovery path when something looks gone.

## Why this rule exists

Incident 2026-06-14: while one session merged a feature branch into `main`, a
second session was editing `console/src/components/PreciseLaunchModal.tsx` in the
SAME working tree. The edit appeared "lost" mid-command (`nothing to commit,
working tree clean`) and the operator reported "j'arrive pas a merger et je perd
du travail". Nothing was actually lost: the other session had committed the file
as `0d7d435`, and a third session advanced `main` to `32df1e0`. But the panic was
real because there was no protocol. This rule is that protocol.

## The root cause: one working tree, many writers

A git working tree holds exactly ONE set of files. Two sessions sharing it share
those files. Uncommitted = unprotected: any branch switch, merge, stash, or hard
reset from the other session can overwrite or revert it. The fix is twofold:
(1) never destroy a dirty tree you do not own, and (2) give each session its own
working tree.

## The protocol (BLOCKING before any branch-moving git command)

A "branch-moving" command = `checkout` / `switch` / `merge` / `pull` / `rebase`
/ `reset`. Before running one:

1. **`git status` first, always.** If the tree shows modified/untracked files
   you did NOT create this session, STOP. They are another session's WIP. Do not
   `checkout`, do not `reset --hard`, do not `stash drop`, do not `merge` over
   them.
2. **Snapshot before you switch.** Never move branches over a dirty tree. Either:
   - commit the dirty file to a wip branch: `git checkout -b wip/<topic>` then
     `git add -p && git commit -m "wip(...): <what> (incomplete)"`, OR
   - `git stash push -m "session-<id>: <what>"` (labelled so the owner finds it).
   A labelled stash or a wip commit is recoverable; an overwritten dirty file may
   not be.
3. **Commit small, commit often, push the branch.** Uncommitted work is the only
   work git cannot help you recover cleanly. The moment a unit compiles, commit
   it on your branch and `git push -u origin <branch>`. Pushed = safe from every
   local race.
4. **Merge to `main` only from a clean, committed, pushed branch** (`--no-ff`,
   after the gate). Never merge with a dirty tree (R1). If `main` advanced under
   you, the push is a clean fast-forward; if it conflicts, resolve on your branch,
   never with `-X ours/theirs` blind.
5. **Never `--force` / `reset --hard` / `stash drop` / `branch -D` on anything
   you did not create this session** without confirming with the operator (R1).
   These are the only git operations that actually destroy work.

## Recovery -- "my change disappeared" (nothing committed is ever lost)

Run these in order; one of them holds the work:

```
git status
git stash list
git reflog -20
git fsck --lost-found
git log --all --oneline -20
```

- `reflog` lists every HEAD move (commits, checkouts, merges) -- a parallel
  session's commit shows up here even if it is on another branch.
- `git stash list` finds another session's labelled snapshot.
- `git fsck --lost-found` surfaces dangling commits/blobs from an interrupted
  operation.
- If the change was committed by another session, it is on some branch/commit:
  `git log --all --source -S"<a unique line of the change>"` finds it.

Only `reset --hard` / `checkout -- <file>` / `stash drop` / `branch -D` over
UNCOMMITTED content destroys it beyond reflog. That is why steps 2-3 above
(snapshot + commit) come first.

## The durable fix: one git worktree per session

Stop sharing one working tree. Give each concurrent session its own tree backed
by the same `.git`, on its own branch:

```
git worktree add ../recette_<session> -b feat/<session>
```

Each session edits, commits, and runs gates in ITS OWN directory -- no shared
dirty-file race is possible. Branch names MUST be distinct per session (a shared
branch name caused an earlier ref collision, see [[shared-working-tree-multisession]]).
List/clean with `git worktree list` / `git worktree remove`. Services stay
launched by `./recette.sh` from the canonical tree (R19); a worktree is for
editing + committing, not for spawning a second platform on new ports.

## Quick check before merging

```
git status                       # clean? if dirty files not yours -> STOP, snapshot
git fetch origin && git log --oneline origin/main..HEAD   # what you will push
./recette.sh console-test        # (or the relevant gate) before a shared-main push
```

## Related

- `.claude/rules/recette-sh-single-entrypoint.md` (R19) -- one launcher, fixed ports.
- `.claude/rules/recette-and-test-constraints.md` (R20) -- gate before merge.
- R1 (CLAUDE.md) -- commit before mass change; never `--force`/`reset --hard`/
  `--no-verify` without authorization.
- memory `shared-working-tree-multisession` -- worktree + distinct branch names.
