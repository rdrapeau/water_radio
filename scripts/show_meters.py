#!/usr/bin/env python3
"""
Utility Meter Live Inventory Display
Prints a categorized table of all Water, Gas, and Electric meters discovered.
"""

import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs") if os.path.exists(os.path.join(PROJECT_ROOT, "logs")) else "."

METERS_FILE = os.path.join(LOGS_DIR, "utility_meters.json")
PACKETS_FILE = os.path.join(LOGS_DIR, "utility_readings.jsonl")


def main():
    print("=" * 80)
    print(" 📊 Municipal Utility Meter Telemetry Registry")
    print("=" * 80)

    if not os.path.exists(METERS_FILE):
        print(f"[!] No meter registry file ({METERS_FILE}) found yet.")
        return

    with open(METERS_FILE, "r") as f:
        meters = json.load(f)

    if not meters:
        print("[i] Meter registry is currently empty.")
        return

    total_pkts = 0
    if os.path.exists(PACKETS_FILE):
        with open(PACKETS_FILE, "r") as pf:
            total_pkts = sum(1 for _ in pf)

    print(f"[*] Total Intercepted Packets: {total_pkts}")
    print(f"[*] Total Tracked Meters:      {len(meters)}")
    print("-" * 80)

    # Group by kind: Water, Gas, Electric, Utility
    groups = {"Water": [], "Gas": [], "Electric": [], "Utility": []}
    for m_id, entry in meters.items():
        kind = entry.get("kind", "Utility")
        if kind not in groups:
            groups[kind] = []
        groups[kind].append(entry)

    for kind, items in groups.items():
        if not items:
            continue
        print(f"\n🏷️  {kind.upper()} METERS ({len(items)}):")
        print(f"  {'Meter ID':<14} | {'Protocol/Model':<22} | {'Packets':<8} | {'Latest Reading':<16} | {'Last Seen'}")
        print("  " + "-" * 76)
        for item in sorted(items, key=lambda x: x.get("count", 0), reverse=True):
            m_id = item.get("id", "N/A")
            proto = item.get("protocol", "N/A")[:20]
            cnt = item.get("count", 0)
            read_val = str(item.get("latest_reading", "N/A"))
            unit = item.get("unit") or ""
            read_str = f"{read_val} {unit}".strip()
            seen = item.get("last_seen", "")
            print(f"  {m_id:<14} | {proto:<22} | {cnt:<8} | {read_str:<16} | {seen}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
