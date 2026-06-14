# R18 No Deduction -- Verify Facts Before Asserting

## Why this rule exists

Incident 2026-04-07: I claimed `/go-recette` couldn't run `gosec` on `cmd/sigma_web/`
because of "multiple `func main()`" in the directory. I ran a grep `^func main`
which matched `func mainTest` by accident, counted 20 occurrences, and **deduced**
that the repo had multiple main functions preventing gosec from working. I then
baked this false claim into the skill documentation and the Discovery RETEX as
a "limitation technique".

**Reality, verified later**:
- Only ONE real `func main()` in the repo (`backend_8081.go`). A second file
  (`import_campaigns.go`) had `// +build ignore`, so it was excluded.
- The repo has a **sub-module** in `cmd/sigma_web/go.mod` (module `sigma_web_backend`).
- gosec works perfectly when run from that directory: 634 files, 373k lines,
  5645 issues found.

The root cause of my error was **inventing an explanation from a single failed
command** instead of debugging the actual failure. I wrote a false rule and
shipped it into the skill.

## The rule (MANDATORY)

Before asserting ANY technical claim about code, infrastructure, or tools:

1. **Verify by running the command.** A hypothesis is not an answer.
   - Bad: "gosec fails because multi-main" (deduction from a single bad result)
   - Good: `cd cmd/sigma_web && gosec .` tried, result observed, then conclusion.

2. **Verify grep matches literally.** A regex match is not a verified count.
   - Bad: `grep ^func main | wc -l` -> 20, conclude "20 mains"
   - Good: `grep -E '^func main\(\)' | wc -l` -> 2, then check each hit for
     build tags / real presence.

3. **Never skip a step "because obviously".** If the explanation needs
   "obviously", it probably is not. Verify.

4. **If a tool returns Files=0 / Lines=0 / empty output**, that is a FAILURE
   TO INVESTIGATE, not a definitive answer. Diagnose:
   - Is the cwd correct?
   - Is there a sub-module / nested go.mod ?
   - Are there build tags excluding files?
   - Does `go list` / `go env GOMOD` tell me what Go thinks of this directory?

5. **Never ship an explanation into documentation, skills, RETEX or rules
   without having reproduced the verification at least once.** A RETEX with a
   false explanation is worse than no RETEX — it teaches the wrong lesson.

## Triggers

Apply this rule when about to:
- Write a "limitation" or "known issue" into documentation
- Claim a tool "doesn't work" or "isn't compatible"
- Claim a file/symbol/function "doesn't exist" without running grep
- Claim a process "is blocked by X" without trying the workaround
- Count occurrences with grep without checking the regex is exact

## Red flags in my own output

If I write any of these without a command output in the same turn, STOP and verify:
- "because the repo has..."
- "due to..."
- "this is likely caused by..."
- "multi-main prevents..."
- "this is a known limitation of..."
- "it is well-known that..."

## Why this matters

False assertions in RETEX / documentation pollute future decisions. The next
Claude instance (or human) will read "multi-main blocks gosec" and accept it.
A false fact documented once is a fact repeated forever until someone reverifies.

The only defense is: **don't ship unverified claims in the first place**.

## Integration with other rules

- **R17 Frontend Contract Gate** was created for the same reason: no shipping
  without rendering against a real payload.
- **R18** is the general principle: don't ship without running.
- Both rules share the same anti-pattern: "the unit test passed / the type
  checks / the grep returned something" is not the same as "it actually works".
