"""Fuller, 'documentary' music for Tareekh Ki Kahani, made by code (original, no copyright problems).

Why this exists: the first music (music_synth.py) lived mostly in the deep bass (40-110 Hz), which laptop and phone
speakers cannot play - so it sounded dull and the drums seemed missing. This set puts the guitar, the pad and the
drums in the middle of the sound (150-4000 Hz) where every speaker plays them, and adds a drum fill at every scene
change, a drum roll + big hit at every chapter change.

Three VARIANTS (A, B, C) share the same instruments but use a different key, tempo, chords and guitar pattern, so
each video sounds like the same series without being a copy. The variant is chosen from the episode number.
Files (in the music folder, made only when missing):  pro<V>_bed_calm / bed_tense / bed_epic / hit / riser /
fill_a / fill_b / fill_c / fill_tense / fill_epic / stinger   (V = 1, 2 or 3).
"""
import wave
from pathlib import Path

import numpy as np

SR = 48000
VARIANTS = {   # shift (semitones from D), bpm calm/tense/epic, arp pattern, chord order
    1: dict(shift=0, bpm=(72, 92, 104), arp=[0, 1, 2, 3, 2, 1, 2, 3], prog=[0, 1, 2, 0]),
    2: dict(shift=2, bpm=(68, 88, 100), arp=[0, 2, 1, 3, 1, 2, 3, 2], prog=[0, 2, 1, 0]),
    3: dict(shift=-2, bpm=(76, 96, 108), arp=[0, 1, 3, 2, 3, 1, 2, 1], prog=[0, 1, 0, 2]),
}
# chords as semitones above D3 (D Phrygian dominant colour): D major, Eb major, G minor
CHORDS = [[0, 7, 12, 16], [1, 8, 13, 17], [5, 12, 17, 20]]
D3 = 146.83


def _f(semi, shift):
    return D3 * 2 ** ((semi + shift) / 12)


def _rng(seed): return np.random.default_rng(seed)


# ------------------------------------------------------------------ instruments
def _pluck(freq, dur, rng, decay=0.9987):
    L = max(int(round(SR / freq)), 2); n = int(dur * SR)
    out = np.zeros(n + 1)
    noise = rng.uniform(-1, 1, L)
    out[1:L + 1] = noise[:min(L, n)]
    for s in range(L + 1, n + 1, L):
        b = min(L, n + 1 - s)
        out[s:s + b] = decay * 0.5 * (out[s - L:s - L + b] + out[s - L - 1:s - L - 1 + b])
    y = out[1:]
    return y * np.minimum(np.arange(n) / (0.002 * SR), 1.0)


def guitar(freq, dur, rng, amp=1.0, bright=1.0):
    """Nylon/steel-ish guitar: two slightly detuned strings, pick click, wooden body resonance, soft saturation."""
    a = _pluck(freq, dur, rng); b = _pluck(freq * 1.0025, dur, rng)
    y = 0.55 * a + 0.45 * b
    t = np.arange(y.size) / SR
    y = y * np.exp(-t / (dur * 0.5))
    click = rng.uniform(-1, 1, y.size) * np.exp(-t * 400) * 0.25 * bright
    body = (np.sin(2 * np.pi * 210 * t) * np.exp(-t * 30) + 0.6 * np.sin(2 * np.pi * 420 * t) * np.exp(-t * 45)) * 0.18
    y = y / (np.max(np.abs(y)) + 1e-9) + click + body
    y = np.tanh(1.6 * y) / 1.3
    return amp * y / (np.max(np.abs(y)) + 1e-9)


def _bp_noise(n, rng, lo_win, hi_win):
    nz = rng.standard_normal(n)
    lo = np.convolve(nz, np.ones(lo_win) / lo_win, mode="same")
    hi = np.convolve(nz, np.ones(hi_win) / hi_win, mode="same")
    return hi - lo


def dum(rng, amp=1.0, f0=190, f1=105, decay=9.0, dur=0.7):
    """Deep frame-drum/dhol 'dum' - fundamental ~105-190 Hz plus overtones and a slap, audible on phone speakers."""
    t = np.arange(int(dur * SR)) / SR
    f = f1 + (f0 - f1) * np.exp(-t * 35)
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = np.sin(ph) * np.exp(-t * decay) + 0.55 * np.sin(2 * ph) * np.exp(-t * (decay + 6)) + 0.3 * np.sin(3 * ph) * np.exp(-t * (decay + 12))
    y += _bp_noise(t.size, rng, 40, 4) * np.exp(-t * 55) * 0.9                   # skin slap, 400-6000 Hz
    y = np.tanh(1.8 * y) / 1.35
    return amp * y / (np.max(np.abs(y)) + 1e-9)


def tak(rng, amp=1.0, pitch=330, dur=0.3):
    t = np.arange(int(dur * SR)) / SR
    f = pitch + 160 * np.exp(-t * 50)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 20)
    y += _bp_noise(t.size, rng, 24, 3) * np.exp(-t * 75) * 1.0
    y = np.tanh(1.5 * y) / 1.2
    return amp * y / (np.max(np.abs(y)) + 1e-9)


def shaker(rng, amp=1.0):
    t = np.arange(int(0.09 * SR)) / SR
    return amp * _bp_noise(t.size, rng, 16, 2) * np.exp(-t * 40) * 0.5


def big_hit(rng):
    """Transition hit: sub + body + mid tom + crack, with a short room tail. Strong in the 100-3000 Hz area."""
    n = int(2.6 * SR)
    h = np.zeros(n)
    for sig, g in ((dum(rng, 1.0, 130, 55, 3.4, 2.4), 0.55), (dum(rng, 1.0, 230, 120, 5.0, 2.0), 1.0), (tak(rng, 1.0, 260, 0.5), 0.6)):
        h[:sig.size] += g * sig
    t = np.arange(n) / SR
    h += _bp_noise(n, rng, 60, 3) * np.exp(-t * 9) * 0.45                        # cymbal-ish wash
    ir = rng.standard_normal(int(1.5 * SR)) * np.exp(-np.arange(int(1.5 * SR)) / SR * 3.0)
    ir /= np.sqrt(np.sum(ir ** 2))
    wet = np.convolve(np.pad(h, (0, ir.size)), ir)[:n]
    h = np.tanh(0.8 * h + 0.45 * wet)
    return h / (np.max(np.abs(h)) + 1e-9) * 0.95


def _pad(chord, seconds, shift, rng):
    """Warm string-like pad: detuned stacked tones with a slow fade in/out."""
    n = int(seconds * SR); t = np.arange(n) / SR
    y = np.zeros(n)
    for k, s in enumerate(chord):
        f = _f(s - 12 if k == 0 else s, shift)
        for det in (-0.0035, 0.0, 0.0035):
            for h, a in ((1, 1.0), (2, 0.5), (3, 0.33), (4, 0.2), (5, 0.12), (6, 0.07)):
                y += a * np.sin(2 * np.pi * f * (1 + det) * h * t + rng.uniform(0, 6.28)) / (1 + 0.25 * k)
    env = np.sin(np.pi * np.clip(t / seconds, 0, 1)) ** 1.5
    return y * env / (np.max(np.abs(y)) + 1e-9)


def _add(buf, sig, pos):
    idx = (int(pos) + np.arange(sig.size)) % buf.size
    np.add.at(buf, idx, sig)


def _reverb(x, seconds, wet, seed, decay=3.0):
    n = int(seconds * SR); rng = _rng(seed)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / SR * decay)
    ir[:int(0.012 * SR)] *= 0.2; ir /= np.sqrt(np.sum(ir ** 2))
    full = np.zeros(x.size); full[:n] = ir[:x.size]
    return (1 - wet) * x + wet * np.fft.irfft(np.fft.rfft(x) * np.fft.rfft(full), x.size)


def _highpass(x, hz=70):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(x.size, 1 / SR)
    X *= np.clip((f - hz * 0.5) / (hz * 0.5), 0, 1)
    return np.fft.irfft(X, x.size)


def _rms_to(x, db):
    r = np.sqrt(np.mean(x ** 2)) + 1e-12
    y = x * (10 ** (db / 20) / r)
    return np.tanh(y * 0.9) / 0.9


def _stereo(x, delay=0.011):
    return np.stack([x, np.roll(x, int(delay * SR)) * 0.96], axis=1).astype(np.float32)


# ------------------------------------------------------------------ beds
def make_bed(mood, v):
    cfg = VARIANTS[v]; shift = cfg["shift"]
    bpm = cfg["bpm"][("calm", "tense", "epic").index(mood)]
    beat = 60.0 / bpm; bars = 16
    length = int(round(bars * 4 * beat * SR)); buf = np.zeros(length)
    rng = _rng(100 * v + len(mood))
    at = lambda b: int(round(b * beat * SR))
    prog = cfg["prog"]

    # pad: one chord per 2 bars (overlapping so there are no gaps)
    for k in range(bars // 2):
        chord = CHORDS[prog[k % len(prog)]]
        _add(buf, _pad(chord, 2 * 4 * beat * 1.3, shift, rng) * (0.5 if mood == "calm" else 0.42), at(k * 8 - 1))

    def jit(b): return b + rng.uniform(-0.012, 0.012)
    if mood == "calm":
        for bar in range(bars):
            chord = CHORDS[prog[(bar // 2) % len(prog)]]
            for i, idx in enumerate(cfg["arp"]):                       # picked arpeggio, eighth notes
                note = chord[idx] + (12 if idx == 3 and i % 4 == 3 else 0)
                _add(buf, guitar(_f(note, shift), 2.2, rng, 0.62 if i % 2 == 0 else 0.45), at(jit(bar * 4 + i * 0.5)))
            _add(buf, dum(rng, 0.85), at(jit(bar * 4)));        _add(buf, dum(rng, 0.45, dur=0.5), at(jit(bar * 4 + 2.5)))
            _add(buf, tak(rng, 0.38), at(jit(bar * 4 + 1.5)));   _add(buf, tak(rng, 0.45), at(jit(bar * 4 + 3)))
        for rep in range(2):                                           # slow lead melody, one octave up
            for b, s, d in [(0, 16, 3), (3, 17, 1), (4, 16, 2), (6, 12, 2), (8, 13, 3), (12, 12, 3.5), (16, 19, 3), (19, 17, 1),
                            (20, 16, 2), (22, 12, 2), (24, 13, 3), (28, 12, 4)]:
                _add(buf, guitar(_f(s + 12, shift), d * beat + 1.0, rng, 0.5, 1.2), at(rep * 32 + b))
        wet, db = 0.28, -19.0
    elif mood == "tense":
        for bar in range(bars):
            chord = CHORDS[prog[(bar // 2) % len(prog)]]
            root = _f(chord[0], shift)
            for i in range(8):                                         # muted low chug, accents on 1 and 3
                acc = 0.8 if i in (0, 4) else (0.55 if i in (2, 6) else 0.38)
                _add(buf, guitar(root, 0.5, rng, acc, 0.7), at(jit(bar * 4 + i * 0.5)))
            for b, a in ((0, 0.95), (0.75, 0.6), (2, 0.8), (2.75, 0.55)):
                _add(buf, dum(rng, a, 175, 95, 8.0, 0.55), at(jit(bar * 4 + b)))
            for k in range(8): _add(buf, shaker(rng, 0.18 if k % 2 else 0.3), at(bar * 4 + k * 0.5))
        for rep in range(bars // 4):
            for k, s in enumerate([12, 13, 12, 13, 16, 13, 12, 12]):
                _add(buf, guitar(_f(s, shift), 1.0, rng, 0.5, 1.1), at(rep * 16 + k * 2))
        wet, db = 0.25, -18.5
    else:  # epic
        for bar in range(bars):
            for k in range(8):
                acc = 1.0 if k == 0 else (0.7 if k in (2, 4, 6) else 0.42)
                lo = k % 2 == 0
                _add(buf, dum(rng, acc, 190 if lo else 240, 105 if lo else 150, 9.0, 0.5), at(jit(bar * 4 + k * 0.5)))
            _add(buf, tak(rng, 0.5, 340), at(bar * 4 + 1)); _add(buf, tak(rng, 0.5, 340), at(bar * 4 + 3))
            if bar % 2 == 0:                                           # strummed chord every two bars
                chord = CHORDS[prog[(bar // 2) % len(prog)]]
                for j, s in enumerate(chord):
                    _add(buf, guitar(_f(s, shift), 3.0, rng, 0.62, 1.2), at(bar * 4 + j * 0.04))
        mel = [(16, 2), (17, 1), (16, 1), (12, 2), (8, 2), (7, 2), (8, 1), (12, 1), (16, 4),
               (21, 2), (22, 1), (21, 1), (17, 2), (16, 2), (12, 2), (8, 2), (7, 4)]
        pos = 0.0
        for rep in range(2):
            for s, d in mel:
                _add(buf, guitar(_f(s + 12, shift), d * beat + 1.0, rng, 0.58, 1.3), at(pos)); pos += d
        wet, db = 0.25, -17.5
    buf = _reverb(buf, 1.3, wet, seed=7 * v + len(mood))
    buf = _highpass(buf, 110)
    return _stereo(_rms_to(buf, db))


# ------------------------------------------------------------------ transitions
def make_hit(v):
    return _stereo(big_hit(_rng(900 + v)), 0.006)


def make_riser(v, sec=1.4):
    """Accelerating drum roll + rising noise and tone; ends exactly where the hit begins."""
    rng = _rng(700 + v); n = int(sec * SR); y = np.zeros(n); t = np.arange(n) / SR
    pos = 0.0; gap = 0.20
    while pos < sec - 0.05:
        a = 0.25 + 0.75 * (pos / sec) ** 1.5
        d = dum(rng, a, 200, 120, 14.0, 0.25) if int(pos / gap) % 2 == 0 else tak(rng, a * 0.8, 300, 0.2)
        i = int(pos * SR); y[i:i + d.size] += d[:max(0, n - i)]
        gap = max(0.045, gap * 0.9); pos += gap
    nz = _bp_noise(n, rng, 120, 2) * (t / sec) ** 2.2 * 0.6
    tone = np.sin(2 * np.pi * np.cumsum(180 + 700 * (t / sec) ** 2) / SR) * (t / sec) ** 2.5 * 0.35
    y = np.tanh(1.2 * (y + nz + tone))
    y = y / (np.max(np.abs(y)) + 1e-9) * 0.85
    return _stereo(y, 0.008)


def _arp(notes, step, tail, rng, amp=0.8):
    total = int((step * (len(notes) - 1) + tail) * SR); buf = np.zeros(total)
    for k, nm in enumerate(notes):
        g = guitar(nm, tail, rng, amp * (0.8 + 0.2 * ((k + 1) % 2)))
        p = int(k * step * SR); buf[p:p + g.size] += g[:max(0, total - p)]
    return buf


def make_fills(v):
    """Guitar phrase + drum, played in the pause between scenes."""
    cfg = VARIANTS[v]; sh = cfg["shift"]; rng = _rng(500 + v)
    F = lambda s: _f(s, sh)
    out = {}

    def mix(guit, drums):
        n = max(guit.size, max((i + d.size for i, d in drums), default=0)); e = np.zeros(n); e[:guit.size] += guit
        for i, d in drums: e[i:i + d.size] += d
        return e
    S = lambda s: int(s * SR)
    out["fill_a"] = mix(_arp([F(0), F(7), F(12), F(16), F(19)], 0.15, 1.7, rng), [(0, dum(rng, 0.8)), (S(0.45), tak(rng, 0.5)), (S(0.6), tak(rng, 0.6))])
    out["fill_b"] = mix(_arp([F(19), F(17), F(16), F(13), F(12)], 0.18, 1.8, rng), [(0, tak(rng, 0.55)), (S(0.2), tak(rng, 0.6)), (S(0.7), dum(rng, 0.85))])
    out["fill_c"] = mix(_arp([F(0), F(4), F(7), F(8), F(7), F(4)], 0.14, 1.6, rng), [(0, dum(rng, 0.8)), (S(0.5), dum(rng, 0.55)), (S(0.75), tak(rng, 0.6))])
    out["fill_tense"] = mix(_arp([F(0), F(1), F(0)], 0.2, 1.0, rng, 0.9), [(0, dum(rng, 0.95, 175, 95, 8, 0.55)), (S(0.3), dum(rng, 0.7, 175, 95, 8, 0.55)), (S(0.75), dum(rng, 0.9, 175, 95, 8, 0.55))])
    out["fill_epic"] = mix(_arp([F(0), F(7), F(12), F(16)], 0.03, 1.8, rng, 0.95), [(0, dum(rng, 1.0, 190, 100, 6, 0.9)), (S(0.5), dum(rng, 0.7, 240, 150, 8, 0.5)), (S(0.75), dum(rng, 0.8, 240, 150, 8, 0.5))])
    out["stinger"] = mix(_arp([F(19), F(24)], 0.12, 1.3, rng, 0.85), [(0, tak(rng, 0.7, 380)), (S(0.12), dum(rng, 0.6))])
    res = {}
    for name, x in out.items():
        x = np.tanh(1.2 * x); x = x / (np.max(np.abs(x)) + 1e-9) * 0.9
        fade = int(0.35 * SR); x[-fade:] *= np.linspace(1, 0, fade)
        res[name] = _stereo(x)
    return res


# ------------------------------------------------------------------ files
def _write(path, arr):
    pcm = (np.clip(arr, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(arr.shape[1]); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


def variant_for(ep):
    """tk001 -> 1, tk002 -> 2, tk003 -> 3, tk004 -> 1 ... (three sounds in rotation)."""
    digits = "".join(c for c in str(ep) if c.isdigit())
    return (int(digits) - 1) % 3 + 1 if digits else 1


def ensure_pro(folder, v):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True); p = f"pro{v}_"
    made = False
    jobs = [("bed_calm", lambda: make_bed("calm", v)), ("bed_tense", lambda: make_bed("tense", v)),
            ("bed_epic", lambda: make_bed("epic", v)), ("hit", lambda: make_hit(v)), ("riser", lambda: make_riser(v))]
    for name, fn in jobs:
        if (folder / f"{p}{name}.wav").exists(): continue
        print(f"  making music file {p}{name} ...", flush=True); _write(folder / f"{p}{name}.wav", fn()); made = True
    fn_ = ("fill_a", "fill_b", "fill_c", "fill_tense", "fill_epic", "stinger")
    if not all((folder / f"{p}{n}.wav").exists() for n in fn_):
        print(f"  making guitar + drum fills ({p}) ...", flush=True)
        for name, arr in make_fills(v).items():
            if not (folder / f"{p}{name}.wav").exists(): _write(folder / f"{p}{name}.wav", arr)
        made = True
    return made


if __name__ == "__main__":
    import sys
    ensure_pro(sys.argv[1] if len(sys.argv) > 1 else "music", int(sys.argv[2]) if len(sys.argv) > 2 else 1)
