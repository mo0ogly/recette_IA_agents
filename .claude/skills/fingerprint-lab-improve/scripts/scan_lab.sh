#!/bin/bash
# Scan complet du Discovery Lab et comparaison attendu vs detecte
# Usage: scan_lab.sh [PORTS] [TIMEOUT]
set -euo pipefail

BASE="/opt/lia-sec/dev"
LIAPROBE="$BASE/liaprobe/bin/liaprobe"
PORTS="${1:-18080,18081,18888,18889,18890,18891,18893,18894,18895,18200,13306,15432,16379,17017,19200,15601,15672}"
TIMEOUT="${2:-120}"
RESULT_FILE="/tmp/lab_scan_$(date +%Y%m%d_%H%M%S).json"

echo "=== Discovery Lab Fingerprint Scan ==="
echo "Ports: $PORTS"
echo "Timeout: ${TIMEOUT}s"
echo ""

cd "$BASE"
timeout "$TIMEOUT" "$LIAPROBE" --mode specific --ports "$PORTS" 127.0.0.1 2>/dev/null > "$RESULT_FILE" || true

RESULT="$RESULT_FILE" python3 << 'PYEOF'
import json, sys, os

result_file = os.environ["RESULT"]

expected = {
    18080: ("Nginx", "NGINX"), 18081: ("Apache", "APACH"),
    18888: ("Tomcat", "TOMC"), 18889: ("WordPress", "WPRSS"),
    18890: ("Drupal", "DRPL"), 18891: ("Nextcloud", "NXTCL"),
    18893: ("Keycloak", "KEYC"), 18894: ("phpMyAdmin", "PHPM"),
    18895: ("Adminer", "ADMI"), 18200: ("Vault", "VAULT"),
    13306: ("MySQL", "MYSQL"), 15432: ("PostgreSQL", "POSTGRESQL"),
    16379: ("Redis", "REDIS"), 17017: ("MongoDB", "MONGODB"),
    19200: ("Elasticsearch", "ELASTIC"), 15601: ("Kibana", "KIBAN"),
    15672: ("RabbitMQ", "RABBI")
}

try:
    with open(result_file) as f:
        content = f.read().strip()
    # Find last JSON block (the report) -- skip JSONL log lines
    depth = 0
    start = end = -1
    for i in range(len(content) - 1, -1, -1):
        if content[i] == '}':
            if depth == 0: end = i + 1
            depth += 1
        elif content[i] == '{':
            depth -= 1
            if depth == 0:
                start = i
                break
    if start < 0:
        print("ERROR: no JSON report found in output")
        sys.exit(1)
    report = json.loads(content[start:end])
except Exception as e:
    print(f"ERROR parsing: {e}")
    sys.exit(1)

# Build detected map: port -> best service (highest confidence)
detected = {}
for host in report.get("hosts", []):
    for svc in host.get("services", []):
        port = svc["port"]
        conf = svc["confidence"]
        if port not in detected or conf > detected[port]["confidence"]:
            detected[port] = svc

ok = fail = miss = down = 0
total = len(expected)

print(f"{'Port':<8} {'Expected':<15} {'Detected':<20} {'Conf':<6} {'Ver':<10} {'Verdict'}")
print("-" * 80)

for port in sorted(expected.keys()):
    name, taxo = expected[port]
    if port in detected:
        d = detected[port]
        product = d.get("product", "")
        dname = d.get("name", "")
        conf = d["confidence"]
        ver = d.get("version", "")
        pat = d.get("pattern_id", "")
        match = taxo.lower() in product.lower() or name.lower() in dname.lower()
        if match:
            verdict = "OK"
            ok += 1
        else:
            verdict = "FP"
            fail += 1
        print(f"{port:<8} {name:<15} {dname:<20} {conf:<6.2f} {ver:<10} {verdict} ({pat})")
    else:
        # Check if port is open
        alive = any(
            any(p.get("port") == port for p in h.get("open_ports", []))
            for h in report.get("hosts", [])
        )
        if alive:
            miss += 1
            print(f"{port:<8} {name:<15} {'---':<20} {'---':<6} {'---':<10} MISS")
        else:
            down += 1
            print(f"{port:<8} {name:<15} {'---':<20} {'---':<6} {'---':<10} DOWN")

print("-" * 80)
alive_total = total - down
if alive_total > 0:
    pct = ok * 100 // alive_total
else:
    pct = 0
print(f"Score: {ok}/{alive_total} alive ({pct}%) | FP: {fail} | MISS: {miss} | DOWN: {down}")
print(f"Results: {result_file}")
PYEOF

echo ""
echo "Result file: $RESULT_FILE"
