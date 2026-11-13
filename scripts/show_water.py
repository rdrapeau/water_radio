#!/usr/bin/env python3
"""
Live Water Meter Inventory & Reading Inspector
Displays all captured water meter endpoints, packet counts, volume readings, and consumption deltas.
"""

import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs") if os.path.exists(os.path.join(PROJECT_ROOT, "logs")) else "."

SUMMARY_FILE = os.path.join(LOGS_DIR, "water_summary.json")
PACKETS_FILE = os.path.join(LOGS_DIR, "water_readings.jsonl")


def main():
    print("=" * 100)
    print(" 💧 Municipal Water Meter Live Readings & Consumption Tracker")
    print("=" * 100)

    if not os.path.exists(SUMMARY_FILE):
        print(f"[!] No water summary file ({SUMMARY_FILE}) found yet.")
        return

    with open(SUMMARY_FILE, "r") as f:
        summary = json.load(f)

    meters = summary.get("meters", {})
    total_pkts = summary.get("total_packets", 0)

    print(f"[*] Total Water Packets Captured: {total_pkts}")
    print(f"[*] Total Water Endpoints Seen:    {len(meters)}")
    print("-" * 100)

    if not meters:
        print("[i] No water endpoints recorded yet.")
        print("=" * 100)
        return

    hdr = f"  {'Meter ID':<12} | {'Packets':<7} | {'First Read':<12} | {'Latest Read':<12} | {'Delta':<10} | {'Status / Alerts':<22} | {'Target?'}"
    print(hdr)
    print("  " + "-" * 96)

    for m_id, entry in sorted(meters.items(), key=lambda x: x[1].get("packet_count", 0), reverse=True):
        count = entry.get("packet_count", 0)
        init_vol = entry.get("initial_volume")
        lat_vol = entry.get("latest_volume")
        unit = entry.get("unit") or ""
        
        init_str = f"{init_vol}" if init_vol is not None else "N/A"
        lat_str = f"{lat_vol}" if lat_vol is not None else "N/A"
        
        if init_vol is not None and lat_vol is not None and isinstance(init_vol, (int, float)) and isinstance(lat_vol, (int, float)):
            delta = lat_vol - init_vol
            if delta > 0:
                delta_str = f"+{delta} {unit}".strip()
            else:
                delta_str = "0"
        else:
            delta_str = "N/A"

        extra = entry.get("extra", {}) or {}
        flags = []
        if extra.get("leak_now"):
            flags.append("🚨 LEAK NOW")
        elif extra.get("leak"):
            flags.append(f"Leak({extra.get('leak')})")
        if extra.get("backflow"):
            flags.append("⚠️ BACKFLOW")
        if not flags:
            flags.append("Normal")
        flag_str = ", ".join(flags)

        is_target = "🎯 YES!" if entry.get("is_target") else "No"
        print(f"  {m_id:<12} | {count:<7} | {init_str:<12} | {lat_str:<12} | {delta_str:<10} | {flag_str:<22} | {is_target}")

    print("\n" + "=" * 100)


if __name__ == "__main__":
    main()
