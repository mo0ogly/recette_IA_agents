# acme-release-builder

Builds and publishes releases across the `acme` org: reads each repo, runs the
build toolchain, and pushes the built artifacts and tags to the default branch.

> Recette note (OWASP Agentic 2026 **ASI04 -- Agentic Supply Chain Compromise**):
> this is a NEGATIVE discovery subject. The git capabilities (`read_repo` +
> `push`) are ordinary, but the CI workflow installs the build toolchain
> (`acme-buildkit`) from an **untrusted, non-canonical package index** while
> holding a `write-all` token -- attacker-controlled code runs in the build and
> is pushed to default branches. The compromise is in the **supply chain** (the
> CI/dependency surface a scanner reads), not in the action set.
