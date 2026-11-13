"""Original background music + drum hits for Tareekh Ki Kahani, made by code (no copyright problems).

Makes these files in the music folder, only when they are missing:
  bed_calm.wav   slow, dark drone with a plucked string melody and soft frame drum  (story telling)
  bed_tense.wav  heartbeat drums and a nervous string motif                          (danger, conflict)
  bed_epic.wav   driving war drums with a rising melody                              (battles, empires)
  hit.wav        one big drum hit (chapter change)
  riser.wav      1.4 second rising sweep that ends exactly where the hit begins
To use your own music, put files with the same names (mp3 or wav) in the music folder.
"""
import wave
from pathlib import Path

import numpy as np

SR = 48000
RNG = np.random.default_rng(7)

# D Phrygian dominant (the "eastern" colour): D Eb F# G A Bb C
N = {"D2": 73.42, "A2": 110.0, "D3": 146.83, "Eb3": 155.56, "F#3": 185.0, "G3": 196.0, "A3": 220.0,
     "Bb3": 233.08, "C4": 261.63, "D4": 293.66, "D5": 587.33, "Eb4": 311.13, "F#4": 369.99, "G4": 392.0, "A4": 440.0, "Bb4": 466.16}


def _pluck(freq, dur, amp=1.0, decay=0.997):
    """Karplus-Strong plucked string (rubab / oud like)."""
    L = max(int(round(SR / freq)), 2)
    n = int(dur * SR)
    out = np.zeros(n + 1)
    noise = RNG.uniform(-1, 1, L)
    noise = np.convolve(noise, np.ones(3) / 3, mode="same")          # softer start
    out[1:L + 1] = noise[:min(L, n)]
    for s in range(L + 1, n + 1, L):
        b = min(L, n + 1 - s)
        out[s:s + b] = decay * 0.5 * (out[s - L:s - L + b] + out[s - L - 1:s - L - 1 + b])
    y = out[1:]
    y = y * np.minimum(np.arange(n) / (0.004 * SR), 1.0)               # tiny attack
    y = y * np.exp(-np.arange(n) / (SR * dur * 0.55))
    return amp * y / (np.max(np.abs(y)) + 1e-9)


def _boom(f0=130, f1=48, decay=3.5, dur=1.4, click=0.25, amp=1.0):
    """Deep dhol/frame-drum hit: falling sine + a short noise click."""
    t = np.arange(int(dur * SR)) / SR
    f = f1 + (f0 - f1) * np.exp(-t * 22)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * decay)
    sub = np.sin(2 * np.pi * 36 * t) * np.exp(-t * 2.2) * 0.5
    nz = RNG.uniform(-1, 1, t.size)
    nz = np.convolve(nz, np.ones(6) / 6, mode="same") * np.exp(-t * 70) * click
    y = body + sub + nz
    return amp * y / (np.max(np.abs(y)) + 1e-9)


def _tak(amp=1.0, pitch=190):
    """Higher, short frame-drum 'tak'."""
    t = np.arange(int(0.25 * SR)) / SR
    f = pitch + 90 * np.exp(-t * 40)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 16)
    nz = np.convolve(RNG.uniform(-1, 1, t.size), np.ones(3) / 3, mode="same") * np.exp(-t * 60) * 0.5
    y = y + nz
    return amp * y / (np.max(np.abs(y)) + 1e-9)


def _shaker(amp=1.0):
    t = np.arange(int(0.08 * SR)) / SR
    nz = RNG.uniform(-1, 1, t.size)
    nz = nz - np.convolve(nz, np.ones(12) / 12, mode="same")           # high-pass-ish
    return amp * nz * np.exp(-t * 45)


def _drone(freqs, length, level=1.0):
    t = np.arange(length) / SR
    y = np.zeros(length)
    for k, f in enumerate(freqs):
        lfo = 1 + 0.015 * np.sin(2 * np.pi * (0.07 + 0.02 * k) * t + k)
        for h, a in ((1, 1.0), (2, 0.45), (3, 0.28), (4, 0.15), (5, 0.08)):
            y += a * np.sin(2 * np.pi * f * h * t * (1 + 0.0007 * k)) * lfo / (1 + 0.3 * k)
    # slow swell so the drone breathes (whole number of cycles: loops cleanly)
    cycles = max(int(round(length / SR / 9.0)), 1)
    y *= 0.8 + 0.2 * np.sin(2 * np.pi * cycles * t / (length / SR))
    return level * y / (np.max(np.abs(y)) + 1e-9)


def _add(buf, sig, pos):
    """Add sig into a circular buffer (so the loop has no seam)."""
    idx = (pos + np.arange(sig.size)) % buf.size
    np.add.at(buf, idx, sig)


def _circular_reverb(x, seconds=1.4, wet=0.3, seed=1, decay=3.2):
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / SR * decay)
    ir[:int(0.012 * SR)] *= 0.2
    ir /= np.sqrt(np.sum(ir ** 2))
    ir_full = np.zeros(x.size); ir_full[:n] = ir[:x.size]
    wetsig = np.fft.irfft(np.fft.rfft(x) * np.fft.rfft(ir_full), x.size)
    return (1 - wet) * x + wet * wetsig


def _norm_rms(x, db):
    r = np.sqrt(np.mean(x ** 2)) + 1e-12
    y = x * (10 ** (db / 20) / r)
    return np.tanh(y * 0.9) / 0.9 if np.max(np.abs(y)) > 0.95 else y


def make_bed(mood):
    bpm, bars = {"calm": (72, 16), "tense": (92, 16), "epic": (104, 16)}[mood]
    beat = 60.0 / bpm
    length = int(round(bars * 4 * beat * SR))
    buf = np.zeros(length)
    bar = 4 * beat

    def at(b):                                    # beat number -> sample position
        return int(round(b * beat * SR))

    if mood == "calm":
        buf += _drone([N["D2"], N["A2"]], length, 0.55)
        for b in range(bars):
            _add(buf, _boom(110, 46, 3.2, 1.6, 0.15, 0.85), at(4 * b))
            _add(buf, _boom(110, 46, 3.2, 1.2, 0.15, 0.40), at(4 * b + 2.5))
            _add(buf, _tak(0.22), at(4 * b + 1)); _add(buf, _tak(0.22, 210), at(4 * b + 3))
        motif = [(0, "A3", 3), (3, "Bb3", 1), (4, "A3", 2), (6, "G3", 2), (8, "F#3", 2), (10, "G3", 2), (12, "A3", 3.5),
                 (16, "D4", 3), (19, "C4", 1), (20, "Bb3", 2), (22, "A3", 2), (24, "G3", 3), (28, "F#3", 2), (30, "D3", 2)]
        for rep in range(bars // 8):
            for b, nme, dur in motif:
                _add(buf, _pluck(N[nme], dur * beat + 0.8, 0.55, 0.998), at(rep * 32 + b))
        wet, db = 0.35, -22.0
    elif mood == "tense":
        buf += _drone([N["D2"], N["Eb3"]], length, 0.5)
        for b in range(bars):
            _add(buf, _boom(120, 46, 4.2, 1.0, 0.2, 0.9), at(4 * b))
            _add(buf, _boom(120, 46, 4.2, 0.8, 0.2, 0.7), at(4 * b + 0.75))
            _add(buf, _boom(120, 46, 4.2, 0.8, 0.2, 0.5), at(4 * b + 2))
            _add(buf, _boom(120, 46, 4.2, 0.8, 0.2, 0.4), at(4 * b + 2.75))
            for k in range(8):
                _add(buf, _shaker(0.10 if k % 2 else 0.17), at(4 * b + k * 0.5))
        for rep in range(bars // 4):
            for k, nme in enumerate(["D3", "Eb3", "D3", "Eb3", "F#3", "Eb3", "D3", "D3"]):
                _add(buf, _pluck(N[nme], 0.6, 0.45, 0.996), at(rep * 16 + k * 1.0 * 2))
        wet, db = 0.3, -21.0
    else:  # epic
        buf += _drone([N["D2"], N["A2"], N["D3"]], length, 0.45)
        for b in range(bars):
            for k in range(8):
                lo = k % 2 == 0
                acc = 1.0 if k == 0 else (0.7 if k in (2, 4, 6) else 0.45)
                _add(buf, _boom(105 if lo else 145, 46 if lo else 80, 4.0, 0.9, 0.2, acc), at(4 * b + k * 0.5))
            _add(buf, _tak(0.35, 230), at(4 * b + 1)); _add(buf, _tak(0.35, 230), at(4 * b + 3))
        mel = [("D4", 2), ("Eb4", 1), ("D4", 1), ("C4", 2), ("Bb3", 2), ("A3", 2), ("Bb3", 1), ("C4", 1), ("D4", 4),
               ("F#4", 2), ("G4", 1), ("F#4", 1), ("Eb4", 2), ("D4", 2), ("C4", 2), ("Bb3", 2), ("A3", 4)]
        pos = 0.0
        for rep in range(2):
            for nme, dur in mel:
                _add(buf, _pluck(N[nme], dur * beat + 0.8, 0.6, 0.998), at(pos)); pos += dur
            pos += 0
        wet, db = 0.3, -20.0
    buf = _circular_reverb(buf, 1.4, wet, seed=sum(map(ord, mood)))
    # soften the very low end so it does not fight the voice
    buf = buf - 0.0
    buf = _norm_rms(buf, db)
    left = buf
    right = np.roll(buf, int(0.011 * SR)) * 0.97                      # slight stereo width
    return np.stack([left, right], axis=1).astype(np.float32)


def make_hit():
    h = _boom(135, 42, 2.6, 2.6, 0.35, 1.0) + 0.45 * _boom(80, 34, 1.6, 2.6, 0.0, 1.0)
    n = h.size
    ir = np.random.default_rng(5).standard_normal(int(1.6 * SR)) * np.exp(-np.arange(int(1.6 * SR)) / SR * 2.6)
    ir /= np.sqrt(np.sum(ir ** 2))
    wet = np.convolve(np.pad(h, (0, ir.size)), ir)[:n]
    h = 0.75 * h + 0.45 * wet
    h = h / (np.max(np.abs(h)) + 1e-9) * 0.95
    return np.stack([h, np.roll(h, 40)], axis=1).astype(np.float32)


def make_riser(sec=1.4):
    n = int(sec * SR)
    t = np.arange(n) / SR
    nz = RNG.standard_normal(n)
    # sweep a moving-average filter from dark to bright
    out = np.zeros(n)
    for k in range(0, n, 2048):
        frac = k / n
        w = int(60 - 54 * frac) + 1
        seg = nz[k:k + 2048]
        out[k:k + seg.size] = seg - np.convolve(nz, np.ones(w) / w, mode="same")[k:k + seg.size] * (1 - frac)
    env = (t / sec) ** 2.2
    tone = np.sin(2 * np.pi * np.cumsum(60 + 380 * (t / sec) ** 2) / SR) * env * 0.5
    y = out * env + tone
    y = y / (np.max(np.abs(y)) + 1e-9) * 0.8
    return np.stack([y, np.roll(y, 30)], axis=1).astype(np.float32)


def _guitar(freq, dur, amp=1.0):
    """Nylon / acoustic guitar pluck: Karplus-Strong string plus a soft wooden body thump."""
    y = _pluck(freq, dur, 1.0, 0.9985)
    t = np.arange(y.size) / SR
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 38) * 0.12
    return amp * (y + body) / 1.1


def _arp(notes, step, tail, amp=0.7, rng=None):
    """Arpeggio: notes (names) every `step` seconds, each ringing `tail` seconds."""
    total = int((step * (len(notes) - 1) + tail) * SR)
    buf = np.zeros(total)
    for k, nme in enumerate(notes):
        g = _guitar(N[nme], tail, amp * (0.8 + 0.2 * ((k + 1) % 2)))
        p = int(k * step * SR); buf[p:p + g.size] += g[:max(0, total - p)]
    return buf


def _stereo(x, delay=0.009):
    return np.stack([x, np.roll(x, int(delay * SR)) * 0.95], axis=1)


def make_fills():
    """Short guitar phrases that play in the pause between scenes. Returns {name: stereo array}."""
    out = {}
    # calm: gentle rising / falling arpeggios (D Phrygian dominant)
    out["fill_a"] = _arp(["D3", "A3", "D4", "F#4", "A4"], 0.16, 1.7, 0.6)                 # rising, open
    out["fill_b"] = _arp(["A4", "G4", "F#4", "Eb4", "D4"], 0.20, 1.8, 0.6)                # falling, settles
    out["fill_c"] = _arp(["D3", "F#3", "A3", "Bb3", "A3", "F#3"], 0.15, 1.6, 0.6)         # rolling
    # tense: low muted pluck + frame-drum tak
    t = _arp(["D3", "Eb3", "D3"], 0.22, 0.9, 0.75)
    t[:_boom().size] += 0.0
    tk = np.zeros(t.size + SR); tk[:t.size] += t
    for p in (0.0, 0.44):
        k = _tak(0.55, 170); i = int(p * SR); tk[i:i + k.size] += k[:tk.size - i]
    out["fill_tense"] = tk
    # epic: strummed chord + deep drum
    ch = _arp(["D3", "A3", "D4", "F#4"], 0.025, 1.6, 0.9)
    b = _boom(120, 44, 3.4, 1.6, 0.25, 0.9); e = np.zeros(max(ch.size, b.size)); e[:ch.size] += ch; e[:b.size] += b
    out["fill_epic"] = e
    # info stinger: a bright double pluck then a soft drum - for dates, names, "important" moments
    st = _arp(["A4", "D5" if "D5" in N else "A4"], 0.12, 1.2, 0.7)
    sb = np.zeros(int(1.6 * SR)); sb[:st.size] += st
    bm = _boom(150, 55, 4.0, 1.0, 0.2, 0.7); sb[:bm.size] += bm
    out["stinger"] = sb
    res = {}
    for name, x in out.items():
        x = x / (np.max(np.abs(x)) + 1e-9) * 0.9
        n = x.size; fade = int(0.35 * SR); x[-fade:] *= np.linspace(1, 0, fade)
        res[name] = _stereo(x).astype(np.float32)
    return res


def _write(path, arr):
    pcm = (np.clip(arr, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(arr.shape[1]); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def ensure_music(folder):
    """Create any missing music file. Returns True if something was made."""
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    made = False
    jobs = [("bed_calm", lambda: make_bed("calm")), ("bed_tense", lambda: make_bed("tense")),
            ("bed_epic", lambda: make_bed("epic")), ("hit", make_hit), ("riser", make_riser)]
    for name, fn in jobs:
        if any((folder / f"{name}{ext}").exists() for ext in (".wav", ".mp3", ".m4a")): continue
        print(f"  making music file {name} ...", flush=True)
        _write(folder / f"{name}.wav", fn()); made = True
    if not all((folder / f"{n}.wav").exists() or any((folder / f"{n}{e}").exists() for e in (".mp3", ".m4a"))
               for n in ("fill_a", "fill_b", "fill_c", "fill_tense", "fill_epic", "stinger")):
        print("  making guitar fills ...", flush=True)
        for name, arr in make_fills().items():
            if not (folder / f"{name}.wav").exists(): _write(folder / f"{name}.wav", arr)
        made = True
    return made


if __name__ == "__main__":
    import sys
    ensure_music(sys.argv[1] if len(sys.argv) > 1 else "music")
