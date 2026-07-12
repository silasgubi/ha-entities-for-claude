#!/usr/bin/env python3
"""
ha_entities.py — Query Home Assistant entities from the JSON registries (.storage)

Reads Home Assistant's own JSON "database" (read-only, safe while HA is running):

    <config>/.storage/core.entity_registry   -> all entities
    <config>/.storage/core.device_registry   -> devices (manufacturer, model, inherited area)
    <config>/.storage/core.area_registry     -> areas

Optionally enriches results with live states from the REST API (--states).

Configuration (environment variables or CLI flags):

    HA_STORAGE_PATH   path to HA's .storage directory (or --storage)
                      e.g. /config/.storage, \\\\homeassistant\\config\\.storage
    HA_URL            base URL for the REST API (or --url)
                      default: http://homeassistant.local:8123
    HA_TOKEN          long-lived access token for --states (or --token)
                      create one at <HA_URL>/profile/security

Examples:

    python ha_entities.py --summary
    python ha_entities.py --domain light
    python ha_entities.py --area kitchen
    python ha_entities.py --search thermostat --states
    python ha_entities.py --domain sensor --search temperature --json

Zero dependencies — Python 3.9+ standard library only.
"""

import argparse
import json
import os
import sys
import urllib.request
from collections import Counter
from pathlib import Path

# Windows consoles may default to a legacy codepage; entity names can
# contain accents and emoji.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_URL = "http://homeassistant.local:8123"


def load_storage(storage: Path, name: str):
    with open(storage / name, encoding="utf-8") as f:
        return json.load(f)["data"]


def load_registries(storage: Path):
    entities = load_storage(storage, "core.entity_registry")["entities"]
    devices = {d["id"]: d for d in load_storage(storage, "core.device_registry")["devices"]}
    areas = {a["id"]: a["name"] for a in load_storage(storage, "core.area_registry")["areas"]}
    return entities, devices, areas


def resolve(e, devices, areas):
    """Flatten one entity, resolving its device and area (entities without
    their own area_id inherit the device's area)."""
    dev = devices.get(e.get("device_id") or "")
    area_id = e.get("area_id") or (dev.get("area_id") if dev else None)
    return {
        "entity_id": e["entity_id"],
        "name": e.get("name") or e.get("original_name") or "",
        "area": areas.get(area_id, ""),
        "device": (dev.get("name_by_user") or dev.get("name") or "") if dev else "",
        "platform": e.get("platform", ""),
        "disabled": e.get("disabled_by") or "",
        "hidden": e.get("hidden_by") or "",
        "device_class": e.get("original_device_class") or e.get("device_class") or "",
        "aliases": e.get("aliases") or [],
    }


def get_states(url: str, token: str, entity_ids):
    """Fetch current states via the REST API. Returns {entity_id: (state, unit)}."""
    req = urllib.request.Request(
        url.rstrip("/") + "/api/states",
        headers={"Authorization": "Bearer " + token},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        all_states = json.load(resp)
    wanted = set(entity_ids)
    return {
        s["entity_id"]: (
            s["state"],
            s.get("attributes", {}).get("unit_of_measurement", ""),
        )
        for s in all_states
        if s["entity_id"] in wanted
    }


def main():
    p = argparse.ArgumentParser(
        description="Query Home Assistant entities from the .storage JSON registries",
        epilog="Configure via HA_STORAGE_PATH / HA_URL / HA_TOKEN env vars or the flags above.",
    )
    p.add_argument("--storage", default=os.environ.get("HA_STORAGE_PATH"),
                   help="path to HA's .storage directory (env: HA_STORAGE_PATH)")
    p.add_argument("--url", default=os.environ.get("HA_URL", DEFAULT_URL),
                   help=f"HA base URL for --states (env: HA_URL, default: {DEFAULT_URL})")
    p.add_argument("--token", default=os.environ.get("HA_TOKEN"),
                   help="long-lived access token for --states (env: HA_TOKEN)")
    p.add_argument("--domain", help="filter by domain (light, sensor, ...)")
    p.add_argument("--area", help="filter by area name (partial match)")
    p.add_argument("--search", help="search in entity_id, name, device and aliases")
    p.add_argument("--disabled", action="store_true", help="only disabled entities")
    p.add_argument("--enabled-only", action="store_true", help="hide disabled entities")
    p.add_argument("--states", action="store_true", help="include current state (REST API)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--summary", action="store_true", help="totals per domain")
    p.add_argument("--areas", action="store_true", help="list areas with entity counts")
    args = p.parse_args()

    if not args.storage:
        p.error("no storage path: set HA_STORAGE_PATH or pass --storage")
    storage = Path(args.storage)
    if not (storage / "core.entity_registry").exists():
        p.error(f"core.entity_registry not found in {storage}")

    entities, devices, areas = load_registries(storage)
    rows = [resolve(e, devices, areas) for e in entities]

    if args.areas:
        counts = Counter(r["area"] or "(no area)" for r in rows)
        for area, n in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"{n:5d}  {area}")
        return

    if args.summary:
        counts = Counter(r["entity_id"].split(".")[0] for r in rows)
        disabled = sum(1 for r in rows if r["disabled"])
        print(f"Total: {len(rows)} entities ({disabled} disabled)")
        for dom, n in counts.most_common():
            print(f"{n:5d}  {dom}")
        return

    if args.domain:
        rows = [r for r in rows if r["entity_id"].split(".")[0] == args.domain]
    if args.area:
        q = args.area.lower()
        rows = [r for r in rows if q in r["area"].lower()]
    if args.search:
        q = args.search.lower()
        rows = [
            r for r in rows
            if q in r["entity_id"].lower()
            or q in r["name"].lower()
            or q in r["device"].lower()
            or any(q in a.lower() for a in r["aliases"])
        ]
    if args.disabled:
        rows = [r for r in rows if r["disabled"]]
    if args.enabled_only:
        rows = [r for r in rows if not r["disabled"]]

    rows.sort(key=lambda r: r["entity_id"])

    if args.states and rows:
        if not args.token:
            print("WARNING: --states needs a token (HA_TOKEN or --token); skipping states",
                  file=sys.stderr)
        else:
            try:
                states = get_states(args.url, args.token, [r["entity_id"] for r in rows])
            except OSError as e:
                print(f"WARNING: could not reach {args.url}: {e}", file=sys.stderr)
                states = {}
            for r in rows:
                st = states.get(r["entity_id"])
                r["state"] = (st[0] + (" " + st[1] if st[1] else "")) if st else "?"

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return

    if not rows:
        print("No entities found.")
        return

    for r in rows:
        flags = []
        if r["disabled"]:
            flags.append("DISABLED")
        if r["hidden"]:
            flags.append("hidden")
        extra = f" [{','.join(flags)}]" if flags else ""
        state = f" = {r['state']}" if "state" in r else ""
        area = f" ({r['area']})" if r["area"] else ""
        name = f" | {r['name']}" if r["name"] else ""
        print(f"{r['entity_id']}{state}{area}{name}{extra}")
    print(f"\n{len(rows)} entities")


if __name__ == "__main__":
    main()
