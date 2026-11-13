# Water Radio: AMR & Municipal RF Telemetry Project

Investigation, reverse engineering, and telemetry capture tools for municipal utility radio signals (902–928 MHz ISM band) using an RTL-SDR Blog V3 receiver on macOS.

---

## Quick Reference

* **Full Technical Investigation Report:** See [`FINDINGS.md`](./FINDINGS.md) for complete methodology, bill audit, frequency analyses, and Home Assistant alternative architectures.

### Directory Structure

```
water_radio/
├── FINDINGS.md            # Comprehensive project report & conclusions
├── scripts/               # Python CLI tools and background capture daemons
└── logs/                  # Captured RF telemetry, JSONL streams, and summaries
```

### Running the Tools

From the project root:

```bash
# View all captured water meter telemetry
./scripts/show_water.py

# View all captured municipal utility meters (PSE / SCL)
./scripts/show_meters.py

# Start the dedicated water meter logger (cycles 916.1M & 912.45M)
./scripts/water_logger.py

# Start the alternating water & gas utility logger
./scripts/utility_logger.py
```

---

## Hardware Used
* **SDR Receiver:** RTL-SDR Blog V3 (1 PPM TCXO SMA)
* **Antenna:** muzi works 915 MHz 17cm Tuned Whip Antenna
* **Target Band:** 902–928 MHz ISM (North America)
