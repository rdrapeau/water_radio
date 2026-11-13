#!/usr/bin/env python3
"""
Dedicated Continuous Neptune R900 Water Meter Radio Ingestion Engine
100% dedicated monitoring on 912.38 MHz via rtlamr and rtl_tcp.
Tracks cumulative consumption integers, real-time consumption deltas,
leak alerts, and backflow events.
"""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs") if os.path.exists(os.path.join(PROJECT_ROOT, "logs")) else "."

TARGET_METER_ID = os.environ.get("TARGET_METER_ID", "").strip()
WATER_PACKETS_FILE = os.path.join(LOGS_DIR, "water_readings.jsonl")
WATER_SUMMARY_FILE = os.path.join(LOGS_DIR, "water_summary.json")
WATER_LOG_FILE = os.path.join(LOGS_DIR, "water_live.log")

NEPTUNE_FREQ = "912380000"  # 912.38 MHz
TUNER_GAIN_IDX = "28"       # Maximum gain (~49.6 dB)


def cleanup_sdr():
    subprocess.run(["pkill", "-9", "rtl_tcp"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "rtlamr"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "rtl_433"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    time.sleep(0.5)


def load_summary():
    if os.path.exists(WATER_SUMMARY_FILE):
        try:
            with open(WATER_SUMMARY_FILE, "r") as f:
                data = json.load(f)
                # Ensure bogus 00000000 is excluded
                if "00000000" in data.get("meters", {}):
                    del data["meters"]["00000000"]
                return data
        except Exception:
            return {"meters": {}, "total_packets": 0, "session_start": datetime.now().isoformat()}
    return {"meters": {}, "total_packets": 0, "session_start": datetime.now().isoformat()}


def save_summary(summary):
    with open(WATER_SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)


def process_packet(pkt_data, summary, pf, logf):
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = pkt_data.get("Message", {})
    meter_id = str(msg.get("ID") or pkt_data.get("EndpointID") or "UNKNOWN")
    volume = msg.get("Consumption")
    unit = "units"
    raw_type = msg.get("Type")
    proto = f"Itron-{pkt_data.get('Type', 'R900')}"
    
    extra = {
        "leak_now": msg.get("LeakNow"),
        "leak": msg.get("Leak"),
        "backflow": msg.get("BackFlow"),
        "no_use": msg.get("NoUse"),
        "unkn1": msg.get("Unkn1"),
        "unkn3": msg.get("Unkn3"),
        "type_code": raw_type
    }

    summary["total_packets"] += 1
    meters = summary["meters"]

    is_target = bool(TARGET_METER_ID) and (meter_id == TARGET_METER_ID or TARGET_METER_ID in meter_id or meter_id == f"15{TARGET_METER_ID}")

    # Save packet record
    record = {
        "timestamp": now_iso,
        "source": "rtlamr",
        "meter_id": meter_id,
        "is_target": is_target,
        "protocol": proto,
        "volume": volume,
        "unit": unit,
        "extra": extra,
        "raw": pkt_data
    }
    pf.write(json.dumps(record) + "\n")
    pf.flush()

    # Track deltas
    delta = 0
    delta_str = ""
    is_new = meter_id not in meters

    if is_new:
        meters[meter_id] = {
            "id": meter_id,
            "is_target": is_target,
            "protocol": proto,
            "first_seen": now_iso,
            "last_seen": now_iso,
            "packet_count": 1,
            "initial_volume": volume,
            "latest_volume": volume,
            "unit": unit,
            "best_snr": None,
            "extra": extra
        }
    else:
        entry = meters[meter_id]
        entry["packet_count"] += 1
        entry["last_seen"] = now_iso
        prev_vol = entry.get("latest_volume")
        if volume is not None and prev_vol is not None and volume != prev_vol:
            delta = volume - prev_vol
            delta_str = f" [Δ {delta:+d} {unit}]"
        if volume is not None:
            entry["latest_volume"] = volume
        entry["extra"] = extra

    save_summary(summary)

    # Alerts and formatting
    alerts = []
    if extra.get("leak_now"):
        alerts.append("🚨 LEAK NOW")
    elif extra.get("leak"):
        alerts.append(f"Leak({extra.get('leak')})")
    if extra.get("backflow"):
        alerts.append("⚠️ BACKFLOW")
    alert_str = f"| {' '.join(alerts)}" if alerts else ""

    if is_target:
        tag = "🎯 TARGET METER!"
    elif delta > 0:
        tag = "🌊 WATER CONSUMED"
    elif is_new:
        tag = "✨ NEW WATER MTR"
    else:
        tag = "💧 NEPTUNE R900 "

    vol_display = f"{volume} {unit}{delta_str}" if volume is not None else "telemetry"
    log_msg = f"[{now_iso}] {tag} | ID: {meter_id:<12} | Read: {vol_display:<26} {alert_str}"
    print(log_msg)
    logf.write(log_msg + "\n")
    logf.flush()


def run_continuous(total_hours=5.0):
    print("=" * 90)
    print(" 💧 100% Dedicated Neptune R900 Water Telemetry Daemon (912.38 MHz)")
    print("=" * 90)
    print(f"[*] Target Meter ID:     {TARGET_METER_ID or '(none)'}")
    print(f"[*] Monitoring Freq:     {float(NEPTUNE_FREQ)/1e6:.2f} MHz (Neptune R900 Bubble-Up)")
    print(f"[*] Tuner Gain:          Index {TUNER_GAIN_IDX} (Maximum Sensitivity ~49.6 dB)")
    print(f"[*] Packets Log:         {WATER_PACKETS_FILE}")
    print(f"[*] Summary Registry:    {WATER_SUMMARY_FILE}")
    print(f"[*] Target Duration:     {total_hours:.1f} Hours Continuous")
    print("=" * 90)

    cleanup_sdr()
    summary = load_summary()
    pf = open(WATER_PACKETS_FILE, "a")
    logf = open(WATER_LOG_FILE, "a")

    def shutdown(signum=None, frame=None):
        print("\n[*] Stopping Neptune water daemon...")
        cleanup_sdr()
        save_summary(summary)
        pf.close()
        logf.close()
        print(f"[+] Total packets in session:  {summary['total_packets']}")
        print(f"[+] Total unique water meters: {len(summary['meters'])}")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    start_time = time.time()
    restarts = 0

    while True:
        elapsed = time.time() - start_time
        elapsed_hours = elapsed / 3600.0
        if elapsed_hours >= total_hours:
            print(f"\n[✓] 5-Hour monitoring window complete ({elapsed_hours:.2f}h). Exiting.")
            shutdown()

        cleanup_sdr()

        # Start rtl_tcp
        tcp_proc = subprocess.Popen(
            ["rtl_tcp", "-p", "1234"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid
        )
        time.sleep(1.5)

        rtlamr_cmd = [
            "rtlamr",
            "-format=json",
            "-msgtype=r900",
            f"-centerfreq={NEPTUNE_FREQ}",
            "-tunergainmode=true",
            f"-gainbyindex={TUNER_GAIN_IDX}",
            "-duration=0"  # Run indefinitely until stopped or restarted
        ]

        print(f"[{datetime.now().strftime('%H:%M:%S')} | {elapsed_hours:.2f}h/{total_hours:.1f}h] [*] RTLAMR streaming Neptune R900 on 912.38 MHz...")

        try:
            proc = subprocess.Popen(rtlamr_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors="replace", bufsize=1)
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    process_packet(data, summary, pf, logf)
                except Exception:
                    pass
                
                # Check elapsed time within stream
                if (time.time() - start_time) / 3600.0 >= total_hours:
                    break

            proc.wait()
        except Exception as e:
            print(f"[!] Stream error: {e}")
        finally:
            try:
                os.killpg(os.getpgid(tcp_proc.pid), signal.SIGKILL)
            except Exception:
                pass
            cleanup_sdr()

        restarts += 1
        print(f"[*] Stream cycled/restarted ({restarts} times). Resuming in 2s...")
        time.sleep(2)


if __name__ == "__main__":
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    run_continuous(dur)
