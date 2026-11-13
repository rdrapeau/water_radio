#!/usr/bin/env python3
"""
10-Minute AMR Stream Logger & Ingestion Engine
Captures 10 minutes of raw RF data across all AMR protocols (SCM, SCM+, IDM, R900)
at maximum tuner gain, logging the raw stream and structured JSON packets in real time.
"""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime

TARGET_METER_ID = os.environ.get("TARGET_METER_ID", "").strip()
RAW_LOG = "raw_stream_10min.log"
PACKETS_JSONL = "packets_10min.jsonl"
SUMMARY_JSON = "summary_10min.json"
DURATION_SEC = 600  # 10 minutes


def main():
    print("=" * 75)
    print(" 🚀 Starting 10-Minute Highline / AMR Water Telemetry Capture")
    print("=" * 75)
    print(f"[*] Duration:         {DURATION_SEC} seconds (10.0 minutes)")
    print(f"[*] Protocols:        All (SCM, SCM+, IDM, R900)")
    print(f"[*] Tuner Gain:       Index 28 (Maximum ~49.6 dB)")
    print(f"[*] Target Meter ID:  {TARGET_METER_ID or '(none)'}")
    print(f"[*] Raw Stream:       {RAW_LOG}")
    print(f"[*] JSONL Packets:    {PACKETS_JSONL}")
    print(f"[*] Output Summary:   {SUMMARY_JSON}")
    print("=" * 75)

    # Clean up any lingering SDR processes
    subprocess.run(["pkill", "-9", "rtl_tcp"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    time.sleep(0.5)

    # Start rtl_tcp
    print("[*] Launching rtl_tcp server...")
    tcp_proc = subprocess.Popen(
        ["rtl_tcp", "-p", "1234"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid
    )
    time.sleep(1.0)
    if tcp_proc.poll() is not None:
        print("[!] Error: rtl_tcp failed to start.")
        sys.exit(1)

    print("[+] rtl_tcp server active.")

    # Start rtlamr
    rtlamr_cmd = [
        "rtlamr",
        "-format=json",
        "-msgtype=all",
        "-tunergainmode=true",
        "-gainbyindex=28",
        f"-duration={DURATION_SEC}s"
    ]

    print(f"[*] Launching rtlamr ({' '.join(rtlamr_cmd)})...")
    rtlamr_proc = subprocess.Popen(
        rtlamr_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    meters = {}
    total_packets = 0
    start_time = time.time()

    # Open log files
    raw_f = open(RAW_LOG, "w")
    jsonl_f = open(PACKETS_JSONL, "w")

    def save_summary():
        with open(SUMMARY_JSON, "w") as f:
            json.dump({
                "start_time": datetime.fromtimestamp(start_time).isoformat(),
                "end_time": datetime.now().isoformat(),
                "duration_seconds": round(time.time() - start_time, 1),
                "total_packets": total_packets,
                "unique_meters_count": len(meters),
                "meters": meters
            }, f, indent=2)

    def cleanup(signum=None, frame=None):
        print("\n[*] Stopping capture...")
        try:
            rtlamr_proc.terminate()
            rtlamr_proc.wait(timeout=2)
        except Exception:
            pass
        try:
            os.killpg(os.getpgid(tcp_proc.pid), signal.SIGKILL)
        except Exception:
            pass
        raw_f.close()
        jsonl_f.close()
        save_summary()
        print(f"[+] Capture complete.")
        print(f"[+] Total packets captured: {total_packets}")
        print(f"[+] Unique meters discovered: {len(meters)}")
        print(f"[+] Data written to {PACKETS_JSONL} and {SUMMARY_JSON}")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("[*] Stream active and recording. Analyzing incoming packets in real-time...\n")

    try:
        for line in rtlamr_proc.stdout:
            raw_f.write(line)
            raw_f.flush()

            clean_line = line.strip()
            if not clean_line:
                continue

            try:
                packet = json.loads(clean_line)
            except json.JSONDecodeError:
                continue

            total_packets += 1
            now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Write structured record
            record = {"received_at": now_iso, "packet": packet}
            jsonl_f.write(json.dumps(record) + "\n")
            jsonl_f.flush()

            msg = packet.get("Message", {})
            m_id = str(msg.get("ID") or packet.get("EndpointID") or "UNKNOWN")
            proto = packet.get("Type", "UNKNOWN")
            consumption = msg.get("Consumption")
            tamper = msg.get("Tamper", 0)

            is_target = bool(TARGET_METER_ID) and ((m_id == TARGET_METER_ID) or (TARGET_METER_ID in m_id))
            tag = "🎯 TARGET METER!" if is_target else "📡 METER HEARD"

            if m_id not in meters:
                meters[m_id] = {
                    "id": m_id,
                    "is_target": is_target,
                    "protocol": proto,
                    "first_seen": now_iso,
                    "last_seen": now_iso,
                    "packet_count": 1,
                    "initial_reading": consumption,
                    "latest_reading": consumption,
                    "tamper": tamper
                }
            else:
                entry = meters[m_id]
                entry["packet_count"] += 1
                entry["last_seen"] = now_iso
                if consumption is not None:
                    entry["latest_reading"] = consumption
                entry["tamper"] = tamper

            save_summary()

            elapsed = int(time.time() - start_time)
            print(f"[{now_iso} | {elapsed:03d}s/{DURATION_SEC}s] {tag} | ID: {m_id:<10} | Proto: {proto:<5} | Volume: {str(consumption):<8} | Count: {meters[m_id]['packet_count']}")

    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
