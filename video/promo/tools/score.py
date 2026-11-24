#!/usr/bin/env python3
"""Original score for the AlgoArch film: futuristic ambient-electronic with a gradual build.
120 BPM (1 bar = 2 s) so every scene change (6, 15, 23, 34, 46, 54 s) and every montage cut
(46..53 s) lands on a beat. Pure numpy, deterministic (seeded)."""
import numpy as np, wave, sys, os
SR = 44100; DUR = 60.0; N = int(SR * DUR); BAR = 2.0; BEAT = 0.5
rng = np.random.default_rng(7)
Lb = np.zeros(N); Rb = np.zeros(N)          # dry bus
Lw = np.zeros(N); Rw = np.zeros(N)          # reverb send
mtof = lambda m: 440.0 * 2 ** ((m - 69) / 12)
def ramp(t, a, b): return float(np.clip((t - a) / (b - a), 0, 1))
def smooth(x): return x * x * (3 - 2 * x)

def put(sig, start, pan=0.0, gain=1.0, send=0.0):
    i = int(round(start * SR))
    if i >= N or i + len(sig) <= 0: return
    if i < 0: sig = sig[-i:]; i = 0
    j = min(N, i + len(sig)); s = sig[: j - i] * gain
    l = np.cos((pan + 1) * np.pi / 4); r = np.sin((pan + 1) * np.pi / 4)
    Lb[i:j] += s * l; Rb[i:j] += s * r
    if send: Lw[i:j] += s * l * send; Rw[i:j] += s * r * send

def saw_lp(f, dur, cutoff, K=28, detune=0.0):
    n = int(dur * SR); t = np.arange(n) / SR
    K = int(min(K, (SR / 2 - 200) / f)); fc = cutoff if np.ndim(cutoff) else np.full(n, cutoff)
    out = np.zeros(n); ph = rng.uniform(0, 2 * np.pi, K)
    for k in range(1, K + 1):
        a = (1.0 / k) / np.sqrt(1 + ((k * f) / fc) ** 4)
        out += a * np.sin(2 * np.pi * k * f * (1 + detune) * t + ph[k - 1])
    return out * 0.6

def env_ar(n, a, r):
    e = np.ones(n); na = int(a * SR); nr = int(r * SR)
    if na: e[:na] = np.sin(np.linspace(0, np.pi / 2, na)) ** 2
    if nr: e[-nr:] *= np.cos(np.linspace(0, np.pi / 2, nr)) ** 2
    return e

# ── voicings ──
V = {'Am': [57, 60, 64, 69], 'F': [53, 57, 60, 65], 'C': [55, 60, 64, 67], 'G': [55, 59, 62, 67],
     'Fmaj7': [53, 57, 60, 64], 'Cmaj7': [52, 55, 59, 64], 'Am9': [57, 60, 64, 71]}
BASS = {'Am': 33, 'F': 29, 'C': 36, 'G': 31, 'Fmaj7': 29, 'Cmaj7': 36, 'Am9': 33}
CYCLE = ['Am', 'F', 'C', 'G']
def chord_at_bar(b): return CYCLE[b % 4] if b < 27 else ['Fmaj7', 'Cmaj7', 'Am9'][b - 27]

# ── drums ──
def kick():
    n = int(0.42 * SR); t = np.arange(n) / SR
    f = 44 + 120 * np.exp(-t / 0.035); ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t / 0.17) + 0.35 * rng.normal(size=n) * np.exp(-t / 0.004)
def hat(open_=False):
    n = int((0.22 if open_ else 0.07) * SR); t = np.arange(n) / SR
    x = np.diff(rng.normal(size=n + 2), 2)[:n]
    return x * np.exp(-t / (0.09 if open_ else 0.018)) * 0.5
def clap():
    n = int(0.3 * SR); t = np.arange(n) / SR; x = np.diff(rng.normal(size=n), prepend=0)
    e = sum(np.exp(-np.clip(t - d, 0, None) / 0.018) * (t >= d) for d in (0, 0.011, 0.023)) * 0.5 + np.exp(-t / 0.11) * 0.35
    return x * e * 0.55
def riser(dur, bright=1.0):
    n = int(dur * SR); t = np.arange(n) / SR; x = rng.normal(size=n)
    x = x + 1.8 * np.diff(x, prepend=0) * bright
    return x * (t / dur) ** 2.2 * 0.5
def boom(dur=3.0):
    n = int(dur * SR); t = np.arange(n) / SR
    f = 28 + 60 * np.exp(-t / 0.25); ph = 2 * np.pi * np.cumsum(f) / SR
    nz = np.diff(rng.normal(size=n), prepend=0) * np.exp(-t / 0.5) * 0.6
    return np.sin(ph) * np.exp(-t / 1.1) * 1.3 + nz

kick_t, clap_t = [], []

# ── arrangement, bar by bar ──
for b in range(30):
    t0 = b * BAR; name = chord_at_bar(b); v = V[name]; last = b >= 27
    # PAD: slow detuned saws, filter opening over the film
    cut = 380 + 1700 * smooth(ramp(t0, 0, 50))
    dur = BAR + (1.6 if not last else 2.2)
    for k, m in enumerate(v[:4] if not last else v):
        for det, pan in ((-0.004, -0.55), (0.004, 0.55)):
            s = saw_lp(mtof(m - 12 if k == 0 else m), dur, cut, K=18, detune=det) * env_ar(int(dur * SR), 0.7, 1.4)
            put(s, t0 - 0.1, pan, (0.11 + 0.07 * smooth(ramp(t0, 0, 40))) * (1.0 if not last else 1.15), send=0.55)
    # SUB drone
    nsub = int((BAR + 0.5) * SR); tt = np.arange(nsub) / SR
    put(np.sin(2 * np.pi * mtof(BASS[name]) * tt) * env_ar(nsub, 0.25, 0.4), t0, 0, 0.30 if t0 < 54 else 0.32)

# SHIMMER bells (intro + finale)
for t0 in np.arange(0.5, 23.0, 0.5):
    if rng.random() < 0.55:
        v = V[chord_at_bar(int(t0 // BAR))]; m = v[rng.integers(0, 4)] + 24
        n = int(1.6 * SR); tt = np.arange(n) / SR
        bell = (np.sin(2 * np.pi * mtof(m) * tt) + 0.35 * np.sin(2 * np.pi * mtof(m) * 2.0 * tt)) * np.exp(-tt / 0.5)
        put(bell, t0, rng.uniform(-0.8, 0.8), 0.035 * (1 - 0.5 * ramp(t0, 8, 23)), send=0.7)
for t0 in np.arange(55.0, 59.0, 0.5):
    v = V[chord_at_bar(int(t0 // BAR))]; m = v[rng.integers(0, len(v))] + 24
    n = int(1.8 * SR); tt = np.arange(n) / SR
    put(np.sin(2 * np.pi * mtof(m) * tt) * np.exp(-tt / 0.6), t0, rng.uniform(-0.7, 0.7), 0.05, send=0.8)

# ARP: 16th plucks, ping-pong, growing from 6 s; thinned in the finale
PAT = [0, 2, 1, 2, 0, 2, 3, 2]
for step in range(int(54 / 0.125)):
    t0 = step * 0.125
    if t0 < 6.0: continue
    g = (0.16 + 0.74 * smooth(ramp(t0, 6, 34))) * (0.8 if t0 >= 46 else 1.0)
    v = V[chord_at_bar(int(t0 // BAR))]; m = v[PAT[step % 8]] + 12
    n = int(0.34 * SR); tt = np.arange(n) / SR
    fc = 600 + 3400 * np.exp(-tt / 0.07) * (0.5 + 0.5 * smooth(ramp(t0, 6, 34)))
    p = saw_lp(mtof(m), 0.34, fc, K=22) * np.exp(-tt / 0.13)
    pan = 0.55 if (step % 2) else -0.55
    put(p, t0, pan, 0.16 * g, send=0.30)
    put(p, t0 + 0.375, -pan, 0.16 * g * 0.33, send=0.4)       # dotted-8th echo
for step in range(int((60 - 54.5) / 0.25)):                      # gentle finale arp
    t0 = 54.5 + step * 0.25
    v = V[chord_at_bar(int(t0 // BAR))]; m = v[[0, 2, 1, 3][step % 4]] + 12
    n = int(0.5 * SR); tt = np.arange(n) / SR
    put(saw_lp(mtof(m), 0.5, 1200 + 1500 * np.exp(-tt / 0.1), K=18) * np.exp(-tt / 0.2), t0, 0.5 if step % 2 else -0.5, 0.09 * (1 - 0.7 * ramp(t0, 57.5, 59.8)), send=0.5)

# BASS pulse (8ths) + drums
for b in range(27):
    t0 = b * BAR
    if t0 >= 15.0:
        name = chord_at_bar(b); f = mtof(BASS[name] + 12)
        for e in range(8):
            tb = t0 + e * 0.25
            n = int(0.24 * SR); tt = np.arange(n) / SR
            s = (np.sin(2 * np.pi * f * tt) + 0.45 * saw_lp(f, 0.24, 520, K=10)) * np.exp(-tt / 0.2) * env_ar(n, 0.004, 0.03)
            put(s, tb, 0, 0.22 * (0.7 + 0.3 * ramp(t0, 15, 46)))
for t0 in np.arange(0, 54.0, 0.25):
    beat = int(round(t0 / 0.5)); on_beat = abs(t0 / 0.5 - round(t0 / 0.5)) < 1e-6
    # hats
    if t0 >= 6.0:
        g = 0.22 if t0 < 15 else (0.38 if t0 < 34 else 0.5)
        if t0 >= 34 and not on_beat or on_beat or t0 >= 15:
            off = not on_beat
            if t0 < 34 and off and t0 >= 15: put(hat(True), t0, 0.35, g * 0.7)
            elif t0 < 34 and on_beat: put(hat(False), t0, 0.35, g)
            elif t0 >= 34: put(hat(off and (int(t0 / 0.25) % 4 == 2)), t0, 0.35 if off else -0.2, g * (0.8 if off else 1.0))
    # kicks (four on the floor from 15 s; a bar of air before 34 s and before the brand hit)
    if on_beat and t0 >= 15.0 and not (33.0 <= t0 < 34.0) and t0 < 53.0:
        put(kick(), t0, 0, 0.9 if t0 < 46 else 1.0); kick_t.append(t0)
    # claps on 2 & 4 from 23 s
    pos = (t0 % BAR) / BEAT
    if on_beat and t0 >= 23.0 and not (33.0 <= t0 < 34.0) and t0 < 53.0 and int(round(pos)) in (1, 3):
        put(clap(), t0, 0.1, 0.55 if t0 < 46 else 0.7, send=0.25); clap_t.append(t0)
# beat-synced accent on each montage cut (46..53)
for c in range(46, 54):
    put(kick(), float(c), 0, 0.55)
    put(riser(0.45, 1.4), c - 0.45, 0, 0.18)
# riser into 34 s, big riser + impact into the brand reveal
put(riser(1.0, 1.0), 33.0, 0, 0.5, send=0.2); put(boom(1.2), 34.0, 0, 0.45)
for k in range(8): put(clap(), 33.0 + k * 0.125, 0, 0.18 + 0.05 * k)        # snare-roll feel
put(riser(2.0, 1.2), 52.0, 0, 0.7, send=0.3)
put(boom(3.4), 54.0, 0, 0.95, send=0.5)

# sidechain pump on the dry bus once kicks enter
sc = np.ones(N)
for kt in kick_t:
    i = int(kt * SR); m = min(N, i + int(0.3 * SR)); tt = np.arange(m - i) / SR
    sc[i:m] = np.minimum(sc[i:m], 1 - 0.0 - 0.55 * np.exp(-tt / 0.11))
# the pump only touches the tonal layers: apply to a copy of pad/arp/bass is overkill; apply lightly overall
Lb *= (0.55 + 0.45 * sc); Rb *= (0.55 + 0.45 * sc)
Lw *= (0.4 + 0.6 * sc); Rw *= (0.4 + 0.6 * sc)

# reverb: synthetic decaying-noise impulse response (FFT convolution)
irn = int(2.6 * SR); ti = np.arange(irn) / SR
def ir():
    x = rng.normal(size=irn) * np.exp(-ti / 0.75)
    x = np.diff(x, prepend=0) * 0.2 + np.convolve(x, np.ones(6) / 6, 'same') * 0.8     # darker tail
    return x / np.sqrt(np.sum(x * x))
def conv(x, h):
    n = 1 << int(np.ceil(np.log2(len(x) + len(h)))); return np.fft.irfft(np.fft.rfft(x, n) * np.fft.rfft(h, n), n)[: len(x)]
Lr = conv(Lw, ir()); Rr = conv(Rw, ir())
L = Lb + 0.9 * Lr; R = Rb + 0.9 * Rr

# master: gentle saturation, fades, normalise
t = np.arange(N) / SR
fade = np.clip(t / 0.4, 0, 1) * np.clip((DUR - t) / 1.6, 0, 1)
L = np.tanh(1.25 * L) * fade; R = np.tanh(1.25 * R) * fade
pk = max(np.abs(L).max(), np.abs(R).max()); L *= 0.425 / pk; R *= 0.425 / pk   # ≈ -15 LUFS integrated, -7.4 dBFS peak

out = sys.argv[1] if len(sys.argv) > 1 else 'score.wav'
with wave.open(out, 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(np.stack([L, R], 1), -1, 1) * 32767).astype('<i2').tobytes())
print('wrote', out, f'{DUR:.1f}s')
import shutil, subprocess
if shutil.which('ffmpeg') and out.endswith('.wav'):   # the film references the small AAC copy
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', out, '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out[:-4] + '.m4a'], check=True)
    print('wrote', out[:-4] + '.m4a')
for a in range(0, 60, 6):
    seg = slice(a * SR, (a + 6) * SR); rms = np.sqrt(np.mean(L[seg] ** 2 + R[seg] ** 2) / 2)
    print(f'  {a:2d}-{a+6:2d}s  rms {20*np.log10(rms+1e-9):6.1f} dBFS')
