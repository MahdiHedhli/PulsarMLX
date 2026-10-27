#!/usr/bin/env bash
# Publish status to an explicitly configured private notification destination.
# Publication receipts are delivery evidence, never execution authorization.
set -euo pipefail
URL="${PULSAR_NTFY_URL:-}"
if [[ -z "$URL" ]]; then
  printf '%s\n' 'PULSAR_NTFY_URL must be configured privately; no default destination.' >&2
  exit 2
fi
case "$URL" in
  https://?*/*) ;;
  *) printf '%s\n' 'Notification destination must be an HTTPS URL with a topic path.' >&2; exit 2 ;;
esac
case "$URL" in
  *$'\r'*|*$'\n'*|*' '*|*$'\t'*)
    printf '%s\n' 'Invalid notification destination.' >&2; exit 2 ;;
esac
TITLE="${1:-PulsarMLX}"
BODY="${2:-status update}"
PRIORITY="${3:-default}"
for HEADER_VALUE in "$TITLE" "$PRIORITY"; do
  case "$HEADER_VALUE" in
    *$'\r'*|*$'\n'*) printf '%s\n' 'Invalid notification header.' >&2; exit 2 ;;
  esac
done
printf '%s' "$BODY" | curl -q \
  --proto '=https' --tlsv1.2 --fail --silent --show-error \
  --connect-timeout 5 --max-time 12 \
  -H "Title: ${TITLE}" \
  -H "Priority: ${PRIORITY}" \
  -H 'Tags: computer' \
  --data-binary @- --url "$URL" >/dev/null
printf '%s\n' 'Notification publish request completed.'
