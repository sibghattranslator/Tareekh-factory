"""Tareekh Ki Kahani - video factory (RENDER).
Makes every episode in episodes\\ that is not yet in "Ready to Upload".
Per scene: picture (images\\tkNNN\\NN.jpg) + voice (recordings\\tkNNN\\NN.wav = your voice,
otherwise AI Hindi voice) + on-screen text -> one MP4 per episode.
"""
import asyncio, json, os, re, shutil, subprocess, sys, wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
EPIS = ROOT / "episodes"; IMGS = ROOT / "images"; RECS = ROOT / "recordings"
READY = ROOT / "Ready to Upload"; MUSIC = ROOT / "music"; WORK = ROOT / "factory" / "_work"
W, H, FPS = 1920, 1080, 30
VOICE_HI = os.environ.get("TK_VOICE", "hi-IN-MadhurNeural")  # male Hindi voice (reads narration_hi); female: hi-IN-SwaraNeural
VOICE_UR = "ur-PK-AsadNeural"                            # only for old episodes that have no narration_hi
SW, SH = 1080, 1920                                      # Shorts (vertical)
TEST = os.environ.get("TK_TEST") == "1"                  # silent audio, for testing only


def ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe: return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run(args):
    r = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"] + [str(a) for a in args])
    if r.returncode: raise RuntimeError("ffmpeg failed: " + " ".join(map(str, args[:6])))


def font(size, bold=True):
    win = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    names = (["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"]) + ["DejaVuSans-Bold.ttf"]
    for n in names:
        for p in [win / n, Path("/usr/share/fonts/truetype/dejavu") / n]:
            if p.exists(): return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def latin_part(text):
    """On-screen text is 'Roman | Hindi | Urdu'. Windows fonts can't join Urdu/Hindi letters
    without extra libraries, so we show the Roman part on screen."""
    return text.split("|")[0].strip()


def wrap(draw, text, f, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= maxw: cur = t
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines


def placeholder(path, scene, idx):
    img = Image.new("RGB", (W, H), (14, 18, 28))
    d = ImageDraw.Draw(img)
    for y in range(H):  # dark gradient
        c = int(14 + 30 * y / H); d.line([(0, y), (W, y)], fill=(c, c // 2 + 8, 20))
    f = font(84); lines = wrap(d, latin_part(scene["text_on_screen"]), f, W - 300)
    y = H // 2 - len(lines) * 55
    for ln in lines:
        d.text(((W - d.textlength(ln, font=f)) / 2, y), ln, font=f, fill=(240, 200, 120)); y += 110
    img.save(path, quality=92)


def safe_name(title, limit=100):
    """Video title -> file name. YouTube uses the file name as the title when you upload."""
    t = re.sub(r'[\\/:*?"<>|]', "", title)
    return re.sub(r"\s+", " ", t).strip(" .")[:limit].strip(" .")


def cover(src, dst, w=W, h=H):
    """Scale/crop picture to the frame shape at double size (smooth slow zoom)."""
    im = Image.open(src).convert("RGB")
    tw, th = w * 2, h * 2
    r = max(tw / im.width, th / im.height)
    im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1), Image.LANCZOS)
    l, t = (im.width - tw) // 2, (im.height - th) // 2
    im.crop((l, t, l + tw, t + th)).save(dst, quality=93)


def lower_third(scene, dst):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    text = latin_part(scene["text_on_screen"])
    if text:
        d = ImageDraw.Draw(img); f = font(52)
        lines = wrap(d, text, f, W - 240)[:2]
        bh = 40 + 66 * len(lines)
        d.rectangle([0, H - bh - 70, W, H - 70], fill=(0, 0, 0, 150))
        d.rectangle([0, H - bh - 70, 14, H - 70], fill=(225, 170, 60, 255))
        y = H - bh - 50
        for ln in lines: d.text((70, y), ln, font=f, fill=(255, 255, 255, 255)); y += 66
    d2 = ImageDraw.Draw(img); f2 = font(30)
    d2.text((W - 40 - d2.textlength("Tareekh Ki Kahani", font=f2), 30), "Tareekh Ki Kahani", font=f2, fill=(255, 255, 255, 170))
    img.save(dst)


def short_frame(src, dst):
    """Vertical frame: blurred copy of the picture as background, sharp picture in the upper middle."""
    im = Image.open(src).convert("RGB"); tw, th = SW * 2, SH * 2
    r = max(tw / im.width, th / im.height)
    bg = im.resize((int(im.width * r) + 1, int(im.height * r) + 1))
    l, t = (bg.width - tw) // 2, (bg.height - th) // 2
    bg = bg.crop((l, t, l + tw, t + th)).filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", bg.size, (0, 0, 0)), 0.45)
    r = min(tw / im.width, (th * 0.5) / im.height)
    fg = im.resize((int(im.width * r), int(im.height * r)), Image.LANCZOS)
    bg.paste(fg, ((tw - fg.width) // 2, int(th * 0.36) - fg.height // 2))
    bg.save(dst, quality=92)


def short_text(scene, dst):
    img = Image.new("RGBA", (SW, SH), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    f2 = font(40); name = "Tareekh Ki Kahani"
    d.text(((SW - d.textlength(name, font=f2)) / 2, 150), name, font=f2, fill=(255, 255, 255, 200))
    text = latin_part(scene.get("text_on_screen", ""))
    if text:
        f = font(76); lines = wrap(d, text, f, SW - 140)[:4]; y = 1290
        for ln in lines:
            d.text(((SW - d.textlength(ln, font=f)) / 2, y), ln, font=f, fill=(255, 215, 80, 255),
                   stroke_width=6, stroke_fill=(0, 0, 0, 255)); y += 96
    img.save(dst)


async def tts(text, voice, out_mp3):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate="-4%").save(str(out_mp3))


def voice_text(scene):
    """Hindi voice reads narration_hi (Hindi script). Old episodes without it use the Urdu voice."""
    if scene.get("narration_hi"): return scene["narration_hi"], VOICE_HI
    return scene["narration_ur"], VOICE_UR


def wav_seconds(p):
    with wave.open(str(p)) as w: return w.getnframes() / w.getframerate()


def scene_audio(ep, i, scene, work, rec_dir=None):
    wav = work / f"{i:02d}.wav"
    mine = (rec_dir or RECS / ep) / f"{i:02d}.wav"
    if mine.exists():
        src, who = mine, "your voice"
    elif TEST:
        secs = max(3, len((scene.get("narration_roman") or scene.get("narration_hi", "")).split()) / 2.4)
        run(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{secs:.2f}", wav]); return wav, "test-silence"
    else:
        src = work / f"{i:02d}_ai.mp3"; who = "AI voice"
        if not src.exists():
            for attempt in range(3):
                try: asyncio.run(tts(*voice_text(scene), src)); break
                except Exception as e:
                    if attempt == 2: raise RuntimeError(f"AI voice failed (internet?): {e}")
    chain = "loudnorm=I=-16:TP=-1.5:LRA=11"
    if who == "your voice":
        try:
            import v2; chain = v2.VOICE_CHAIN + "," + chain
        except Exception: pass
    run(["-i", src, "-af", chain, "-ar", "48000", "-ac", "2", wav])
    return wav, who


MOTIONS = [
    ("min(1+0.12*on/{F},1.12)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),            # zoom in
    ("max(1.12-0.12*on/{F},1)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),            # zoom out
    ("1.12", "(iw-iw/zoom)*on/{F}", "ih/2-(ih/zoom/2)"),                             # pan right
    ("1.12", "(iw-iw/zoom)*(1-on/{F})", "ih/2-(ih/zoom/2)"),                         # pan left
    ("min(1+0.10*on/{F},1.10)", "(iw-iw/zoom)*0.3", "(ih-ih/zoom)*0.3"),           # zoom to upper-left
]


def make_clip(img2x, overlay, wav, out, secs, idx, w=W, h=H):
    frames = int(secs * FPS) + 1
    m = MOTIONS[idx % len(MOTIONS)] if w > h else MOTIONS[idx % 2]   # Shorts: zoom in / zoom out only
    z, x, y = [k.replace("{F}", str(frames)) for k in m]
    zoom = f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={FPS}"
    run(["-loop", "1", "-i", img2x, "-i", overlay, "-i", wav,
         "-filter_complex", f"[0:v]{zoom}[bg];[bg][1:v]overlay=0:0,format=yuv420p[v];[2:a]apad[a]",
         "-map", "[v]", "-map", "[a]", "-t", f"{secs:.2f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", FPS,
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", out])


TRANSITIONS = ["fade", "smoothleft", "circleopen", "dissolve", "slideleft", "fadeblack", "radial", "smoothright", "wiperight", "zoomin"]
XF = 0.8  # seconds of each transition


def join_with_transitions(clips, durs, out, work):
    """Join scene clips with a different smooth transition between every two scenes."""
    if len(clips) == 1: shutil.copy(clips[0], out); return
    v, a, parts, t = "[0:v]", "[0:a]", [], durs[0]
    for i in range(1, len(clips)):
        off = t - XF
        tr = TRANSITIONS[(i - 1) % len(TRANSITIONS)]
        parts.append(f"{v}[{i}:v]xfade=transition={tr}:duration={XF}:offset={off:.3f}[v{i}]")
        parts.append(f"{a}[{i}:a]acrossfade=d={XF}[a{i}]")
        v, a = f"[v{i}]", f"[a{i}]"
        t = off + durs[i]
    parts.append(f"{v}fade=t=in:st=0:d=0.6,fade=t=out:st={t-1:.2f}:d=1,format=yuv420p[vout]")
    script = work / "join_filter.txt"; script.write_text(";\n".join(parts), encoding="utf-8")
    args = []
    for c in clips: args += ["-i", c]
    tail = ["-map", "[vout]", "-map", a, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", FPS,
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", out]
    try:   # ffmpeg 7.1 and newer
        run(args + ["-/filter_complex", script] + tail)
    except RuntimeError:   # older ffmpeg
        run(args + ["-filter_complex_script", script] + tail)


def _download(url, dest):
    """Try Windows' own curl.exe first (uses Windows certificates), then Python."""
    tmp = dest.with_suffix(".part")
    curl = shutil.which("curl") or shutil.which("curl.exe")
    if curl:
        r = subprocess.run([curl, "-L", "-f", "-s", "-S", "--retry", "3", "-A", "Mozilla/5.0", "-o", str(tmp), url],
                           capture_output=True, text=True)
        if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 10000: return tmp
        err = r.stderr.strip()
    else:
        err = "curl not found"
    import urllib.request, ssl
    try:
        ctx = ssl.create_default_context()
        data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=90, context=ctx).read()
    except Exception:
        ctx = ssl._create_unverified_context()   # public image; Windows Python often lacks root certificates
        data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=90, context=ctx).read()
    tmp.write_bytes(data)
    if tmp.stat().st_size < 10000: raise RuntimeError(f"download too small ({err})")
    return tmp


def fetch_pictures(ep):
    """Download AI pictures listed in images\\tkNNN\\download.txt (lines: 'NN url').
    Returns True if any new picture was downloaded."""
    folder = IMGS / ep; lst = folder / "download.txt"; done = folder / ".downloaded"
    if not lst.exists(): return False
    have = set(done.read_text().split()) if done.exists() else set()
    new = False
    for line in lst.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 2 or parts[0] in have: continue
        n, url = parts
        print(f"  downloading AI picture {n} ...", end=" ", flush=True)
        try:
            tmp = _download(url, folder / f"{n}.jpg")
            Image.open(tmp).convert("RGB").save(folder / f"{n}.jpg", quality=93); tmp.unlink()
        except Exception as e:
            print("FAILED")
            raise RuntimeError(f"AI picture {n} could not be downloaded ({e}). Check internet and run RENDER.bat again. Nothing was rendered.")
        have.add(n); done.write_text("\n".join(sorted(have))); new = True; print("ok")
    return new


def thumbnail(ep, data, out):
    custom = IMGS / ep / "thumbnail.jpg"      # a ready-made thumbnail (e.g. with Urdu text) wins
    if custom.exists() and not data.get("thumb_ur"): shutil.copy(custom, out); return
    if data.get("thumb_ur"):                  # new episodes: Urdu + English thumbnail
        try:
            import v2; v2.thumb_card(data, ep, out); return
        except Exception as e: print(f"  (Urdu thumbnail failed: {e}; using the simple one)")
    first = []
    for pat in ("02.*", "01.*", "01a.*", "02a.*", "03a.*"):
        first = [p for p in sorted((IMGS / ep).glob(pat)) if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
        if first: break
    base = Image.open(first[0]).convert("RGB") if first else Image.new("RGB", (W, H), (20, 20, 30))
    r = max(1280 / base.width, 720 / base.height)
    base = base.resize((int(base.width * r) + 1, int(base.height * r) + 1)).crop((0, 0, 1280, 720))
    base = Image.blend(base, Image.new("RGB", base.size, (0, 0, 0)), 0.35)
    d = ImageDraw.Draw(base)
    title = data.get("thumb_text") or data["title"].split("–")[0].split("-")[0].strip()
    f = font(110); lines = wrap(d, title.upper(), f, 1180)[:3]
    y = 360 - len(lines) * 62
    for ln in lines:
        x = (1280 - d.textlength(ln, font=f)) / 2
        d.text((x, y), ln, font=f, fill=(255, 215, 80), stroke_width=8, stroke_fill=(0, 0, 0)); y += 125
    base.save(out, quality=94)


def update_status(ep):
    """Move 'tkNNN | ...' from SCRIPT SAVED to RENDERED in VIDEO_STATUS.txt."""
    p = ROOT / "VIDEO_STATUS.txt"
    if not p.exists(): return
    lines = p.read_text(encoding="utf-8").splitlines()
    sec, moved, out = None, None, []
    for ln in lines:
        if ln.startswith("RENDERED"): sec = "R"
        elif ln.startswith("SCRIPT SAVED"): sec = "S"
        elif ln.startswith("REMAINING"): sec = "X"
        if sec == "S" and ln.startswith(ep + " |"):
            import datetime; moved = ln + " | rendered " + datetime.date.today().isoformat(); continue
        out.append(ln)
    if not moved: return
    res, sec = [], None
    for i, ln in enumerate(out):
        if ln.startswith("RENDERED"): sec = "R"
        elif ln.startswith("SCRIPT SAVED"): sec = "S"
        if sec in ("R", "R2") and ln.strip() == "(none yet)": continue
        res.append(ln)
        if sec == "R" and ln.startswith("----"): res.append(moved); sec = "R2"
    # put "(none yet)" back if SCRIPT SAVED is empty
    for i, ln in enumerate(res):
        if ln.startswith("SCRIPT SAVED"):
            nxt = res[i + 2] if i + 2 < len(res) else ""
            if not nxt.strip(): res.insert(i + 2, "(none yet)")
            break
    p.write_text("\n".join(res) + "\n", encoding="utf-8")


SUB_SPEECH = {}   # label -> seconds of speech in every scene of the last build (for subtitles)


def _srt_time(t):
    ms = int(round(max(t, 0) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _chunks(text, limit=84):
    """Split a long sentence into subtitle-sized pieces."""
    out, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > limit: out.append(cur); cur = w
        else: cur = (cur + " " + w).strip()
    if cur: out.append(cur)
    if len(out) > 1 and len(out[-1]) < limit * 0.3:
        tail = out.pop(); out[-1] += " " + tail
    return out


def _ur_sentences(scene):
    return [x.strip() for x in re.findall(r"[^\u06d4\u061f!]+[\u06d4\u061f!]", scene.get("narration_ur", ""))]


def write_subs(ep, scenes, speech, out_dir):
    """Write tkNNN_subtitles_English.srt / _Urdu.srt (upload them to YouTube as captions).
    English comes from scene["subtitle_en"] (list of sentences), Urdu from scene["narration_ur"].
    Each sentence gets a share of its scene's speech time, by the length of the spoken (Urdu) sentence."""
    if len(speech) != len(scenes): return
    def en(sc):
        v = sc.get("subtitle_en") or []
        return [v] if isinstance(v, str) else list(v)
    for name, get in (("English", en), ("Urdu", _ur_sentences)):
        if not any(get(sc) for sc in scenes): continue
        cues, start = [], 0.0
        for sc, sp in zip(scenes, speech):
            sents, spoken = get(sc), _ur_sentences(sc)
            weights = [len(x) for x in (spoken if len(spoken) == len(sents) else sents)]
            total, t, span = (sum(weights) or 1), start + 0.1, max(sp - 0.2, 0.5)
            for sent, wgt in zip(sents, weights):
                win, parts = span * wgt / total, _chunks(sent)
                plen = sum(len(p) for p in parts) or 1
                for p in parts:
                    d = win * len(p) / plen; cues.append((t, t + d - 0.04, p)); t += d
            start += sp + 0.7
        (out_dir / f"{ep}_subtitles_{name}.srt").write_text(
            "".join(f"{k}\n{_srt_time(a)} --> {_srt_time(b)}\n{p}\n\n" for k, (a, b, p) in enumerate(cues, 1)), encoding="utf-8")


def find_pic(ep, n):
    stem = n if isinstance(n, str) and not n.isdigit() else f"{int(n):02d}"      # Shorts of new episodes use shot names like 03b
    pics = [p for p in (IMGS / ep).glob(f"{stem}.*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
    return pics[0] if pics else None


def build(ep, scenes, work, label, vertical=False, rec_dir=None):
    """Make one clip per scene and join them. Returns (joined file, missing picture numbers, voices used)."""
    work.mkdir(parents=True, exist_ok=True)
    w, h = (SW, SH) if vertical else (W, H)
    missing, voices, clips, durs = [], {}, [], []
    n = len(scenes)
    for i, sc in enumerate(scenes, 1):
        print(f"  {label} scene {i}/{n} ...", end=" ", flush=True)
        pic = find_pic(ep, sc.get("image", i))
        had = bool(pic)
        if not pic:
            pic = work / f"{i:02d}_placeholder.jpg"; placeholder(pic, sc, i); missing.append(sc.get("image", i))
        clip = work / f"{i:02d}.mp4"; wav = work / f"{i:02d}.wav"
        if clip.exists() and wav.exists() and clip.stat().st_size > 100000:   # finished in an earlier run
            secs = wav_seconds(wav) + 0.7; who = "reused"
        else:
            img2x = work / f"{i:02d}_2x.jpg"; ov = work / f"{i:02d}_text.png"
            if vertical: short_frame(pic, img2x); short_text(sc, ov)
            else: cover(pic, img2x); lower_third(sc, ov)
            wav, who = scene_audio(ep, i, sc, work, rec_dir)
            secs = wav_seconds(wav) + 0.7
            make_clip(img2x, ov, wav, clip, secs + XF, i - 1, w, h)
        voices[who] = voices.get(who, 0) + 1; clips.append(clip); durs.append(secs + XF)
        print(f"{secs:.0f}s ({who}{'' if had else ', NO PICTURE'})")
    SUB_SPEECH[label] = [d - XF - 0.7 for d in durs]
    joined = work / "joined.mp4"
    print("  joining scenes with transitions (this takes a few minutes) ...")
    join_with_transitions(clips, durs, joined, work)
    return joined, missing, voices


def add_music(joined, final):
    music = [m for m in MUSIC.glob("bed_calm.*") if m.suffix.lower() in (".mp3", ".wav", ".m4a")] if MUSIC.exists() else []
    if not music and MUSIC.exists():
        music = [m for m in MUSIC.glob("*") if m.suffix.lower() in (".mp3", ".wav", ".m4a") and not m.stem.startswith(("hit", "riser", "bed_tense", "bed_epic"))]
    if music:
        run(["-i", joined, "-stream_loop", "-1", "-i", music[0], "-filter_complex",
             "[1:a]volume=0.12[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", final])
    else:
        shutil.copy(joined, final)


def render(ep_file):
    ep = ep_file.stem
    data = json.loads(ep_file.read_text(encoding="utf-8"))
    out_dir = READY / ep; sh_dir = out_dir / "Shorts"
    (IMGS / ep).mkdir(parents=True, exist_ok=True)
    old = list(out_dir.glob("*.mp4")) if out_dir.exists() else []
    if data.get("format") == 2:
        import v2
        if v2.purge_banned(ep, data) and old:
            print(f"  {ep}: unsafe/old pictures removed - making the video again")
            for f in old: f.unlink()
            shutil.rmtree(sh_dir, ignore_errors=True); old = []
    if fetch_pictures(ep) and old:
        print(f"  {ep}: new pictures downloaded - making the video again")
        for f in old: f.unlink()
        shutil.rmtree(sh_dir, ignore_errors=True); old = []
    work = WORK / ep; out_dir.mkdir(parents=True, exist_ok=True)
    # the file name IS the video title, so YouTube fills the title box by itself
    final = out_dir / (safe_name(data["title"]) + ".mp4")
    if old:
        print(f"  {ep}: long video already rendered - skipped")
    elif data.get("format") == 2:
        import v2
        rep = v2.render_episode(ep, data, work, final, out_dir)
        thumbnail(ep, data, out_dir / f"{ep}_thumbnail.jpg")
        update_status(ep)
        print(f"  DONE: {final}  ({rep['seconds'] / 60:.1f} minutes; pictures downloaded: {rep['downloaded']}; without picture: {rep['missing_pictures']})")
    else:
        joined, missing, voices = build(ep, data["scenes"], work, ep)
        add_music(joined, final)
        thumbnail(ep, data, out_dir / f"{ep}_thumbnail.jpg")
        write_subs(ep, data["scenes"], SUB_SPEECH.get(ep, []), out_dir)
        if missing:
            (out_dir / "MISSING_PICTURES.txt").write_text(
                "These scenes used a plain title card because no picture was found in images\\" + ep + "\\\n"
                "Put a picture named like 05.jpg there, delete this video and run RENDER.bat again.\n\n" +
                "\n".join(f"{i:02d}.jpg  ->  {data['scenes'][i-1]['visual']}" for i in missing), encoding="utf-8")
        update_status(ep)
        print(f"  DONE: {final}  (voices: {voices}; missing pictures: {len(missing)})")
    up = EPIS / f"{ep}_upload.txt"
    if up.exists(): shutil.copy(up, out_dir / "upload.txt")
    for k, sh in enumerate(data.get("shorts", []), 1):   # vertical Shorts made from the same pictures
        sfinal = sh_dir / (safe_name(sh["title"]) + ".mp4")
        if sfinal.exists(): continue
        sh_dir.mkdir(parents=True, exist_ok=True)
        joined, _, _ = build(ep, sh["scenes"], work / f"short{k}", f"{ep} SHORT {k}", vertical=True,
                             rec_dir=RECS / ep / f"short{k}")
        add_music(joined, sfinal)
        print(f"  DONE: {sfinal}")
    shutil.rmtree(work, ignore_errors=True)


def main():
    eps = sorted(EPIS.glob("tk[0-9][0-9][0-9].json"))
    if not eps: print("No episodes found in", EPIS); return
    for e in eps:
        try: render(e)
        except Exception as ex: print(f"\n  ERROR in {e.stem}: {ex}")


if __name__ == "__main__":
    main()
