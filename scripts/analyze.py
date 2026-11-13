#!/usr/bin/env python3
"""
AMR Capture Log Analyzer
Parses packets_10min.jsonl, raw_stream_10min.log, and summary_10min.json.
Generates tabular reporting, checks for an optional target ID, and calculates broadcast rates.
"""

import json
import os
import sys

TARGET_ID = os.environ.get("TARGET_METER_ID", "").strip()
PACKETS_FILE = "packets_10min.jsonl"
SUMMARY_FILE = "summary_10min.json"
RAW_FILE = "raw_stream_10min.log"


def main():
    print("=" * 75)
    print(" 📊 AMR Water Radio 10-Minute Capture Analysis Report")
    print("=" * 75)

    if not os.path.exists(PACKETS_FILE) and not os.path.exists(SUMMARY_FILE):
        print(f"[!] No capture files found in {os.getcwd()}")
        sys.exit(1)

    raw_lines = 0
    if os.path.exists(RAW_FILE):
        with open(RAW_FILE, "r") as f:
            raw_lines = sum(1 for _ in f)

    packets = []
    if os.path.exists(PACKETS_FILE):
        with open(PACKETS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        packets.append(json.loads(line))
                    except Exception:
                        pass

    print(f"[*] Raw Stream Output Lines: {raw_lines}")
    print(f"[*] Valid Structured Packets: {len(packets)}")

    if not packets:
        print("\n[i] No valid AMR packets decoded during this session.")
        print(f"[i] Raw log location: {os.path.abspath(RAW_FILE)}")
        print("=" * 75)
        return

    # Aggregate stats
    meters = {}
    target_hits = []

    for item in packets:
        pkt = item.get("packet", {})
        msg = pkt.get("Message", {})
        m_id = str(msg.get("ID") or pkt.get("EndpointID") or "UNKNOWN")
        proto = pkt.get("Type", "UNKNOWN")
        vol = msg.get("Consumption")
        ts = item.get("received_at", "")

        if TARGET_ID and TARGET_ID in m_id:
            target_hits.append(item)

        if m_id not in meters:
            meters[m_id] = {
                "id": m_id,
                "protocol": proto,
                "first_seen": ts,
                "last_seen": ts,
                "count": 1,
                "initial_vol": vol,
                "latest_vol": vol,
                "volumes": [vol] if vol is not None else []
            }
        else:
            entry = meters[m_id]
            entry["count"] += 1
            entry["last_seen"] = ts
            if vol is not None:
                entry["latest_vol"] = vol
                entry["volumes"].append(vol)

    print(f"[*] Total Unique Meters Heard: {len(meters)}")
    print("-" * 75)
    print(f"{'Meter ID':<12} | {'Proto':<6} | {'Packets':<8} | {'Initial Vol':<12} | {'Latest Vol':<12} | {'Target?'}")
    print("-" * 75)

    for m_id, data in sorted(meters.items(), key=lambda x: x[1]["count"], reverse=True):
        is_target = "🎯 YES!" if (TARGET_ID and TARGET_ID in m_id) else "No"
        print(f"{m_id:<12} | {data['protocol']:<6} | {data['count']:<8} | {str(data['initial_vol']):<12} | {str(data['latest_vol']):<12} | {is_target}")

    print("=" * 75)

    if TARGET_ID:
        if target_hits:
            print(f"\n🎉 TARGET METER {TARGET_ID} CONFIRMED! ({len(target_hits)} packets)")
            for h in target_hits:
                print(f"  - [{h.get('received_at')}] Reading: {h.get('packet', {}).get('Message', {}).get('Consumption')}")
        else:
            print(f"\n[i] Target Meter {TARGET_ID} was not heard among the {len(meters)} meters detected.")

    print("=" * 75)


if __name__ == "__main__":
    main()
