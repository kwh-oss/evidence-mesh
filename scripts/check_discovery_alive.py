"""Check that requested AICs are alive in the official Discovery recent view."""

from __future__ import annotations

import argparse
import json
import urllib.request


DISCOVERY_URL = "https://wt.ioa.pub/discovery/acps-adp-v2/discover"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aic", action="append", required=True)
    parser.add_argument("--limit", type=int, default=50, choices=range(1, 51))
    args = parser.parse_args()

    body = json.dumps({"type": "recent", "limit": args.limit}).encode("utf-8")
    request = urllib.request.Request(
        DISCOVERY_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)

    alive_map = (payload.get("result") or {}).get("aliveMap") or {}
    results = {}
    missing = []
    for aic in args.aic:
        item = alive_map.get(aic) or {}
        alive = item.get("alive") is True
        results[aic] = {
            "alive": alive,
            "lastSeen": item.get("lastSeen") or item.get("last_seen"),
        }
        if not alive:
            missing.append(aic)

    print(json.dumps({"status": "DISCOVERY_ALIVE_OK" if not missing else "DISCOVERY_ALIVE_FAILED", "agents": results}, ensure_ascii=False))
    if missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
