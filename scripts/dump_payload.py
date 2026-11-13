#!/usr/bin/env python3
"""
Inspect and decode raw payload from captured Dialog 3G CU8 files.
"""

import os
import glob
import numpy as np

def analyze_cu8(filename):
    print("=" * 60)
    print(f"Analyzing {filename}")
    raw = np.fromfile(filename, dtype=np.uint8)
    if len(raw) < 4000:
        return

    # IQ samples
    iq = (raw[0::2].astype(np.float32) - 127.5) + 1j * (raw[1::2].astype(np.float32) - 127.5)
    sample_rate = 1000000.0

    # Frequency demodulation
    phase = np.unwrap(np.angle(iq))
    freq = np.diff(phase) * (sample_rate / (2.0 * np.pi))

    # Low-pass filter (moving average)
    kernel_size = 5
    freq_filtered = np.convolve(freq, np.ones(kernel_size)/kernel_size, mode="same")

    # Slicer to binary
    bits = (freq_filtered > 0).astype(np.uint8)

    # Convert bit array to bitstring
    bit_str = "".join(str(b) for b in bits[::8]) # rough decimation
    
    print(f"Sample length: {len(iq)} samples ({len(iq)/sample_rate*1000:.1f} ms)")

if __name__ == "__main__":
    for f in sorted(glob.glob("/tmp/dialog3g_captures/*.cu8")):
        analyze_cu8(f)
