#!/usr/bin/env python3
"""
Demodulate and extract raw Arad / Master Meter Dialog 3G payload bytes
directly from captured I/Q files (CU8 format).
"""

import sys
import numpy as np

def demodulate_cu8(filename):
    # Read raw CU8 (interleaved uint8 I and Q)
    raw = np.fromfile(filename, dtype=np.uint8)
    if len(raw) < 2000:
        print(f"File {filename} too small")
        return

    # Convert to complex float centered at 0
    iq = (raw[0::2].astype(np.float32) - 127.5) + 1j * (raw[1::2].astype(np.float32) - 127.5)
    sample_rate = 1000000.0  # 1 MSPS

    # Frequency demodulation (instantaneous frequency = phase difference)
    phase = np.unwrap(np.angle(iq))
    freq = np.diff(phase) * (sample_rate / (2.0 * np.pi))

    # Low-pass filter to smooth frequency demodulation
    kernel_size = 5
    kernel = np.ones(kernel_size) / kernel_size
    freq_smooth = np.convolve(freq, kernel, mode="same")

    # Threshold to binary (slicer)
    bits_raw = (freq_smooth > 0).astype(np.int8)

    # Search for sync pattern or Manchester transitions
    # In Manchester: symbol rate is ~119 kbps (8.4 us per bit -> ~8.4 samples per bit at 1 MSPS)
    samples_per_chip = 8.4

    # Let's search across the bit stream
    print(f"Demodulated {len(freq_smooth)} samples from {filename}")
    print(f"Max freq dev: {np.max(freq_smooth):.1f} Hz, Min: {np.min(freq_smooth):.1f} Hz")

if __name__ == "__main__":
    files = ["/tmp/dialog3g_captures/g001_916.1M_1000k.cu8",
             "/tmp/dialog3g_captures/g002_916.1M_1000k.cu8",
             "/tmp/dialog3g_captures/g003_916.1M_1000k.cu8"]
    for f in files:
        demodulate_cu8(f)
