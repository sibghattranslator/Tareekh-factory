"""Tareekh Ki Kahani - RECORD your own voice, line by line.
Saves recordings\\tkNNN\\01.wav, 02.wav ... Lines you skip use the AI voice in RENDER.bat."""
import json, sys, queue, threading
from pathlib import Path
import sounddevice as sd, soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
EPIS, RECS, RATE = ROOT / "episodes", ROOT / "recordings", 48000


def record_until_enter(path):
    q, stop = queue.Queue(), threading.Event()
    def cb(indata, frames, t, status): q.put(indata.copy())
    with sf.SoundFile(str(path), "w", samplerate=RATE, channels=1, subtype="PCM_16") as f:
        with sd.InputStream(samplerate=RATE, channels=1, callback=cb):
            threading.Thread(target=lambda: (input(), stop.set()), daemon=True).start()
            while not stop.is_set() or not q.empty():
                try: f.write(q.get(timeout=0.1))
                except queue.Empty: pass


def main():
    eps = sorted(EPIS.glob("tk[0-9][0-9][0-9].json"))
    if not eps: print("No episodes."); return
    print("Episodes:", ", ".join(e.stem for e in eps))
    ep = input(f"Which episode? [Enter = {eps[-1].stem}]: ").strip() or eps[-1].stem
    data = json.loads((EPIS / f"{ep}.json").read_text(encoding="utf-8"))
    out = RECS / ep; out.mkdir(parents=True, exist_ok=True)
    start = input("Start from scene number? [Enter = 1]: ").strip()
    i = int(start) if start.isdigit() else 1
    n = len(data["scenes"])
    while i <= n:
        sc = data["scenes"][i - 1]; wav = out / f"{i:02d}.wav"
        print("\n" + "=" * 70 + f"\nSCENE {i}/{n}" + ("   (already recorded)" if wav.exists() else ""))
        print(sc["narration_roman"])
        c = input("\n[Enter]=record  [s]=skip (AI voice)  [p]=play  [d]=delete my take  [q]=quit : ").strip().lower()
        if c == "q": break
        if c == "s": i += 1; continue
        if c == "p" and wav.exists():
            d, r = sf.read(str(wav)); sd.play(d, r); sd.wait(); continue
        if c == "d" and wav.exists(): wav.unlink(); print("Deleted - AI voice will be used."); continue
        if c == "":
            print(">>> RECORDING... speak now. Press Enter to STOP.")
            record_until_enter(wav)
            d, r = sf.read(str(wav)); print(f"Saved {wav.name} ({len(d)/r:.1f} s)")
            if input("[Enter]=keep & next  [r]=redo : ").strip().lower() == "r": continue
            i += 1
    print("\nDone. Now double-click RENDER.bat.")


if __name__ == "__main__":
    main()
