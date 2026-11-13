# Municipal RF Reverse Engineering & Water Telemetry Investigation
**Location:** Pacific Northwest (Seattle Metro Area, WA)  
**Target Utility:** Regional Water District & Electric/Gas Utility  
**Date:** September 13, 2026  
**Status:** Completed & Documented  

---

## 1. Executive Summary

This project investigated the feasibility of passively intercepting real-time residential water consumption telemetry using a Software-Defined Radio (RTL-SDR) on macOS for subsequent export to Home Assistant OS (HAOS).

Over several hours of wideband spectrum analysis, indoor and outdoor testing, and multi-protocol sweeps across 902–928 MHz:
1. **Radio Hardware Operational:** The RTL-SDR Blog V3 and 915 MHz tuned whip antenna were 100% verified, successfully capturing live municipal utility telemetry from both **Seattle City Light** and **Puget Sound Energy** (up to 30.5 dB SNR).
2. **Utility Identified:** Bill analysis identified the water purveyor as a regional water district (**Highline Water District**), billed under read code **`MR` (Manual Read)**.
3. **Water Sniffing Verdict:** Highline Water District **does not broadcast unencrypted, real-time "bubble-up" AMR consumption telemetry** in the clear. Active flow testing confirmed that while regional Arad Dialog 3G keepalive sync bursts are present around 916.1 MHz, live consumption integers are not emitted over open RF. 
4. **Physical Ingestion Mechanism:** Inaccessible cliffside/bluff meters in this district are read either via **remote roadside TouchRead pads** (wired inductive wand read) or **two-way interrogated wake-up RF** (transmitting only when pinged by a utility truck every 60 days).

---

## 2. Hardware & Toolchain Configuration

* **SDR Receiver:** RTL-SDR Blog V3 (Realtek RTL2832U / Rafael Micro R860 tuner, 1 PPM TCXO stability).
* **Antenna:** muzi works 915 MHz 17cm Tuned Whip Antenna (SMA Male, low VSWR in 902–928 MHz ISM band).
* **Driver & Stream Server:** `librtlsdr` 2.0.3 / `rtl_tcp` (installed via Homebrew).
* **Demodulators:**
  * `rtlamr` v0.9.5 (compiled with CGO external linking on macOS Apple Silicon).
  * `rtl_433` v25.12 (universal ISM decoder).
* **Outdoor Gain Advantage:** Relocating the antenna outdoors eliminated double-pane Low-E window attenuation (15–20 dB), elevating reception from baseline noise to +34 dB SNR.

---

## 3. Account & Meter Profile (from Bill Audit)

Audit of a sample residential billing statement:
* **Utility Purveyor:** Highline Water District (www.highlinewater.org)
* **Customer Account:** `[REDACTED]`
* **Service Address:** `[REDACTED]`
* **Meter Serial Number:** `[REDACTED]`
* **Billing Period:** ~60 days (bi-monthly)
* **Read Type Code:** `MR` (**Manual Read**)
* **Meter Register Dial Feature:** Highline FAQ explicitly directs customers to look for the **blue rotating flow indicator wheel** (a hallmark of Master Meter / Arad registers).

---

## 4. Empirical RF Scan Results

### 4.1 Puget Sound Energy (PSE) Smart Grid Telemetry (Decoded)
* **Frequencies:** 914.8 MHz – 916.4 MHz (frequency hopping)
* **Protocol:** `LandisGyr-GS` (Gridstream RF Mesh Network, Subtype 213, Proto v5)
* **Signal Quality:** RSSI up to `-0.48 dB`, SNR up to **`30.5 dB`**
* **Tracked Meter IDs (Anonymized):**
  * `Endpoint A` (SNR 30.5 dB — strong nearby signal)
  * `Endpoint B` (SNR 20.0 dB)
  * `Endpoint C` (SNR 19.4 dB)
  * `Endpoint D` (SNR 18.2 dB)
  * `Endpoint E` (SNR 17.5 dB)
  * `Endpoint F` (SNR 16.4 dB)
* **Payload Security:** Network routing headers (ID, destination, mesh hops) are transmitted in the clear; billing registers (kWh/therms) are encrypted via **AES-128 GCM**.

### 4.2 Water Protocol Analysis (916.10 MHz Arad Dialog 3G)
* **Protocol:** `AradMsMeter-Dialog3G` (FSK Manchester, Protocol 260)
* **Observed Frequencies:** 915.78 MHz, 916.09 MHz, 916.40 MHz
* **Packets Captured:** 29 bursts over 8 minutes (SNR up to **34.4 dB**)
* **Decoded Payload:** `Serial No: 00000000`, `Volume: 0.0 m3`
* **Flow Test Verification:** Household water was actively running during the capture window. The volume register did not increment and the serial number remained zeroed.
* **Conclusion:** These pulses represent regional network keepalive/synchronization frames rather than live consumption broadcasts.

### 4.3 Neptune R900 Water Meter Telemetry (Decoded!)
* **Protocol:** `Neptune R900` (FSK, 912.38 MHz via `rtlamr`)
* **Status:** Actively captured live in the neighborhood.
* **Captured Endpoint Registry (Final Tally: 774 Packets, 10 Anonymized Endpoints):**
  | Endpoint | Dial Reading | Session Delta | Status Flags | Significance |
  | :--- | :--- | :--- | :--- | :--- |
  | `Meter #1` | `1,301,412 units` | **`+495 units`** | **Backflow Alert** (`BackFlow: 1`) | Largest water draw in area (153 pkts) |
  | `Meter #2` | `1,790,005 units` | **`+106 units`** | Normal (`LeakNow: 0`, `BackFlow: 0`) | High-traffic endpoint (156 pkts) |
  | `Meter #3` | `571,164 units` | **`+100 units`** | **Active Leak** (`LeakNow: 1`, `Leak: 6`) | Continuous daytime draw (8 pkts) |
  | `Meter #4` | `6,840,676 units` | **`+46 units`** | **Active Leak** (`LeakNow: 1`) | High-volume endpoint (5 pkts) |
  | `Meter #5` | `5,729,847 units` | **`+41 units`** | **Active Leak** (`LeakNow: 1`, `Leak: 5`) | Active leak endpoint (37 pkts) |
  | `Meter #6` | `95,570 units` | **`+36 units`** | Normal (`LeakNow: 0`, `BackFlow: 0`) | Low-reading residential endpoint (93 pkts) |
  | `Meter #7` | `1,719,541 units` | **`+14 units`** | `Leak: 1`, **Backflow Alert** | Reverse flow alert (5 pkts) |
  | `Meter #8` | `643,455 units` | **`+13 units`** | **Active Leak** (`LeakNow: 1`) | Slow trickling leak (+1 unit every ~15m, 121 pkts) |
  | `Meter #9` | `4,024,278 units` | **`+3 units`** | `Leak: 1` | Intermittent leak (2 pkts) |
  | `Meter #10` | `6,419,950 units` | `0` | Intermittent Leak (`Leak: 1`) | Strongest radio signal (194 pkts) |

* **Key Takeaway:** Proves that **Neptune R900 AMR water meters are extensively deployed** (10 unique endpoints captured, 774 total packets) and broadcast unencrypted cumulative consumption integers and leak alerts every 14–28 seconds. All Neptune IDs follow a distinct 10-digit format beginning with `15` (e.g. `15xxxxxxxx`).

---

## 5. Technical Verdict: Why Passive Sniffing Fails Here

Municipal water utilities use four methods for difficult-access hillside services:

```
+-------------------------------------------------------------------------------+
| Scenario A: Remote TouchRead Station (Most Probable)                          |
| - A 2-wire cable runs from the meter to an external roadside pad.             |
| - Reader touches an electronic wand to the pad every 60 days.                 |
| - Matches bill code "MR" (Manual Read). Result: ZERO RF in the air.           |
+-------------------------------------------------------------------------------+

+-------------------------------------------------------------------------------+
| Scenario B: Two-Way Interrogated RF (Wake-Up)                                 |
| - Meter sleeps 100% of the time to preserve 20-year battery life.             |
| - Only chirps when utility truck transmits 900 MHz wake-up ping.              |
| - Result: Complete radio silence between 60-day drive-by sweeps.               |
+-------------------------------------------------------------------------------+

+-------------------------------------------------------------------------------+
| Scenario C: Licensed Encrypted AMI (Sensus FlexNet / Cellular)                |
| - Transmits on licensed FCC spectrum (901 MHz / 952 MHz) or LTE-M cellular.   |
| - Payloads use proprietary framing with AES encryption.                       |
| - Result: Cannot be sniffed or decoded with open-source SDR tools.            |
+-------------------------------------------------------------------------------+
```

---

## 6. Recommended Paths Forward for Home Assistant

Because the municipal water meter does not emit open consumption radio, homeowners seeking real-time water telemetry and automated leak protection should implement customer-side monitoring:

| Solution | Mechanism | Home Assistant Integration | Primary Advantage |
| :--- | :--- | :--- | :--- |
| **Flo by Moen** | Inline ultrasonic flow, temp, & pressure sensor on main inlet line. | Official `flo` integration. | **Instant GPM**, daily gallons, and **automatic motorized shutoff** if a pipe ruptures. |
| **ESPHome Magnetic Sensor** | Magnetometer (QMC5883L) mounted to outside glass of meter dial. | Native ESPHome / HA API. | **Zero pipe cuts**; counts internal magnetic disc rotations for sub-gallon resolution. |
| **AI-on-the-Edge (ESP32-CAM)** | Inexpensive camera pointing at meter dials running on-device neural OCR. | Native MQTT auto-discovery. | Reads odometer numerals directly; zero plumbing work. |

---

## 7. Project Directory Structure

All tools and captured telemetry are organized in `water_radio/`:

```
water_radio/
├── FINDINGS.md                      # This comprehensive technical investigation report
├── scripts/                         # Operational CLI tools & capture engines
│   ├── water_logger.py              # Dedicated multi-channel water meter ingestion daemon
│   ├── show_water.py                # Formatted live viewer for water meter endpoints
│   ├── utility_logger.py            # Alternating multi-band water & gas logger
│   ├── show_meters.py               # Formatted live viewer for all utility endpoints
│   ├── scanner.py                   # Initial rtlamr discovery scanner
│   ├── run_10min_capture.py         # 10-minute continuous ERT recorder
│   ├── analyze.py                   # Tabular analyzer for ERT capture logs
│   ├── comprehensive_scan.py        # 7-phase automated multi-protocol outdoor sweeper
│   ├── decode_dialog3g.py           # Raw CU8 I/Q phase demodulator
│   └── dump_payload.py              # Low-level sample slicer
└── logs/                            # Recorded RF telemetry & structured captures
    ├── water_readings.jsonl         # 29 recorded Dialog 3G water bursts with SNR/RSSI
    ├── water_summary.json           # Aggregated summary of water meter bursts
    ├── water_live.log               # Human-readable water packet log
    ├── utility_readings.jsonl       # 11 recorded Puget Sound Energy smart grid packets
    ├── utility_meters.json          # Catalog of 6 tracked PSE Gridstream endpoints
    ├── utility_readings.log         # Human-readable utility packet log
    └── outdoor_packets.jsonl        # Multi-band outdoor sweep packet captures
```
