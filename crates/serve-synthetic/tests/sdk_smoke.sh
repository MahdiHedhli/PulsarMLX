#!/usr/bin/env bash
# Run the OpenAI SDK compatibility check against a freshly started synthetic
# server on IPv4 loopback. Used unchanged by local runs and by CI so the two
# execute the same sequence.
#
# The bearer token is generated per run, written 0600, never printed, and
# removed on exit. No model assets, no network destination other than loopback.
set -euo pipefail

PYTHON="${PYTHON:-python3}"
CRATE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$CRATE_DIR"

WORK="$(mktemp -d)"
SERVER_PID=""
cleanup() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT

TOKEN_FILE="$WORK/token"
umask 077
# Disposable, generated, never echoed. Written directly rather than through a
# pipe so `set -o pipefail` cannot see a SIGPIPE from an early-exiting reader.
openssl rand -hex 20 > "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE"

cargo build --locked --quiet --bin pulsar-serve-synthetic

LOG="$WORK/server.log"
./target/debug/pulsar-serve-synthetic --token-file "$TOKEN_FILE" --port 0 >"$LOG" 2>&1 &
SERVER_PID=$!

ADDRESS=""
for _ in $(seq 1 100); do
  if [ -s "$LOG" ]; then
    ADDRESS="$(sed -n 's/.*listening on \(127\.0\.0\.1:[0-9]*\).*/\1/p' "$LOG" | head -1)"
    [ -n "$ADDRESS" ] && break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "server exited before binding:" >&2
    cat "$LOG" >&2
    exit 1
  fi
  sleep 0.1
done
if [ -z "$ADDRESS" ]; then
  echo "server did not report a loopback address:" >&2
  cat "$LOG" >&2
  exit 1
fi

case "$ADDRESS" in
  127.0.0.1:*) ;;
  *) echo "refusing non-loopback address: $ADDRESS" >&2; exit 1 ;;
esac

"$PYTHON" tests/sdk_client.py \
  --base-url "http://$ADDRESS/v1" \
  --token-file "$TOKEN_FILE"

# The server must not have written the bearer token to its own output.
if grep -qF "$(cat "$TOKEN_FILE")" "$LOG"; then
  echo "server log contained the bearer token" >&2
  exit 1
fi
echo "SDK_SMOKE_OK address=$ADDRESS"
