#!/usr/bin/env bash
# Send a short status notification to the project NTFY topic.
# Topic: https://ntfy.sh/Mahdi-Dev
set -euo pipefail
TITLE="${1:-PulsarMLX}"
BODY="${2:-status update}"
PRIORITY="${3:-default}"
curl -fsS \
  -H "Title: ${TITLE}" \
  -H "Priority: ${PRIORITY}" \
  -H "Tags: computer" \
  -d "${BODY}" \
  "https://ntfy.sh/Mahdi-Dev" >/dev/null
echo "ntfy ok: ${TITLE}"
