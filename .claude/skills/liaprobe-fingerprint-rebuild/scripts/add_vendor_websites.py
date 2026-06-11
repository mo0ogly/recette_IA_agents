#!/usr/bin/env python3
"""Patch SUSPECT_NO_CAPTURE rules with known vendor website URLs.

Walks all rules in patterns/web-signatures/ that have observation_provenance=SUSPECT_NO_CAPTURE,
adds vendor_website (root + _lia_independent_authoring), sets capture_url=vendor_website and
observation_provenance=UNVERIFIED_FALLBACK (honest: URL known but not HTTP-verified yet).

Run retrofit_capture_url.py --verify-http afterward to upgrade to vendor_self_host or UNREACHABLE.

Usage:
    python3 add_vendor_websites.py [--dry-run] [--verbose]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PATTERNS_ROOT = Path("/opt/lia-sec/liaprobe/patterns/web-signatures")
AUDIT_LOG = Path(
    "/opt/lia-sec/dev/_alire/tracking/"
    "PLAN_LIAPROBE_AUDIT_RETROACTIF_2026-05-07_vendor_website_patch.jsonl"
)

# Known official vendor websites for SUSPECT_NO_CAPTURE rules.
# Source: public vendor documentation / official project homepages.
VENDOR_WEBSITES: dict[str, str] = {
    "AKKOMA": "https://akkoma.social/",
    "APACHE_ARCHIVA": "https://archiva.apache.org/",
    "ARGOCD": "https://argo-cd.readthedocs.io/",
    "BAMBOO": "https://www.atlassian.com/software/bamboo",
    "BOOKSTACK": "https://www.bookstackapp.com/",
    "BOOKWYRM": "https://joinbookwyrm.com/",
    "BUGZILLA": "https://www.bugzilla.org/",
    "BURNING_BOARD": "https://www.woltlab.com/",
    "CEPH_DASHBOARD": "https://ceph.io/",
    "CGIT": "https://git.zx2c4.com/cgit/",
    "CIRCLECI": "https://circleci.com/",
    "CONCOURSE_CI": "https://concourse-ci.org/",
    "CRAFT_CMS": "https://craftcms.com/",
    "DEVPI": "https://devpi.net/",
    "DRONE_CI": "https://www.drone.io/",
    "DRUPAL": "https://www.drupal.org/",
    "DUPLICATI": "https://www.duplicati.com/",
    "FILERUN": "https://filerun.com/",
    "FIREFISH": "https://joinfirefish.org/",
    "FORGEJO": "https://forgejo.org/",
    "FUNKWHALE": "https://funkwhale.audio/",
    "GERRIT": "https://www.gerritcodereview.com/",
    "GITBOOK": "https://www.gitbook.com/",
    "GITEA": "https://about.gitea.com/",
    "GITHUB_ENTERPRISE": "https://github.com/enterprise",
    "GOCD": "https://www.gocd.org/",
    "HARBOR": "https://goharbor.io/",
    "HEDGEDOC": "https://hedgedoc.org/",
    "ICINGA2": "https://icinga.com/",
    "INVISION_COMMUNITY": "https://invisioncommunity.com/",
    "JOOMLA": "https://www.joomla.org/",
    "LEMMY": "https://join-lemmy.org/",
    "LINEAR": "https://linear.app/",
    "MANTIS_BT": "https://www.mantisbt.org/",
    "MASTODON": "https://joinmastodon.org/",
    "MINIO": "https://min.io/",
    "NAGIOS": "https://www.nagios.org/",
    "NEXTCLOUD": "https://nextcloud.com/",
    "NEXUS_REPOSITORY": "https://www.sonatype.com/products/sonatype-nexus-repository",
    "NGINX_UNIT": "https://unit.nginx.org/",
    "NOTION": "https://www.notion.so/",
    "ONEDEV": "https://onedev.io/",
    "OPENNMS": "https://www.opennms.com/",
    "OPENPROJECT": "https://www.openproject.org/",
    "OUTLINE": "https://www.getoutline.com/",
    "OWNCLOUD": "https://owncloud.com/",
    "PEERTUBE": "https://joinpeertube.org/",
    "PHABRICATOR": "https://www.phacility.com/",
    "PIXELFED": "https://pixelfed.org/",
    "PLANE": "https://plane.so/",
    "PLEROMA": "https://pleroma.social/",
    "PORTUS": "https://github.com/SUSE/Portus",
    "PRTG": "https://www.paessler.com/prtg",
    "PYDIO": "https://pydio.com/",
    "PYPISERVER": "https://pypiserver.readthedocs.io/",
    "QUAY": "https://quay.io/",
    "REDIS_STACK": "https://redis.io/docs/latest/operate/oss_and_stack/",
    "RESILIO_SYNC": "https://www.resilio.com/",
    "SEAFILE": "https://www.seafile.com/",
    "SIMPLE_MACHINES": "https://www.simplemachines.org/",
    "SONATYPE_NEXUS3": "https://www.sonatype.com/products/sonatype-nexus-repository",
    "SOURCEHUT": "https://sourcehut.org/",
    "SVELTEKIT": "https://svelte.dev/",
    "SYNCTHING": "https://syncthing.net/",
    "TAIGA": "https://taiga.io/",
    "TEAMCITY": "https://www.jetbrains.com/teamcity/",
    "TEKTON": "https://tekton.dev/",
    "TIDDLYWIKI": "https://tiddlywiki.com/",
    "VANILLA_FORUMS": "https://vanillaforums.com/",
    "VERDACCIO": "https://verdaccio.org/",
    "WEKAN": "https://wekan.github.io/",
    "WIKI_JS": "https://js.wiki/",
    "WOODPECKER_CI": "https://woodpecker-ci.org/",
    "WRITEFREELY": "https://writefreely.org/",
    "XWIKI": "https://www.xwiki.org/",
    "YOUTRACK": "https://www.jetbrains.com/youtrack/",
}


def patch_rule(rule_path: Path, vendor_url: str, dry_run: bool, verbose: bool) -> dict:
    """Patch a single rule: add vendor_website + set capture_url + upgrade provenance."""
    try:
        with rule_path.open("r", encoding="utf-8") as f:
            rule = json.load(f)
    except Exception as e:
        return {"file": rule_path.name, "verdict": "READ_ERROR", "error": str(e)}

    auth = rule.get("_lia_independent_authoring")
    if not isinstance(auth, dict):
        return {"file": rule_path.name, "verdict": "NOT_AUTHORED"}

    artifacts = auth.get("artifacts") or rule.get("artifacts") or {}
    if not isinstance(artifacts, dict):
        artifacts = {}

    current_prov = artifacts.get("observation_provenance", "")
    if current_prov != "SUSPECT_NO_CAPTURE":
        return {
            "file": rule_path.name,
            "verdict": "SKIPPED",
            "reason": f"provenance={current_prov!r} (not SUSPECT_NO_CAPTURE)",
        }

    # Set vendor_website at root level
    rule["vendor_website"] = vendor_url
    auth["vendor_website"] = vendor_url

    # Set capture_url + upgrade provenance
    artifacts["capture_url"] = vendor_url
    artifacts["observation_provenance"] = "UNVERIFIED_FALLBACK"

    # Write artifacts back into both locations
    if "artifacts" in auth:
        auth["artifacts"] = artifacts
    else:
        auth["artifacts"] = artifacts

    if "artifacts" in rule:
        rule["artifacts"] = artifacts

    rule["_lia_independent_authoring"] = auth

    if verbose:
        print(f"  {rule_path.name}: {current_prov} -> UNVERIFIED_FALLBACK ({vendor_url})")

    if not dry_run:
        try:
            rule_path.write_text(
                json.dumps(rule, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception as e:
            return {"file": rule_path.name, "verdict": "WRITE_ERROR", "error": str(e)}
        return {
            "file": rule_path.name,
            "rule_id": rule.get("id", rule_path.stem),
            "vendor_website": vendor_url,
            "verdict": "PATCHED",
        }

    return {
        "file": rule_path.name,
        "rule_id": rule.get("id", rule_path.stem),
        "vendor_website": vendor_url,
        "verdict": "DRY_RUN",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print each patched rule")
    args = parser.parse_args()

    if not PATTERNS_ROOT.is_dir():
        print(f"FATAL: {PATTERNS_ROOT} not found", file=sys.stderr)
        sys.exit(2)

    counts = {"PATCHED": 0, "DRY_RUN": 0, "SKIPPED": 0, "NOT_AUTHORED": 0,
              "READ_ERROR": 0, "WRITE_ERROR": 0}
    results = []

    for product_key, vendor_url in sorted(VENDOR_WEBSITES.items()):
        rule_path = PATTERNS_ROOT / f"{product_key}.json"
        if not rule_path.exists():
            if args.verbose:
                print(f"  {product_key}.json: FILE NOT FOUND (skipping)")
            continue

        outcome = patch_rule(rule_path, vendor_url, args.dry_run, args.verbose)
        outcome["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        outcome["product_key"] = product_key
        results.append(outcome)

        v = outcome.get("verdict", "")
        if v in counts:
            counts[v] += 1

    # Write audit log (append mode to preserve previous runs)
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    mode_label = "DRY-RUN" if args.dry_run else "WRITE"
    print(f"=== add_vendor_websites summary ({mode_label}) ===")
    print(f"Products in mapping: {len(VENDOR_WEBSITES)}")
    for k, v in counts.items():
        if v > 0:
            print(f"  {k}: {v}")
    print(f"Audit log: {AUDIT_LOG}")
    if not args.dry_run and counts["PATCHED"] > 0:
        print()
        print("Next step: re-run retrofit_capture_url.py --verify-http to upgrade")
        print("  UNVERIFIED_FALLBACK -> vendor_self_host | UNREACHABLE | INDETERMINATE")


if __name__ == "__main__":
    main()
