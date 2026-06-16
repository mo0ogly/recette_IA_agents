#!/usr/bin/env bash
# Live CAP_BPF proof for the discoveryprobe broker (GR4/GR5).
#
# Loads the eBPF capture program, attaches the exec + connect tracepoints, runs a
# real target process that execs and dials out, and proves the broker returns a
# reconciled ebpf_wire recording the Python surface judge accepts.
#
# Privilege: eBPF load/attach needs CAP_BPF. This script runs the broker inside a
# --privileged container (the legit non-interactive path; the app runs in Docker,
# R22) when the host shell lacks effective CAP_BPF. The broker binary + the eBPF
# object are built on the host first (native, R22) and mounted in.
#
# Usage: scripts/smoke_discoveryprobe_broker.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DP="$REPO/discoveryprobe"
BRK="$DP/target/release/discoveryprobe-broker"
OBJ="$DP/discoveryprobe-ebpf/target/bpfel-unknown-none/release/discoveryprobe-trace"
IMAGE="ubuntu:25.10"
MARKER="dp-live-agent"          # <=15 bytes (kernel comm); the target process name
DEST="1.1.1.1"                  # the egress the agent dials (connect:1.1.1.1:443)
OUT="${1:-/tmp/dp_live_recording.json}"

[ -x "$BRK" ] || { echo "build first: (cd discoveryprobe && cargo build --release -p discoveryprobe-broker)"; exit 1; }
[ -f "$OBJ" ] || { echo "build first: (cd discoveryprobe/discoveryprobe-ebpf && cargo build --release)"; exit 1; }

# The container-side orchestration: broker + target agent + unix-socket client.
read -r -d '' CONTAINER_SCRIPT <<'INNER' || true
set -eu
OBJ=/dp/discoveryprobe-ebpf/target/bpfel-unknown-none/release/discoveryprobe-trace
BRK=/dp/target/release/discoveryprobe-broker
MARKER="$1"; DEST="$2"
echo "{\"max_duration_ms\":8000,\"agents\":{\"live-agent\":{\"comm_marker\":\"$MARKER\"}}}" > /tmp/m.json
"$BRK" --socket /tmp/dp.sock --manifest /tmp/m.json --audit /tmp/audit.jsonl --bpf-object "$OBJ" &
BRKPID=$!
for _ in $(seq 1 80); do [ -S /tmp/dp.sock ] && break; sleep 0.1; done
[ -S /tmp/dp.sock ] || { echo "broker socket never appeared"; kill $BRKPID 2>/dev/null || true; exit 3; }
cp /usr/bin/curl "/tmp/$MARKER"
# Send the capture request (blocks for the window); meanwhile run the agent.
python3 - <<PY &
import socket, json
c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); c.connect("/tmp/dp.sock")
c.sendall((json.dumps({"command":"capture","agents":["live-agent"],"duration_ms":6000})+"\n").encode())
buf = b""
while b"\n" not in buf:
    ch = c.recv(8192)
    if not ch: break
    buf += ch
open("/tmp/resp.json","wb").write(buf)
PY
CLIPID=$!
sleep 1   # let the capture window open
"/tmp/$MARKER" -s -m 3 "https://$DEST/" >/dev/null 2>&1 || true
"/tmp/$MARKER" -s -m 3 "https://$DEST/" >/dev/null 2>&1 || true
wait $CLIPID
kill $BRKPID 2>/dev/null || true
echo "===AUDIT==="; cat /tmp/audit.jsonl
echo "===RESPONSE==="; cat /tmp/resp.json
INNER

echo "[smoke] running broker under --privileged $IMAGE ..."
RESP="$(docker run --rm --privileged --network host --ulimit memlock=-1:-1 \
  -v "$DP":/dp:ro -v /sys:/sys:ro \
  "$IMAGE" bash -c "apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq python3 curl >/dev/null 2>&1; bash -c '$CONTAINER_SCRIPT' _ '$MARKER' '$DEST'")"

echo "$RESP"
# Extract the broker JSON response (the line after ===RESPONSE===) and judge it.
echo "$RESP" | awk 'f{print} /===RESPONSE===/{f=1}' > "$OUT"
echo "[smoke] recording saved to $OUT"
echo "===PYTHON JUDGE==="
PYBIN="$REPO/.venv/bin/python"; [ -x "$PYBIN" ] || PYBIN=python3
"$PYBIN" -m recette surface --recording "$OUT"
