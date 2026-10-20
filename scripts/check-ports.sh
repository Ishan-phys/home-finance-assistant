#!/usr/bin/env bash
# Acceptance 6: PostgreSQL publishes no host port; the web app and API accept connections
# only on 127.0.0.1. Run with the stack up: `docker compose up -d`.
set -euo pipefail
cd "$(dirname "$0")/.."

fail() { echo "FAIL: $1" >&2; exit 1; }

db_ports=$(docker compose ps db --format '{{.Ports}}')
case "$db_ports" in
  *"->"*) fail "db publishes a host port: $db_ports" ;;
esac

for svc in web api; do
  ports=$(docker compose ps "$svc" --format '{{.Ports}}')
  [[ "$ports" == *"127.0.0.1:"* ]] || fail "$svc is not bound to 127.0.0.1: $ports"
  [[ "$ports" != *"0.0.0.0:"* && "$ports" != *"[::]:"* ]] || fail "$svc listens on all interfaces: $ports"
done

# A connection to the machine's LAN address must be refused.
lan_ip=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || true)
if [[ -n "${lan_ip:-}" ]]; then
  for port in 3000 8000 5432; do
    if (exec 3<>"/dev/tcp/$lan_ip/$port") 2>/dev/null; then
      fail "$lan_ip:$port accepted a connection"
    fi
  done
fi
echo "ok: db has no host port; web and api are bound to 127.0.0.1 only"
