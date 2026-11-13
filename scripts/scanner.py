#!/usr/bin/env python3
"""
AMR Water Meter Scanner & Telemetry Collector
Spawns rtl_tcp and rtlamr, captures packets, formats them in real time,
and logs unique meters to meters.json and all raw packets to packets.jsonl.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime

METERS_FILE = "meters.json"
PACKETS_FILE = "packets.jsonl"


def print_banner():
    print("=" * 70)
    print(" 📡  AMR Water Meter RF Scanner (915 MHz ISM Band)")
    print("=" * 70)


def start_rtl_tcp(gain=None, port=1234):
    cmd = ["rtl_tcp", "-p", str(port)]
    if gain is not None:
        cmd.extend(["-g", str(gain)])
    
    # Suppress verbose raw spectrum logs from rtl_tcp
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid
    )
    time.sleep(1.0)
    if proc.poll() is not None:
        raise RuntimeError("Failed to start rtl_tcp. Is another instance already running or is the RTL-SDR in use?")
    return proc


def load_existing_meters():
    if os.path.exists(METERS_FILE):
        try:
            with open(METERS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_meters(meters):
    with open(METERS_FILE, "w") as f:
        json.dump(meters, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Scan and monitor AMR water/gas meters using RTL-SDR.")
    parser.add_argument("--msgtype", default="all", help="Protocols to decode: all, scm, scm+, idm, r900 (default: all)")
    parser.add_argument("--gain-index", type=int, default=25, help="Tuner gain index (0-28, default: 25)")
    parser.add_argument("--filter-id", help="Filter by specific meter ID (comma-separated)")
    parser.add_argument("--center-freq", type=int, help="Center frequency in Hz (e.g. 912600155)")
    parser.add_argument("--symbol-length", type=int, default=72, help="Symbol length (default: 72)")
    parser.add_argument("--duration", help="Run duration (e.g., 60s, 5m, 1h). Default: indefinite")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print debug logs from rtlamr")
    args = parser.parse_args()

    print_banner()
    print(f"[*] Protocols:    {args.msgtype}")
    print(f"[*] Gain Index:   {args.gain_index} (~43 dB)")
    if args.filter_id:
        print(f"[*] Filter ID:    {args.filter_id}")
    print(f"[*] Packets log:  {PACKETS_FILE}")
    print(f"[*] Meters log:   {METERS_FILE}")
    print("=" * 70)

    # Clean up any orphan rtl_tcp
    subprocess.run(["pkill", "-9", "rtl_tcp"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    time.sleep(0.5)

    print("[*] Starting rtl_tcp server...")
    tcp_proc = start_rtl_tcp()
    print("[+] rtl_tcp server running.")

    rtlamr_cmd = [
        "rtlamr",
        "-format=json",
        f"-msgtype={args.msgtype}",
        "-tunergainmode=true",
        f"-gainbyindex={args.gain_index}",
        f"-symbollength={args.symbol_length}",
    ]
    if args.filter_id:
        rtlamr_cmd.append(f"-filterid={args.filter_id}")
    if args.center_freq:
        rtlamr_cmd.append(f"-centerfreq={args.center_freq}")
    if args.duration:
        rtlamr_cmd.append(f"-duration={args.duration}")

    print(f"[*] Launching rtlamr...")
    rtlamr_proc = subprocess.Popen(
        rtlamr_cmd,
        stdout=subprocess.PIPE,
        stderr=None if args.verbose else subprocess.DEVNULL,
        text=True,
        bufsize=1
    )

    meters = load_existing_meters()
    total_packets = 0

    def cleanup(signum=None, frame=None):
        print("\n[*] Shutting down scanner...")
        try:
            rtlamr_proc.terminate()
            rtlamr_proc.wait(timeout=2)
        except Exception:
            pass
        try:
            os.killpg(os.getpgid(tcp_proc.pid), signal.SIGKILL)
        except Exception:
            pass
        save_meters(meters)
        print(f"[+] Total packets captured: {total_packets}")
        print(f"[+] Total unique meters tracked: {len(meters)}")
        print(f"[+] Saved meter summary to {METERS_FILE}")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("[*] Listening for RF broadcasts... (Press Ctrl+C to stop)\n")

    try:
        for line in rtlamr_proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                packet = json.loads(line)
            except json.JSONDecodeError:
                continue

            total_packets += 1
            now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Append to packets file
            with open(PACKETS_FILE, "a") as pf:
                pf.write(json.dumps({"timestamp": now_iso, "packet": packet}) + "\n")

            msg = packet.get("Message", {})
            meter_id = str(msg.get("ID") or packet.get("EndpointID") or "UNKNOWN")
            proto = packet.get("Type", "UNKNOWN")
            consumption = msg.get("Consumption")
            tamper = msg.get("Tamper", 0)
            meter_type = msg.get("Type", 0)

            # Update meter database
            if meter_id not in meters:
                meters[meter_id] = {
                    "meter_id": meter_id,
                    "protocol": proto,
                    "meter_type": meter_type,
                    "first_seen": now_iso,
                    "last_seen": now_iso,
                    "packet_count": 1,
                    "consumption": consumption,
                    "tamper": tamper,
                }
                save_meters(meters)
                tag = "⭐ NEW METER"
            else:
                entry = meters[meter_id]
                entry["last_seen"] = now_iso
                entry["packet_count"] += 1
                if consumption is not None:
                    entry["consumption"] = consumption
                entry["tamper"] = tamper
                save_meters(meters)
                tag = "  HEARD    "

            print(f"[{now_iso}] {tag} | ID: {meter_id:<10} | Type: {proto:<5} | Volume: {str(consumption):<8} | Packets: {meters[meter_id]['packet_count']}")

    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
