#!/usr/bin/env python3
"""
Comprehensive Outdoor Multi-Band AMR / Utility Meter Scanner
Systematically scans all major North American water, gas, and electric meter
protocols and center frequencies, logging all packets and signals.
"""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime

RESULTS_FILE = "outdoor_scan_results.json"
PACKETS_FILE = "outdoor_packets.jsonl"
TARGET_METER_ID = os.environ.get("TARGET_METER_ID", "").strip()

# Scan profiles: (name, tool, cmd_args, duration_seconds, description)
PROFILES = [
    {
        "name": "Master Meter / Dialog 3G",
        "tool": "rtl_433",
        "freq": "916.30 MHz",
        "duration": 45,
        "args": ["-f", "916.3M", "-R", "260", "-M", "level", "-F", "json"],
        "description": "Arad / Master Meter Dialog3G water meter (916.3 MHz)"
    },
    {
        "name": "Universal 915 MHz ISM Suite",
        "tool": "rtl_433",
        "freq": "915.00 MHz",
        "duration": 90,
        "args": ["-f", "915M", "-M", "level", "-F", "json"],
        "description": "All 915 MHz municipal utility & sensor decoders (915.0 MHz)"
    },
    {
        "name": "Universal 920 MHz High-Band Suite",
        "tool": "rtl_433",
        "freq": "920.00 MHz",
        "duration": 60,
        "args": ["-f", "920M", "-M", "level", "-F", "json"],
        "description": "Upper ISM band utility decoders (920.0 MHz)"
    },
    {
        "name": "Wideband Pulse Analyzer",
        "tool": "rtl_433",
        "freq": "915.00 MHz",
        "duration": 45,
        "args": ["-f", "915M", "-A"],
        "description": "Raw FSK/OOK pulse detection and preamble extraction"
    }
]


def cleanup_processes():
    subprocess.run(["pkill", "-9", "rtl_tcp"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "rtlamr"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "rtl_433"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    time.sleep(0.5)


def run_rtlamr_profile(profile, packets_out, results):
    freq_arg = []
    if "912.85" in profile["freq"]:
        freq_arg = ["-centerfreq=912850000"]
    elif "912.38" in profile["freq"]:
        freq_arg = ["-centerfreq=912380000"]

    # Start rtl_tcp
    tcp_proc = subprocess.Popen(
        ["rtl_tcp", "-p", "1234"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid
    )
    time.sleep(1.2)

    rtlamr_cmd = [
        "rtlamr",
        "-format=json",
        f"-msgtype={profile['protocol']}",
        "-tunergainmode=true",
        "-gainbyindex=28",
        f"-duration={profile['duration']}s"
    ] + freq_arg

    packets_found = 0
    try:
        proc = subprocess.Popen(rtlamr_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors="replace", bufsize=1)
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                pkt = json.loads(line)
                packets_found += 1
                record = {
                    "timestamp": datetime.now().isoformat(),
                    "profile": profile["name"],
                    "frequency": profile["freq"],
                    "data": pkt
                }
                packets_out.write(json.dumps(record) + "\n")
                packets_out.flush()

                msg = pkt.get("Message", {})
                m_id = str(msg.get("ID") or pkt.get("EndpointID") or "UNKNOWN")
                proto = pkt.get("Type", "UNKNOWN")
                vol = msg.get("Consumption")
                hit = "🎯 TARGET!" if (TARGET_METER_ID and (m_id == TARGET_METER_ID or TARGET_METER_ID in m_id)) else "📡 DECODED"
                print(f"    [{datetime.now().strftime('%H:%M:%S')}] {hit} | ID: {m_id:<10} | {proto:<5} | Vol: {str(vol):<8}")
            except Exception:
                pass
        proc.wait()
    finally:
        try:
            os.killpg(os.getpgid(tcp_proc.pid), signal.SIGKILL)
        except Exception:
            pass
        cleanup_processes()

    return packets_found


def run_rtl433_profile(profile, packets_out, results):
    cmd = ["rtl_433", "-T", str(profile["duration"])] + profile["args"]
    packets_found = 0

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace", bufsize=1)
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        if "-A" in profile.get("args", []):
            if "Detected FSK" in line or "Detected OOK" in line or "codes" in line or "RSSI" in line:
                print(f"    [PULSE] {line[:90]}")
            continue

        try:
            pkt = json.loads(line)
            packets_found += 1
            record = {
                "timestamp": datetime.now().isoformat(),
                "profile": profile["name"],
                "frequency": profile["freq"],
                "data": pkt
            }
            packets_out.write(json.dumps(record) + "\n")
            packets_out.flush()

            model = pkt.get("model", "unknown")
            dev_id = str(pkt.get("id") or pkt.get("Source Meter ID") or pkt.get("Meter ID") or "N/A")
            rssi = pkt.get("rssi", "N/A")
            hit = "🎯 TARGET!" if (TARGET_METER_ID and TARGET_METER_ID in dev_id) else "📡"
            print(f"    [{datetime.now().strftime('%H:%M:%S')}] {hit} {model} | ID: {dev_id} | RSSI: {rssi} dB")
        except Exception:
            pass

    proc.wait()
    cleanup_processes()
    return packets_found


def main():
    print("=" * 78)
    print(" 📡 Comprehensive Multi-Band Outdoor AMR / Smart Meter Sweeper")
    print("=" * 78)
    print(f"[*] Target Meter ID:    {TARGET_METER_ID or '(none)'}")
    print(f"[*] Number of Profiles: {len(PROFILES)}")
    total_est = sum(p['duration'] for p in PROFILES)
    print(f"[*] Total Est. Runtime: {total_est} seconds (~{round(total_est / 60, 1)} minutes)")
    print(f"[*] Output Files:       {RESULTS_FILE}, {PACKETS_FILE}")
    print("=" * 78)

    cleanup_processes()
    results = {
        "start_time": datetime.now().isoformat(),
        "profiles_run": []
    }

    with open(PACKETS_FILE, "a") as packets_out:
        for idx, prof in enumerate(PROFILES, 1):
            print(f"\n[{idx}/{len(PROFILES)}] ▶ Running: {prof['name']} ({prof['freq']}) for {prof['duration']}s")
            print(f"       Description: {prof['description']}")

            start_t = time.time()
            if prof["tool"] == "rtlamr":
                pkts = run_rtlamr_profile(prof, packets_out, results)
            else:
                pkts = run_rtl433_profile(prof, packets_out, results)
            elapsed = round(time.time() - start_t, 1)

            prof_result = {
                "profile": prof["name"],
                "frequency": prof["freq"],
                "duration_seconds": elapsed,
                "packets_captured": pkts
            }
            results["profiles_run"].append(prof_result)
            print(f"       ✓ Finished in {elapsed}s | Packets decoded: {pkts}")

    results["end_time"] = datetime.now().isoformat()
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 78)
    print(" 🏁 Comprehensive Outdoor Sweep Completed!")
    print("=" * 78)
    print(f"[+] Summary saved to {RESULTS_FILE}")
    print(f"[+] Detailed packet logs saved to {PACKETS_FILE}")


if __name__ == "__main__":
    main()
