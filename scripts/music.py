#!/usr/bin/env python3
"""Generate a soft, royalty-free ambient music bed (original, made by code).

  python scripts/music.py out.wav --seconds 32 [--seed 1]

Calm minor-key pad (Am - F - C - G) with a gentle pluck on each beat, made only
from synthesised waves, so there is no licence question. If brand/audio/bed.wav
exists, revoice.py uses that instead (drop a licensed track there to override).
"""
import argparse, wave
import numpy as np

SR = 44100
CHORDS = [  # Am, F, C, G (Hz, mid register)
    [220.00, 261.63, 329.63],
    [174.61, 220.00, 261.63],
    [196.00, 261.63, 329.63],
    [196.00, 246.94, 293.66],
]


def env(n, attack, release):
    e = np.ones(n)
    a, r = int(attack * SR), int(release * SR)
    e[:a] = np.linspace(0, 1, a)
    e[-r:] = np.linspace(1, 0, r)
    return e


def pad(freqs, dur):
    t = np.arange(int(dur * SR)) / SR
    s = np.zeros_like(t)
    for f in freqs:
        for detune in (-0.6, 0.6):           # slight chorus
            s += np.sin(2 * np.pi * (f + detune) * t)
        s += 0.3 * np.sin(2 * np.pi * f / 2 * t)  # sub octave
    return s / (len(freqs) * 2.3) * env(len(t), 0.8, 0.9)


def pluck(f, dur=0.6):
    t = np.arange(int(dur * SR)) / SR
    return np.sin(2 * np.pi * f * 2 * t) * np.exp(-t * 7)


def make(seconds, seed):
    rng = np.random.default_rng(seed)
    bar = 4 * 60 / 84               # 84 bpm, 4 beats per chord
    total = int(seconds * SR)
    out = np.zeros(total + SR * 2)
    i, pos = 0, 0
    while pos < total:
        ch = CHORDS[i % len(CHORDS)]
        p = pad(ch, bar + 1.0)
        out[pos:pos + len(p)] += 0.55 * p
        for beat in range(4):
            b = pos + int(beat * bar / 4 * SR)
            pl = pluck(ch[rng.integers(0, 3)]) * (0.18 if beat else 0.24)
            out[b:b + len(pl)] += pl
        pos += int(bar * SR)
        i += 1
    out = out[:total]
    # gentle low-pass (moving average) and fades
    k = 9
    out = np.convolve(out, np.ones(k) / k, mode="same")
    out *= env(total, 1.0, 1.5)
    out /= np.max(np.abs(out)) + 1e-9
    stereo = np.stack([out, np.roll(out, 220)], axis=1) * 0.7
    return (stereo * 32767).astype(np.int16)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=32)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    data = make(a.seconds, a.seed)
    with wave.open(a.out, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(data.tobytes())


if __name__ == "__main__":
    main()
