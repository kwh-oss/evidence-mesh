#!/usr/bin/env bash
set -euo pipefail

BROKER="${AMP_KAFKA_BROKERS:-wt.ioa.pub:19092}"
AIC_PATTERN='1.2.156.3088.1.BUPT.V2OEMK.(8F6Q2P.5DFSEW.04FV|4WOEC2.QC1J9G.1CKB|SNH8OB.O2SC18.01G5|W12RL4.G7QDHG.0MLO|V2F9QQ.WFZS7M.0A28)'
SINCE_MS="$(date -u -d '10 minutes ago' +%s000)"

topics=(amp.heartbeat amp.access amp.audit)
if [[ "${CHECK_GROUP_MESSAGE:-false}" == "true" ]]; then
  topics+=(amp.message)
fi

for topic in "${topics[@]}"; do
  count="$({
    timeout 15 sudo docker run --rm edenhill/kcat:1.7.1 \
      -C -b "$BROKER" -t "$topic" -o "s@$SINCE_MS" -e -q 2>/dev/null || true
  } | grep -E -c "$AIC_PATTERN" || true)"
  printf '%s matching_records=%s\n' "$topic" "$count"
  if [[ "$count" -lt 1 ]]; then
    printf 'No matching records for %s\n' "$topic" >&2
    exit 1
  fi
done
