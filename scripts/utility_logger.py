#!/usr/bin/env python3
"""
Continuous Municipal Water & Gas Utility Logger
Alternates between rtl_433 (Arad Dialog3G, Badger ORION, Neptune, PSE Gridstream)
and rtlamr (Itron SCM/SCM+/IDM Gas & Water) in a continuous loop.
Logs all readings to utility_readings.jsonl, utility_meters.json, and utility_readings.log.
"""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime

PACKETS_FILE = "utility_readings.jsonl"
METERS_FILE = "utility_meters.json"
STREAM_LOG = "utility_readings.log"

# Cycle durations in seconds
RTL433_DURATION = 120   # 2 minutes on 916.1M / 915M
RTLAMR_DURATION = 120   # 2 minutes on 912.6M


def classify_meter(model_or_type, raw_type=None):
    """Classify device into Water, Gas, Electric, or Other."""
    name = str(model_or_type).lower()
    if any(w in name for w in ["water", "arad", "dialog3g", "orion", "neptune", "r900", "flowis"]):
        return "Water"
    if "gas" in name:
        return "Gas"
    if "electric" in name or "gridstream" in name:
        return "Electric"

    # rtlamr numeric message types: 4=water, 2/12=gas, 7=electric
    if raw_type == 4:
        return "Water"
    elif raw_type in [2, 12]:
        return "Gas"
    elif raw_type == 7:
        return "Electric"

    return "Utility"


def load_meters():
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


def log_packet(source, packet_data, meters, pf, logf):
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Extract common fields
    meter_id = "UNKNOWN"
    meter_kind = "Utility"
    protocol = source
    reading = None
    unit = None
    extra = {}

    if source == "rtlamr":
        msg = packet_data.get("Message", {})
        meter_id = str(msg.get("ID") or packet_data.get("EndpointID") or "UNKNOWN")
        raw_type = msg.get("Type")
        protocol = f"Itron-{packet_data.get('Type', 'ERT')}"
        meter_kind = classify_meter(protocol, raw_type)
        reading = msg.get("Consumption")
        unit = "units"
        extra = {"tamper": msg.get("Tamper", 0), "type_code": raw_type}

    elif source == "rtl_433":
        model = packet_data.get("model", "unknown")
        meter_id = str(packet_data.get("id") or packet_data.get("Serial No") or packet_data.get("Source Meter ID") or "UNKNOWN")
        protocol = model
        meter_kind = classify_meter(model)

        # Volume / reading extraction
        for key in ["volume_m3", "volume", "waterread", "consumption", "reading"]:
            if key in packet_data and packet_data[key] is not None:
                reading = packet_data[key]
                unit = packet_data.get("unit", "m3" if "m3" in key else "gal")
                break

        extra = {
            "rssi": packet_data.get("rssi"),
            "snr": packet_data.get("snr"),
            "freq": packet_data.get("freq1"),
            "provider": packet_data.get("provider")
        }

    # Record to JSONL
    record = {
        "timestamp": now_iso,
        "source": source,
        "kind": meter_kind,
        "meter_id": meter_id,
        "protocol": protocol,
        "reading": reading,
        "unit": unit,
        "extra": extra,
        "raw": packet_data
    }
    pf.write(json.dumps(record) + "\n")
    pf.flush()

    # Update meter registry
    is_new = meter_id not in meters
    if is_new:
        meters[meter_id] = {
            "id": meter_id,
            "kind": meter_kind,
            "protocol": protocol,
            "first_seen": now_iso,
            "last_seen": now_iso,
            "count": 1,
            "initial_reading": reading,
            "latest_reading": reading,
            "unit": unit,
            "provider": extra.get("provider")
        }
    else:
        entry = meters[meter_id]
        entry["count"] += 1
        entry["last_seen"] = now_iso
        if reading is not None and reading != 0:
            entry["latest_reading"] = reading
        if extra.get("provider"):
            entry["provider"] = extra.get("provider")

    save_meters(meters)

    tag = "⭐ NEW" if is_new else "📡 UPDATE"
    read_str = f"{reading} {unit}" if reading is not None else "telemetry"
    log_line = f"[{now_iso}] {tag} | [{meter_kind:<8}] ID: {meter_id:<12} | Proto: {protocol:<20} | Read: {read_str}"
    print(log_line)
    logf.write(log_line + "\n")
    logf.flush()


def run_rtl433_cycle(duration, meters, pf, logf):
    """Run rtl_433 sweeping water and gas frequencies."""
    cmd = [
        "rtl_433",
        "-T", str(duration),
        "-f", "916.1M",
        "-f", "915.0M",
        "-H", "30",
        "-M", "level",
        "-F", "json"
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors="replace", bufsize=1)
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            log_packet("rtl_433", data, meters, pf, logf)
        except Exception:
            pass
    proc.wait()


def run_rtlamr_cycle(duration, meters, pf, logf):
    """Run rtlamr capturing Itron SCM/SCM+/IDM water and gas packets."""
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
        "-msgtype=all",
        "-tunergainmode=true",
        "-gainbyindex=28",
        f"-duration={duration}s"
    ]

    try:
        proc = subprocess.Popen(rtlamr_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors="replace", bufsize=1)
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                log_packet("rtlamr", data, meters, pf, logf)
            except Exception:
                pass
        proc.wait()
    finally:
        try:
            os.killpg(os.getpgid(tcp_proc.pid), signal.SIGKILL)
        except Exception:
            pass
        subprocess.run(["pkill", "-9", "rtl_tcp"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        time.sleep(0.5)


def main():
    print("=" * 78)
    print(" 📡 Continuous Municipal Water & Gas Utility Radio Ingestion")
    print("=" * 78)
    print(f"[*] JSONL Stream:   {PACKETS_FILE}")
    print(f"[*] Meter Registry: {METERS_FILE}")
    print(f"[*] Log Stream:     {STREAM_LOG}")
    print(f"[*] Cycles:         rtl_433 ({RTL433_DURATION}s) <---> rtlamr ({RTLAMR_DURATION}s)")
    print("=" * 78)

    meters = load_meters()
    pf = open(PACKETS_FILE, "a")
    logf = open(STREAM_LOG, "a")

    def cleanup(signum=None, frame=None):
        print("\n[*] Shutting down utility logger...")
        subprocess.run(["pkill", "-9", "rtl_tcp"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        subprocess.run(["pkill", "-9", "rtlamr"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        subprocess.run(["pkill", "-9", "rtl_433"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        save_meters(meters)
        pf.close()
        logf.close()
        print(f"[+] Total unique meters in registry: {len(meters)}")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    cycle_count = 0
    while True:
        cycle_count += 1
        print(f"\n--- [Cycle #{cycle_count}] Phase 1: Water & Grid Radio (rtl_433 @ 916.1M/915M) ---")
        run_rtl433_cycle(RTL433_DURATION, meters, pf, logf)

        print(f"\n--- [Cycle #{cycle_count}] Phase 2: Gas & ERT Radio (rtlamr @ 912.6M) ---")
        run_rtlamr_cycle(RTLAMR_DURATION, meters, pf, logf)


if __name__ == "__main__":
    main()
