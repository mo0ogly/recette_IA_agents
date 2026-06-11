# R24 No Backslash Line Continuation in Copy-Paste Commands

## Why this rule exists

User feedback 2026-04-17: when I propose shell commands with `\` line
continuations (multi-line command joined by trailing backslashes), the
backslashes do NOT survive copy-paste cleanly. The user ends up with broken
commands, stray `\` characters, or commands that run only the first line.

## The rule (MANDATORY)

When I output a shell command block intended to be copy-pasted by the user
into a terminal:

1. **Never use trailing `\` to continue a command on the next line.**
2. **One logical command = one single physical line**, even if long.
3. If a command is too long to read:
   - Split into **multiple independent lines** (separate commands) when they
     are commutative / idempotent
   - Or chain with `&&` **on the same line** (not with `\` linebreaks)
   - Or put the logic in a script file and tell the user to run the script

## Forbidden pattern

```bash
# FORBIDDEN -- backslashes break on copy-paste
mkdir -p /etc/nginx/archive && \
mv /etc/nginx/sites-enabled/agentrail.bak.20260313 /etc/nginx/archive/ && \
nginx -t && systemctl reload nginx
```

```bash
# FORBIDDEN -- even with indentation
rm -v /opt/agentrail/backups/agentrail_20260414.dump \
      /opt/agentrail/backups/agentrail_20260415.dump \
      /opt/agentrail/backups/agentrail_20260416.dump
```

## Correct patterns

**Option 1 -- one long line, chained with `&&`:**

```bash
mkdir -p /etc/nginx/archive && mv /etc/nginx/sites-enabled/agentrail.bak.20260313 /etc/nginx/sites-enabled/agentrail.bak.20260409-093040 /etc/nginx/archive/ && nginx -t && systemctl reload nginx
```

**Option 2 -- separate independent lines (preferred when steps are commutative):**

```bash
rm -v /opt/agentrail/backups/agentrail_20260414.dump
rm -v /opt/agentrail/backups/agentrail_20260415.dump
rm -v /opt/agentrail/backups/agentrail_20260416.dump
rm -v /opt/agentrail/backups/agentrail_20260417.dump
df -h / | tail -1
```

**Option 3 -- list form for `rm` / `mv` with multiple targets on one line:**

```bash
rm -v /opt/agentrail/backups/agentrail_20260414.dump /opt/agentrail/backups/agentrail_20260415.dump /opt/agentrail/backups/agentrail_20260416.dump /opt/agentrail/backups/agentrail_20260417.dump
```

**Option 4 -- shell loop on one line when the pattern fits:**

```bash
for d in 20260414 20260415 20260416 20260417; do rm -v /opt/agentrail/backups/agentrail_${d}.dump; done
```

## Exception (documented in code files only)

Backslash continuations ARE still allowed inside:
- Shell scripts checked into the repo (`.sh` files) — they are sourced, not copy-pasted
- Dockerfiles (`RUN foo \\\n    && bar`)
- Makefiles (tab-indented continuations)
- Example code blocks whose sole purpose is documentation of a script (not execution)

In those cases, the user reads/edits the file, they do not copy-paste it into a terminal.

## Triggers

Apply this rule any time I output a shell command block to the user. Before
I send the response, scan my output for any line ending with `\\\n`. If I find
one, rewrite it using Option 1, 2, 3 or 4 above.

## Related

- `.claude/rules/no-deduction-verify-facts.md` (R18) — same philosophy:
  verify the output is usable, do not assume "it is obvious"
- `.claude/rules/anti-patterns.md` — applies to all shared commands
