"""Tareekh Ki Kahani - video factory v2 (documentary style).

What it does for an episode whose JSON has  "format": 2 :
  * VOICE      your recording is cleaned (noise, rumble, clipping), given body + clarity, compressed and levelled
  * PICTURES   every scene gets a new moving picture every 5-8 seconds (zoom / pan, grain, vignette, smooth fades).
               Pictures come from  images\\tkNNN\\<name>.jpg  or are found automatically on Wikimedia Commons
               from the search words written in the shot; if nothing is found a moving title card is used.
  * MUSIC      original background music (music\\bed_*.wav) that gets quiet when you speak,
               a riser + big drum hit at every chapter change, optional hits for dramatic scenes
  * SUBTITLES  Urdu subtitles burned into the video + an English .srt file (and an Urdu .srt) to upload to YouTube
"""
import asyncio, json, math, os, re, shutil, subprocess, sys, wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

ROOT = Path(__file__).resolve().parent.parent
IMGS = ROOT / "images"; RECS = ROOT / "recordings"; MUSIC = ROOT / "music"
W, H, FPS = 1920, 1080, 30

def _need(mod, pip_name=None):
    """Import a package; if it is missing, install it automatically (needs internet once)."""
    import importlib
    try: return importlib.import_module(mod)
    except ImportError:
        print(f"  installing {pip_name or mod} (one time) ...", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--quiet", pip_name or mod], check=False)
        importlib.invalidate_caches()
        try: return importlib.import_module(mod)
        except ImportError: return None


_SCIPY_OK = _need("scipy") is not None

SR = 48000
XF = 15                    # frames of cross-fade between two pictures (0.5 s)
GAP = 0.45                 # seconds of breathing space after every scene
CARD = 3.0                 # seconds of a chapter card
PRESET = os.environ.get("TK_PRESET", "veryfast")
CRF = os.environ.get("TK_CRF", "18")          # single shots (they are encoded once more later)
FINAL_CRF = os.environ.get("TK_FINAL_CRF", "21")
BURN = [x.strip() for x in os.environ.get("TK_BURN", "").split(",") if x.strip()]   # "" = none (YouTube subtitles only); "ur" or "ur,en" burns them in
TEST = os.environ.get("TK_TEST") == "1"
MUSIC_GAIN = float(os.environ.get("TK_MUSIC", "0.85"))      # 0.7 = quieter music, 1.4 = louder
AI_VOICE = os.environ.get("TK_VOICE_UR", "ur-PK-AsadNeural")
UA = "TareekhKiKahani/1.0 (history documentary channel; sibghattranslator@gmail.com)"


# ----------------------------------------------------------------------------- basics
def ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe: return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run(args, capture=False):
    r = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"] + [str(a) for a in args],
                       capture_output=capture)
    if r.returncode:
        raise RuntimeError("ffmpeg failed: " + " ".join(map(str, args[:8])) + ((" | " + r.stderr.decode(errors="ignore")[-300:]) if capture else ""))
    return r


def frames_to_s(n): return n / FPS


# ----------------------------------------------------------------------------- fonts and text
_FONT_DIRS = [ROOT / "factory" / "fonts", Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
              Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/truetype/noto")]
_LATIN_B = ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]
_LATIN_R = ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]
# Urdu candidates, best first. Any .ttf you put in factory\fonts is tried first.
_URDU_CAND = ["NotoNaskhArabic-Bold.ttf", "NotoNaskhArabic-Regular.ttf", "NotoNaskhArabic[wght].ttf", "segoeuib.ttf", "tahomabd.ttf",
              "arialbd.ttf", "segoeui.ttf", "tahoma.ttf", "arial.ttf", "times.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"]
_NOTO_URL = "https://github.com/google/fonts/raw/main/ofl/notonaskharabic/NotoNaskhArabic%5Bwght%5D.ttf"
URDU_TEST = "ٹ ڈ ڑ ں ے ہ ھ گ چ پ ژ ک ی ء آ أ ؤ ئ ۔ ؟ ب ت ث ج ح خ د ذ ر ز س ش ص ض ط ظ ع غ ف ق ل م ن و"
_fc = {}


def _font(names, size, basic=False):
    key = (tuple(names), size, basic)
    if key in _fc: return _fc[key]
    for n in names:
        for d in _FONT_DIRS:
            p = d / n
            if p.exists():
                kw = {"layout_engine": ImageFont.Layout.BASIC} if basic else {}
                _fc[key] = ImageFont.truetype(str(p), size, **kw); return _fc[key]
    _fc[key] = ImageFont.load_default(); return _fc[key]


def latin(size, bold=True): return _font(_LATIN_B if bold else _LATIN_R, size)


def shape(text):
    """Fallback engine: join the Urdu letters ourselves and reverse them (Pillow draws left to right)."""
    import arabic_reshaper
    try: from bidi import get_display
    except Exception: from bidi.algorithm import get_display
    return get_display(arabic_reshaper.reshape(text))


def _raqm_ok():
    try:
        from PIL import features
        if not features.check("raqm"): return False
        f = ImageFont.truetype(str(_find_any(["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"])), 30,
                               layout_engine=ImageFont.Layout.RAQM)
        Image.new("RGBA", (200, 80)).getbbox(); d = ImageDraw.Draw(Image.new("RGBA", (200, 80)))
        d.text((5, 5), "کے", font=f, direction="rtl", language="ur"); return True
    except Exception:
        return False


def _find_any(names):
    for n in names:
        for d in _FONT_DIRS:
            if (d / n).exists(): return d / n
    return None


def _glyph(f, ch, mode):
    im = Image.new("L", (90, 90), 0); d = ImageDraw.Draw(im)
    if mode == "raqm": d.text((10, 5), ch, font=f, fill=255, direction="rtl", language="ur")
    else: d.text((10, 5), ch, font=f, fill=255)
    return im.tobytes()


def _has_glyphs(path, mode):
    """True if the font really draws every Urdu letter (a missing letter draws as an empty box)."""
    try:
        eng = ImageFont.Layout.RAQM if mode == "raqm" else ImageFont.Layout.BASIC
        f = ImageFont.truetype(str(path), 40, layout_engine=eng)
        text = URDU_TEST if mode == "raqm" else shape(URDU_TEST)
        blank = _glyph(f, "\ue0ff", mode)
        return all(_glyph(f, ch, mode) != blank for ch in text if ch != " ")
    except Exception:
        return False



# ----------------------------------------------------------------------------- Nastaleeq without libraqm (HarfBuzz)
_HB = {}


def _hb(path):
    if path not in _HB:
        import uharfbuzz as hb
        blob = hb.Blob.from_file_path(str(path)); face = hb.Face(blob); _HB[path] = (hb, face, hb.Font(face))
    return _HB[path]


def _hb_shape(text, path, px):
    hb, face, font = _hb(path)
    text = re.sub(r"[A-Za-z0-9.%+\u0660-\u0669\u06f0-\u06f9]+", lambda m: m.group()[::-1], text)   # numbers/latin read left-to-right
    buf = hb.Buffer(); buf.add_str(text); buf.direction = "rtl"; buf.script = "Arab"; buf.language = "ur"
    hb.shape(font, buf, {})
    return buf.glyph_infos, buf.glyph_positions, px / face.upem


def hb_width(text, path, px):
    _, pos, s = _hb_shape(text, path, px)
    return sum(p.x_advance for p in pos) * s


def _flatten(ops, tx, ty, s):
    """TrueType outline (RecordingPen ops) -> list of polygons [(x, y), ...] in pixels (y down)."""
    from fontTools.pens.basePen import decomposeQuadraticSegment
    polys, cur, last = [], [], None
    def pt(p): return (tx + p[0] * s, ty - p[1] * s)
    def quad(p0, p1, p2, n=8):
        return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
                 (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in [i / n for i in range(1, n + 1)]]
    for op, args in ops:
        if op == "moveTo": cur = [pt(args[0])]; last = args[0]
        elif op == "lineTo": cur.append(pt(args[0])); last = args[0]
        elif op == "qCurveTo":
            pts = list(args)
            if pts[-1] is None:                                   # closed contour made only of off-curve points
                pts = pts[:-1]; start = ((pts[-1][0] + pts[0][0]) / 2, (pts[-1][1] + pts[0][1]) / 2); last = start; cur = [pt(start)]; pts.append(start)
            for c, e in decomposeQuadraticSegment(pts):
                for q in quad(last, c, e): cur.append(pt(q))
                last = e
        elif op == "curveTo":
            c1, c2, e = args
            for i in range(1, 9):
                t = i / 8
                x = (1 - t) ** 3 * last[0] + 3 * (1 - t) ** 2 * t * c1[0] + 3 * (1 - t) * t * t * c2[0] + t ** 3 * e[0]
                y = (1 - t) ** 3 * last[1] + 3 * (1 - t) ** 2 * t * c1[1] + 3 * (1 - t) * t * t * c2[1] + t ** 3 * e[1]
                cur.append(pt((x, y)))
            last = e
        elif op in ("closePath", "endPath"):
            if len(cur) > 2: polys.append(cur)
            cur = []
    return polys


def hb_draw(img, text, path, px, x, y, fill, stroke=0, stroke_fill=(0, 0, 0, 255)):
    """Draw Nastaleeq text (left edge x, top y) onto an RGBA image. Same look as Pillow+raqm, but only needs uharfbuzz."""
    from fontTools.pens.recordingPen import DecomposingRecordingPen
    hb, face, font = _hb(path)
    infos, pos, s = _hb_shape(text, path, px)
    ext = font.get_font_extents("ltr"); asc = ext.ascender * s; desc = -ext.descender * s
    width = sum(p.x_advance for p in pos) * s
    pad = int(px * 0.35) + stroke * 2 + 4; SS = 3
    w, h = int(width) + 2 * pad, int(asc + desc) + 2 * pad
    mask = Image.new("L", (w * SS, h * SS), 0)
    cx = 0.0
    for info, p in zip(infos, pos):
        pen = DecomposingRecordingPen(None) if False else None
        from fontTools.pens.recordingPen import RecordingPen
        pen = RecordingPen()
        try: font.draw_glyph_with_pen(info.codepoint, pen)
        except Exception: pen = None
        if pen is not None and pen.value:
            ox = pad + cx + p.x_offset * s; oy = pad + asc - p.y_offset * s
            polys = _flatten(pen.value, ox, oy, s)
            if polys:
                xs = [q[0] for pl in polys for q in pl]; ys = [q[1] for pl in polys for q in pl]
                bx0, by0 = int(min(xs)) - 2, int(min(ys)) - 2; bx1, by1 = int(max(xs)) + 3, int(max(ys)) + 3
                g = Image.new("L", ((bx1 - bx0) * SS, (by1 - by0) * SS), 0); gd = ImageDraw.Draw(g)
                def area(pl): return sum(pl[i][0] * pl[(i + 1) % len(pl)][1] - pl[(i + 1) % len(pl)][0] * pl[i][1] for i in range(len(pl)))
                sc = lambda pl: [((q[0] - bx0) * SS, (q[1] - by0) * SS) for q in pl]
                for pl in polys:
                    if area(pl) > 0: gd.polygon(sc(pl), fill=255)           # y flipped: positive area = outer contour
                for pl in polys:
                    if area(pl) <= 0: gd.polygon(sc(pl), fill=0)            # counters
                mask.paste(ImageChops.lighter(mask.crop((bx0 * SS, by0 * SS, bx1 * SS, by1 * SS)), g), (bx0 * SS, by0 * SS))
        cx += p.x_advance * s
    m = mask.resize((w, h), Image.LANCZOS)
    dest = (int(round(x)) - pad, int(round(y)) - pad)
    def put(color, mk):
        a = mk.point(lambda v: int(v * color[3] / 255))
        layer = Image.new("RGBA", (w, h), tuple(color[:3]) + (0,)); layer.putalpha(a)
        L, T = max(dest[0], 0), max(dest[1], 0); R, B = min(dest[0] + w, img.width), min(dest[1] + h, img.height)
        if R <= L or B <= T: return
        sub = layer.crop((L - dest[0], T - dest[1], R - dest[0], B - dest[1]))
        base = img.crop((L, T, R, B)); img.paste(Image.alpha_composite(base, sub), (L, T))
    if stroke: put(stroke_fill, m.filter(ImageFilter.MaxFilter(2 * stroke + 1)))
    put(fill, m)


_UR = {}
_JN_URLS = ["https://cdn.jsdelivr.net/npm/jameel-noori/fonts/jameel-noori-nastaleeq4.woff2",
            "https://unpkg.com/jameel-noori/fonts/jameel-noori-nastaleeq4.woff2"]


def _jameel():
    """factory\\fonts\\JameelNoori.ttf - made once from the free web font (needs internet one time)."""
    dst = ROOT / "factory" / "fonts" / "JameelNoori.ttf"
    if dst.exists() and dst.stat().st_size > 1_000_000: return dst
    try:
        dst.parent.mkdir(exist_ok=True); print("  getting Jameel Noori Nastaleeq (one time) ...", flush=True)
        data = None
        for u in _JN_URLS:
            try: data = _http_get(u, 180); break
            except Exception: continue
        if not data: return None
        _need("brotli"); _need("fontTools", "fonttools")
        from fontTools.ttLib import TTFont
        import io
        f = TTFont(io.BytesIO(data)); f.flavor = None; f.save(str(dst))
        return dst
    except Exception as e:
        print(f"  (Jameel Noori not available: {e})"); return None


def urdu_setup():
    """Pick the Urdu drawing method + font once. Result: {'mode': 'raqm'|'shaped'|None, 'path': Path}."""
    if _UR: return _UR
    modes = (["raqm"] if _raqm_ok() else []) + ["shaped"]
    def pick():
        folder = ROOT / "factory" / "fonts"
        own = sorted(folder.glob("*.ttf")) if folder.exists() else []
        cands = own + [p for p in (_find_any([n]) for n in _URDU_CAND) if p]
        for mode in modes:
            if mode == "shaped":
                try: import arabic_reshaper  # noqa
                except Exception: continue
            for p in cands:
                if _has_glyphs(p, mode): return {"mode": mode, "path": p}
        return None
    r = pick()
    try:                                                # Jameel Noori Nastaleeq, when the machine can shape it
        if _raqm_ok():
            jp = _jameel()
            if jp and _has_glyphs(jp, "raqm"): r = {"mode": "raqm", "path": jp}
    except Exception as e:
        print(f"  (Jameel Noori not used: {e})")
    try:                                                # no libraqm on this PC: HarfBuzz draws the Nastaleeq itself
        jp = ROOT / "factory" / "fonts" / "JameelNoori.ttf"
        if (os.environ.get("TK_FORCE_HB") == "1" or not _raqm_ok()) and jp.exists() and jp.stat().st_size > 1_000_000:
            if _need("uharfbuzz") and _need("fontTools", "fonttools"):
                _hb(jp); r = {"mode": "hb", "path": jp}
    except Exception as e:
        print(f"  (HarfBuzz Nastaleeq not used: {e})")
    if not r:                                           # last chance: download a free Urdu-capable font once
        try:
            dst = ROOT / "factory" / "fonts" / "NotoNaskhArabic[wght].ttf"; dst.parent.mkdir(exist_ok=True)
            print("  downloading a free Urdu font (one time) ...", flush=True)
            dst.write_bytes(_http_get(_NOTO_URL, 120)); r = pick()
        except Exception as e:
            print(f"  (could not download an Urdu font: {e})")
    _UR.update(r or {"mode": None, "path": None})
    print(f"  Urdu text: {_UR['mode']} / {_UR['path'].name if _UR['path'] else 'NO FONT'}")
    return _UR


def urdu(size, bold=True):
    u = urdu_setup()
    if not u["mode"]: return ImageFont.load_default()
    key = ("ur", size)
    if key not in _fc:
        eng = ImageFont.Layout.RAQM if u["mode"] == "raqm" else ImageFont.Layout.BASIC
        sz = int(size * 1.3) if "Jameel" in u["path"].name else size   # Nastaleeq draws small
        f = ImageFont.truetype(str(u["path"]), sz, layout_engine=eng)
        try:                                                # variable font: take the bold weight
            if "wght" in u["path"].name or "[" in u["path"].name: f.set_variation_by_name("Bold")
        except Exception: pass
        _fc[key] = f
    return _fc[key]


_AR_DIG = str.maketrans("0123456789", "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9")


def clean_ur(text):
    """Swap characters that the chosen Urdu font cannot draw (they show as boxes)."""
    u = _UR or {}
    if u.get("path") is not None and "Jameel" in u["path"].name: return text
    t = text.replace("\u2014", "\u060c").replace("\u2013", "\u060c").replace("\u00b7", " ").replace(":", "\u060c")
    t = t.replace(",", "\u060c").replace("?", "\u061f").replace(";", "\u061b").replace("!", "").replace(".", "\u06d4")
    t = t.replace("(", "").replace(")", "").replace('"', "").replace("-", " ").replace("/", " ").replace("%", "")
    return t.translate(_AR_DIG)


def has_rtl(s): return any("\u0600" <= c <= "\u06ff" for c in s)


def tlen(d, text, f, rtl=False):
    if not rtl: return d.textlength(text, font=f)
    u = urdu_setup(); text = clean_ur(text)
    if u["mode"] == "hb": return hb_width(text, u["path"], f.size)
    if u["mode"] == "raqm": return d.textlength(text, font=f, direction="rtl", language="ur")
    return d.textlength(shape(text) if u["mode"] else text, font=f)


def wrap(d, text, f, maxw, rtl=False):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if tlen(d, t, f, rtl) <= maxw: cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines


def draw_at(d, text, f, x, y, fill, rtl=False, stroke=0, stroke_fill=(0, 0, 0, 255)):
    """Draw text with its left edge at x."""
    if rtl: urdu_setup(); text = clean_ur(text)
    kw = dict(font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
    if rtl:
        u = urdu_setup()
        if u["mode"] == "hb": hb_draw(d._image, text, u["path"], f.size, x, y, fill, stroke, stroke_fill); return
        if u["mode"] == "raqm": d.text((x, y), text, direction="rtl", language="ur", **kw); return
        if u["mode"] == "shaped": text = shape(text)
    d.text((x, y), text, **kw)


def draw_c(d, text, f, cx, y, fill, rtl=False, stroke=0, stroke_fill=(0, 0, 0, 255)):
    draw_at(d, text, f, cx - tlen(d, text, f, rtl) / 2, y, fill, rtl, stroke, stroke_fill)


# ----------------------------------------------------------------------------- overlay pictures
def sub_png(ur, en, dst, show_en=False):
    """Subtitle: Urdu (and optionally English) at the bottom, on a soft dark band."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    fu, fe = urdu(64), latin(36)
    blocks = []                                    # (text, font, rtl, height)
    if ur:
        for ln in wrap(d, ur, fu, 1500, True)[:2]: blocks.append((ln, fu, True, 88))
    if show_en and en:
        for ln in wrap(d, en, fe, 1500)[:2]: blocks.append((ln, fe, False, 50))
    if not blocks: img.save(dst); return
    total = sum(b[3] for b in blocks); widest = max(tlen(d, b[0], b[1], b[2]) for b in blocks)
    pad = 26; bottom = H - 52; top = bottom - total - 2 * pad
    d.rounded_rectangle([(W - widest) / 2 - 44, top, (W + widest) / 2 + 44, bottom], radius=22, fill=(0, 0, 0, 150))
    y = top + pad - 4
    for text, f, rtl, h in blocks:
        draw_c(d, text, f, W / 2, y, (255, 255, 255, 255) if rtl else (255, 214, 120, 255), rtl, stroke=2)
        y += h
    img.save(dst)


def key_png(en, ur, dst):
    """Key name / date panel in the top-left corner."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    fe, fu = latin(50), urdu(50)
    w1 = tlen(d, en, fe) if en else 0; w2 = tlen(d, ur, fu, True) if ur else 0
    w = max(w1, w2) + 70; h = (64 if en else 0) + (72 if ur else 0) + 30
    x0, y0 = 60, 60
    d.rectangle([x0, y0, x0 + w, y0 + h], fill=(0, 0, 0, 165))
    d.rectangle([x0, y0, x0 + 10, y0 + h], fill=(225, 170, 60, 255))
    y = y0 + 12
    if en: d.text((x0 + 36, y), en, font=fe, fill=(255, 255, 255, 255)); y += 64
    if ur: draw_at(d, ur, fu, x0 + w - 28 - w2, y, (255, 214, 120, 255), True)
    img.save(dst)


def _noise_bg(c1, c2, seed=3):
    rng = np.random.default_rng(seed)
    y = np.linspace(0, 1, H)[:, None, None]
    base = (np.array(c1)[None, None, :] * (1 - y) + np.array(c2)[None, None, :] * y) * np.ones((H, W, 3))
    xx, yy = np.meshgrid(np.linspace(-1, 1, W), np.linspace(-1, 1, H))
    glow = np.exp(-((xx * 0.8) ** 2 + (yy * 1.1) ** 2) * 2.2)[:, :, None] * np.array([70, 42, 18])[None, None, :]
    noise = rng.normal(0, 5, (H, W, 1))
    return Image.fromarray(np.clip(base + glow + noise, 0, 255).astype("uint8"))


def _star(d, cx, cy, r, rot, fill):
    pts = []
    for k in range(16):
        ang = rot + k * math.pi / 8; rr = r if k % 2 == 0 else r * 0.72
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    d.polygon(pts, outline=fill)


def card_bg(dst, seed=3, warm=True):
    """Dark textured background with a faint geometric star - used for title cards and missing pictures."""
    bg = _noise_bg((34, 22, 16) if warm else (16, 22, 34), (8, 6, 6) if warm else (6, 8, 12), seed)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    for k, r in enumerate((470, 400, 330, 260)):
        _star(d, W / 2, H / 2, r, k * math.pi / 16, (225, 170, 60, 38 + 10 * k))
        d.ellipse([W / 2 - r * 0.97, H / 2 - r * 0.97, W / 2 + r * 0.97, H / 2 + r * 0.97], outline=(225, 170, 60, 22))
    d.rectangle([40, 40, W - 40, H - 40], outline=(225, 170, 60, 90), width=3)
    d.rectangle([58, 58, W - 58, H - 58], outline=(225, 170, 60, 45), width=1)
    bg = Image.alpha_composite(bg.convert("RGBA"), ov).convert("RGB")
    bg.save(dst, quality=93)


def card_text(dst, lines, y_center=H // 2):
    """lines: list of (text, size, color, is_urdu)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    items = []
    for text, size, color, rtl in lines:
        f = urdu(size) if rtl else latin(size)
        for ln in wrap(d, text, f, W - 420, rtl)[:3]: items.append((ln, f, color, rtl, int(f.size * 1.5) if rtl else int(size * 1.35)))   # Nastaleeq is tall: give it room
    total = sum(i[4] for i in items); y = y_center - total // 2
    for ln, f, color, rtl, h in items:
        draw_c(d, ln, f, W / 2, y, color, rtl, stroke=3); y += h
    img.save(dst)


# ----------------------------------------------------------------------------- pictures
def find_pic(ep, stem):
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        p = IMGS / ep / f"{stem}{ext}"
        if p.exists(): return p
    return None


def find_vid(ep, stem):
    """A real video clip dropped into images\\<ep>\\ with the shot's name (for example 01a.mp4) is used instead of a picture."""
    for ext in (".mp4", ".mov", ".webm", ".mkv"):
        p = IMGS / ep / f"{stem}{ext}"
        if p.exists(): return p
    return None


def video_clip(src, frames, out):
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},{GRADE},format=yuv420p"
    run(["-stream_loop", "-1", "-i", src, "-vf", vf, "-frames:v", frames, "-an", "-c:v", "libx264", "-preset", PRESET,
         "-crf", CRF, "-pix_fmt", "yuv420p", "-r", FPS, out])


def norm_shots(si, sc):
    """Every scene gets a list of shot dicts: {stem, search, kind, ur, en, w}."""
    out = []
    raw = sc.get("shots") or []
    if not raw:                                      # old style: one picture per scene
        raw = [{"img": f"{sc.get('image', si):02d}"}]
    for k, s in enumerate(raw):
        if isinstance(s, str): s = {"search": s}
        s = dict(s)
        if s.get("skip"): continue                       # checked by hand: wrong picture -> shot dropped (letters of the others stay the same)
        s.setdefault("img", f"{si:02d}{chr(97 + k)}"); s["stem"] = s["img"]
        s.setdefault("w", 1.0)
        out.append(s)
    return out


def cover2x(src, dst, w=W, h=H):
    im = Image.open(src).convert("RGB"); tw, th = w * 2, h * 2
    r = max(tw / im.width, th / im.height)
    im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1), Image.LANCZOS)
    l, t = (im.width - tw) // 2, (im.height - th) // 2
    im.crop((l, t, l + tw, t + th)).save(dst, quality=93)


MOTIONS = [
    ("min(1+0.16*on/{F},1.16)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),            # slow push in
    ("1.14", "(iw-iw/zoom)*on/{F}", "ih/2-(ih/zoom/2)"),                             # pan right
    ("max(1.16-0.16*on/{F},1)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),            # pull out
    ("1.14", "(iw-iw/zoom)*(1-on/{F})", "ih/2-(ih/zoom/2)"),                         # pan left
    ("min(1+0.14*on/{F},1.14)", "(iw-iw/zoom)*0.25", "(ih-ih/zoom)*(0.9-0.8*on/{F})"),  # drift up-left
    ("min(1+0.14*on/{F},1.14)", "(iw-iw/zoom)*0.75", "(ih-ih/zoom)*(0.1+0.8*on/{F})"),  # drift down-right
]
TRANS = ["fade", "smoothleft", "dissolve", "smoothright", "slideleft", "fadeblack", "wipeleft", "circleopen"]
GRADE = "eq=contrast=1.06:saturation=1.10:gamma=0.97,vignette=PI/5"


def shot_clip(img2x, frames, motion, out):
    z, x, y = [k.replace("{F}", str(frames)) for k in MOTIONS[motion % len(MOTIONS)]]
    vf = f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS},{GRADE},format=yuv420p"
    run(["-i", img2x, "-vf", vf, "-frames:v", frames, "-c:v", "libx264", "-preset", PRESET, "-crf", CRF,
         "-pix_fmt", "yuv420p", "-r", FPS, out])


WM_PNG = [None]


def make_watermark(path):
    """Small see-through channel mark in the top-right corner (Urdu name + English name)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    a = 85
    fe = latin(20, True); fu = urdu(27, True)
    en = "TAREEKH KI KAHANI"; ur = "تاریخ کی کہانی"
    we = tlen(d, en, fe); wu = tlen(d, ur, fu, True)
    x_right = W - 36
    draw_at(d, en, fe, x_right - we, 82, (255, 255, 255, a), stroke=1, stroke_fill=(0, 0, 0, 70))
    draw_at(d, ur, fu, x_right - wu, 34, (255, 255, 255, a), rtl=True, stroke=1, stroke_fill=(0, 0, 0, 70))
    img.save(path); return str(path)


def compose(clips, vis, overlays, out, ep_seed=0):
    """One pass: cross-fade the shot clips (clips[j] is vis[j]+XF frames long, the last one vis[-1])
    and burn the overlays on top.  overlays: [(png, start_s, end_s, fade)].  Output has sum(vis) frames."""
    total = sum(vis); n = len(clips)
    args = []
    for c in clips: args += ["-i", c]
    for png, *_ in overlays: args += ["-loop", "1", "-framerate", FPS, "-i", png]
    wm = WM_PNG[0] if WM_PNG and WM_PNG[0] and Path(WM_PNG[0]).exists() else None
    if wm: args += ["-loop", "1", "-framerate", FPS, "-i", wm]
    parts, prev, acc = [], "[0:v]", 0
    for k in range(1, n):
        acc += vis[k - 1]
        tr = TRANS[(ep_seed + k - 1) % len(TRANS)]
        parts.append(f"{prev}[{k}:v]xfade=transition={tr}:duration={XF / FPS:.4f}:offset={acc / FPS:.4f}[x{k}]")
        prev = f"[x{k}]"
    for k, (png, a, b, fade) in enumerate(overlays):
        src = f"[{n + k}:v]"
        if fade:
            parts.append(f"{src}format=rgba,fade=t=in:st={a:.2f}:d=0.35:alpha=1,fade=t=out:st={max(b - 0.35, a):.2f}:d=0.35:alpha=1[o{k}]")
            src = f"[o{k}]"
        parts.append(f"{prev}{src}overlay=0:0:enable='between(t,{a:.3f},{b:.3f})'[y{k}]")
        prev = f"[y{k}]"
    if wm:
        parts.append(f"{prev}[{n + len(overlays)}:v]overlay=0:0[wm]"); prev = "[wm]"
    if not parts: parts.append(f"{prev}null[z]"); prev = "[z]"
    run(args + ["-filter_complex", ";".join(parts), "-map", prev, "-frames:v", total, "-c:v", "libx264",
                "-preset", PRESET, "-crf", FINAL_CRF, "-pix_fmt", "yuv420p", "-r", FPS, out])


# ----------------------------------------------------------------------------- Wikimedia Commons
_DOH = {}
_KNOWN_IP = {"commons.wikimedia.org": "103.102.166.224", "en.wikipedia.org": "103.102.166.224",
             "upload.wikimedia.org": "103.102.166.240", "www.wikidata.org": "103.102.166.224"}   # Wikimedia edge addresses (checked 2026-11-12)


def _doh(host):
    """Backup DNS: ask Google / Cloudflare directly (by IP) when this computer's own DNS cannot find the site."""
    if host in _DOH: return _DOH[host]
    import urllib.request, ssl
    for base in ("https://8.8.8.8/resolve?name=%s&type=A", "https://1.1.1.1/dns-query?name=%s&type=A", "https://dns.google/resolve?name=%s&type=A"):
        try:
            req = urllib.request.Request(base % host, headers={"accept": "application/dns-json", "User-Agent": UA})
            try: raw = urllib.request.urlopen(req, timeout=15).read()
            except Exception: raw = urllib.request.urlopen(req, timeout=15, context=ssl._create_unverified_context()).read()
            j = json.loads(raw.decode())
            ips = [a["data"] for a in j.get("Answer", []) if a.get("type") == 1]
            if ips: _DOH[host] = ips[0]; return ips[0]
        except Exception: continue
    _DOH[host] = _KNOWN_IP.get(host)                                   # last resort: address written into the program
    return _DOH[host]


def _get_via_ip(url, timeout=60):
    import urllib.request, urllib.parse, http.client, socket, ssl
    u = urllib.parse.urlparse(url); host = u.hostname; ip = _doh(host)
    if not ip: raise OSError("backup DNS also failed for " + host)
    curl = shutil.which("curl") or shutil.which("curl.exe")
    if curl:
        r = subprocess.run([curl, "-L", "-f", "-s", "-S", "--retry", "2", "--resolve", f"{host}:443:{ip}", "-A", UA, url], capture_output=True)
        if r.returncode == 0 and r.stdout: return r.stdout
    ctx = ssl.create_default_context()

    class Conn(http.client.HTTPSConnection):
        def connect(self):
            sock = socket.create_connection((ip, self.port or 443), self.timeout)
            self.sock = ctx.wrap_socket(sock, server_hostname=host)

    class H(urllib.request.HTTPSHandler):
        def https_open(self, req): return self.do_open(Conn, req)
    op = urllib.request.build_opener(H())
    op.addheaders = [("User-Agent", UA)]
    return op.open(url, timeout=timeout).read()


def _http_get(url, timeout=60):
    curl = shutil.which("curl") or shutil.which("curl.exe")
    if curl:
        r = subprocess.run([curl, "-L", "-f", "-s", "-S", "--retry", "2", "-A", UA, url], capture_output=True)
        if r.returncode == 0 and r.stdout: return r.stdout
    import urllib.request, ssl
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try: return urllib.request.urlopen(req, timeout=timeout).read()
    except Exception as e1:
        try: return urllib.request.urlopen(req, timeout=timeout, context=ssl._create_unverified_context()).read()
        except Exception as e2:
            try: return _get_via_ip(url, timeout)                      # this computer's DNS cannot find the site -> backup DNS
            except Exception as e3: raise e2 if "11001" not in str(e2) and "getaddrinfo" not in str(e2) else e3


def _clean(s): return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


# Safety: never show banned-organisation / militant / separatist material (a flag of such a group can put the presenter in danger in Pakistan)
_BAN = re.compile(r"\bBLA\b|baloch(istan)? liberation|liberation army|\bBLF\b|\bBRA\b|separatis|insurgen|militant|terror|rebel|guerr|fighters|"
                  r"flag|banner|emblem|massacre|attack|bombing|jaish|lashkar|\bTTP\b|\bISIS\b|al-?qaeda|extremis|jihad|suicide|"
                  r"taliban|offensive|pompeo|negotiat|mutin|assassinat|hoplite|killing|mad ?max|fury|execut|corpse|prison|guantanamo", re.I)


def purge_banned(ep, data=None):
    """Delete already-downloaded pictures that break the safety rule, and refresh shots the script asked to refresh."""
    folder = IMGS / ep; n = 0
    cf = folder / "credits.txt"; uf = folder / "commons_used.json"
    if cf.exists():
        keep = []
        for ln in cf.read_text(encoding="utf-8").splitlines():
            stem = ln.split("|")[0].strip(); title = ln.split("|")[1] if "|" in ln else ""
            if _BAN.search(title):
                for ext in (".jpg", ".jpeg", ".png", ".webp"):
                    f = folder / f"{stem}{ext}"
                    if f.exists(): f.unlink(); n += 1
            else: keep.append(ln)
        if n: cf.write_text("\n".join(keep), encoding="utf-8")
    rp = (data or {}).get("refresh_pics") or {}
    mark = folder / f".refresh_v{rp.get('v', 0)}"
    if rp.get("all") and not mark.exists():                      # start the pictures again from scratch
        for f in folder.glob("*"):
            if re.fullmatch(r"\d\d[a-z]\.(jpg|jpeg|png|webp)", f.name): f.unlink(); n += 1
        for nm in ("commons_used.json", "credits.txt"):
            if (folder / nm).exists(): (folder / nm).unlink()
        mark.write_text("done", encoding="utf-8")
    if rp.get("stems") and not mark.exists():
        for stem in rp["stems"]:
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                f = folder / f"{stem}{ext}"
                if f.exists(): f.unlink(); n += 1
        mark.write_text("done", encoding="utf-8")
    rv = (data or {}).get("rerender_v")
    rm = folder / f".rerender_v{rv}"
    if rv and not rm.exists():
        rm.write_text("done", encoding="utf-8"); n += 1                  # forces the video to be made again once
    return n


_COMMONS_DEAD = [False]
_JUNK = re.compile(r"\d{6}-D-|\bnavy\b|\bseals?\b|\barmy\b|marines?\b|operation|soldier|troop|military|cricket|\bvs\b|shahid|shaheen|imran|bhutto|hilal|feld|restaurant|kabab|kebab|bread|hound|stadium|economic forum|\bwef\b|literacy|princes of hope|kartarpur|gurdwara|genealogy library|nordisk|webley|revolver|guardi|football|player|parable|unforgiving|graph\b|mercedes|jersey|\bgym\b|concert|actor|actress|singer|minister|president|chief of|general\b|screenshot|microsoft|office|powerpoint|interchange|cloverleaf|unleashing|marin|dominican|infobox|logo|icon|flag|ribbon|symbol|seal_of|coat_of|signature|blank|edit-|wikidata|question_book|commons-|stub|\.svg|medal|emblem|map_of|locator", re.I)


def wiki_search(query, used, want_landscape=True):
    """Find one free picture through the pictures used on matching English Wikipedia articles (works where Commons is blocked)."""
    from urllib.parse import quote
    base = "https://en.wikipedia.org/w/api.php?format=json&action=query&"
    try:
        j = json.loads(_http_get(base + f"generator=search&gsrnamespace=0&gsrlimit=4&gsrsearch={quote(query)}&prop=images&imlimit=40").decode("utf-8", "ignore"))
    except Exception as e:
        print(f"      (Wikipedia search failed: {e})"); return None
    arts = [a for a in sorted((j.get("query", {}).get("pages", {})).values(), key=lambda p: p.get("index", 99)) if not _BAN.search(a.get("title", ""))]
    titles = []
    _stop = {"the", "and", "of", "in", "for", "from", "with", "old", "map"}
    qtok = {w for w in re.findall(r"[a-z]{3,}", query.lower()) if w not in _stop}
    cand = []
    for ai, a in enumerate(arts):
        atok = set(re.findall(r"[a-z]{3,}", a.get("title", "").lower()))
        for oi, im in enumerate(a.get("images", [])):
            t = im.get("title", "")
            if re.search(r"\.(jpe?g|png)$", t, re.I) and not _JUNK.search(t) and not _BAN.search(t) and t not in used and all(t != c[3] for c in cand):
                ft = set(re.findall(r"[a-z]{3,}", t.lower()))
                score = 2 * len(qtok & ft) + len(qtok & atok) * 0.5          # picture name that matches the search words wins
                cand.append((-score, ai, oi, t))
    cand.sort()
    titles = [c[3] for c in cand]
    best = None
    for i in range(0, min(len(titles), 40), 20):
        chunk = titles[i:i + 20]
        try:
            ij = json.loads(_http_get(base + "prop=imageinfo&iiprop=url|size|mime|extmetadata&iiurlwidth=2400&titles=" + quote("|".join(chunk))).decode("utf-8", "ignore"))
        except Exception: continue
        pages = sorted((ij.get("query", {}).get("pages", {})).values(), key=lambda p: chunk.index(p["title"]) if p.get("title") in chunk else 99)
        for p in pages:
            ii = (p.get("imageinfo") or [{}])[0]
            if ii.get("mime") not in ("image/jpeg", "image/png"): continue
            w, h = ii.get("width", 0), ii.get("height", 0)
            if w < 900 or h < 500: continue
            meta = ii.get("extmetadata", {}); lic = _clean(meta.get("LicenseShortName", {}).get("value"))
            if not lic or re.search(r"fair use|non-?commercial|\bNC\b|\bND\b", lic, re.I): continue
            item = dict(url=ii.get("thumburl") or ii.get("url"), title=p.get("title", ""), license=lic,
                        author=_clean(meta.get("Artist", {}).get("value"))[:90], page=ii.get("descriptionurl", ""))
            if w / max(h, 1) >= 1.25 or not want_landscape: return item
            best = best or item
    return best


def commons_search(query, used, want_landscape=True, limit=12):
    """Find one free picture on Wikimedia Commons. Returns dict(url, title, author, license, page) or None."""
    from urllib.parse import quote
    hit = wiki_search(query, used, want_landscape)
    if hit or _COMMONS_DEAD[0]: return hit
    api = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrnamespace=6"
           f"&gsrlimit={limit}&gsrsearch={quote(query + ' filetype:bitmap')}"
           "&prop=imageinfo&iiprop=url|size|mime|extmetadata&iiurlwidth=2400")
    data = None
    for attempt in range(3):
        try: data = json.loads(_http_get(api).decode("utf-8", "ignore")); break
        except Exception as e:
            err = e; import time; time.sleep(1.5 * (attempt + 1))
    if data is None:
        _COMMONS_DEAD[0] = True
        print(f"      (Commons is blocked here - using Wikipedia pictures only)"); return None
    pages = sorted((data.get("query", {}).get("pages", {})).values(), key=lambda p: p.get("index", 99))
    best = None
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        if ii.get("mime") not in ("image/jpeg", "image/png"): continue
        w, h = ii.get("width", 0), ii.get("height", 0)
        if w < 1100 or h < 600 or p.get("title") in used or _BAN.search(p.get("title", "")) or _JUNK.search(p.get("title", "")): continue
        meta = ii.get("extmetadata", {}); lic = _clean(meta.get("LicenseShortName", {}).get("value"))
        if not lic or re.search(r"fair use|non-?commercial|\bNC\b|\bND\b", lic, re.I): continue
        landscape = w / max(h, 1) >= 1.25
        item = dict(url=ii.get("thumburl") or ii.get("url"), title=p.get("title", ""), license=lic,
                    author=_clean(meta.get("Artist", {}).get("value"))[:90], page=ii.get("descriptionurl", ""))
        if landscape or not want_landscape: return item
        best = best or item
    return best


def net_check(log=print):
    """Is the internet (and Wikimedia) reachable from this computer? Returns True/False and says why."""
    import socket
    bad = []
    for host in ("commons.wikimedia.org", "upload.wikimedia.org"):
        try: socket.getaddrinfo(host, 443)
        except OSError as e: bad.append((host, e))
    if not bad: return True
    if all(_doh(h) for h, _ in bad):
        log("  (This computer's DNS cannot find Wikimedia - using backup DNS 8.8.8.8 instead. Pictures will still download.)")
        return True
    try: socket.getaddrinfo("www.google.com", 443); web = True
    except OSError: web = False
    log("")
    log("  !! PICTURES: this computer cannot reach " + ", ".join(h for h, _ in bad) + " (" + str(bad[0][1]) + ")")
    log("  !! " + ("Other websites work, so Wikimedia is being blocked by your DNS/ISP." if web else "No internet connection right now."))
    log("  !! Fix: connect to the internet (or turn the VPN on), or change Windows DNS to 8.8.8.8 and 1.1.1.1,")
    log("  !!      then double-click RENDER.bat again. Nothing is lost - voices and music are kept.")
    return False


def fetch_pictures(ep, scenes):
    """Download every missing shot picture (search words -> Commons). Writes images\\ep\\credits.txt and SHOTLIST.txt."""
    folder = IMGS / ep; folder.mkdir(parents=True, exist_ok=True)
    used_file = folder / "commons_used.json"
    used = set(json.loads(used_file.read_text(encoding="utf-8"))) if used_file.exists() else set()
    credits_file = folder / "credits.txt"
    credits = credits_file.read_text(encoding="utf-8").splitlines() if credits_file.exists() else []
    shotlist, got, miss = [], 0, 0
    need = any(not (find_pic(ep, sh["stem"]) or find_vid(ep, sh["stem"])) and sh.get("search") and not sh.get("card")
               for si, sc in enumerate(scenes, 1) for sh in norm_shots(si, sc))
    if need and not net_check():
        if os.environ.get("TK_NO_PICS") != "1":
            raise RuntimeError("No access to Wikimedia pictures. Fix the internet/DNS (see above) and run RENDER.bat again. "
                               "(To render with title cards only, set TK_NO_PICS=1.)")
    for si, sc in enumerate(scenes, 1):
        for sh in norm_shots(si, sc):
            stem = sh["stem"]; have = find_pic(ep, stem) or find_vid(ep, stem)
            note = "picture/video in folder" if have else ""
            if not have and sh.get("search") and not sh.get("card"):
                print(f"  picture {stem}: searching Commons for '{sh['search']}' ...", end=" ", flush=True)
                hit = commons_search(sh["search"], used)
                if hit:
                    try:
                        raw = _http_get(hit["url"], 120)
                        tmp = folder / f"{stem}.part"; tmp.write_bytes(raw)
                        Image.open(tmp).convert("RGB").save(folder / f"{stem}.jpg", quality=92); tmp.unlink()
                        used.add(hit["title"]); got += 1; have = True
                        note = f"Commons: {hit['title']} | {hit['author']} | {hit['license']} | {hit['page']}"
                        credits.append(f"{stem} | {note}"); print("ok")
                    except Exception as e:
                        print(f"download failed ({e})"); note = "download failed"
                else:
                    print("nothing found"); note = "nothing found - title card used"
                if not have: miss += 1
            elif not have:
                note = "title card" if sh.get("card") else "no search words - title card used"
            shotlist.append(f"{stem:6s} | {sh.get('search') or sh.get('card') or ''} | {note}")
    used_file.write_text(json.dumps(sorted(used)), encoding="utf-8")
    credits_file.write_text("\n".join(credits), encoding="utf-8")
    (folder / f"SHOTLIST_{ep}.txt").write_text(
        "Every shot of the video. To use your own picture, save it here as <name>.jpg (the first column) and render again.\n\n" + "\n".join(shotlist), encoding="utf-8")
    return got, miss


# ----------------------------------------------------------------------------- voice
VOICE_CHAIN = ("adeclip,highpass=f=80,"
               "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.12:detection=peak,"
               "areverse,silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.18:detection=peak,areverse,"
               "afftdn=nr=14:nf=-48,"
               "equalizer=f=110:t=q:w=1.0:g=3,equalizer=f=330:t=q:w=1.2:g=-2.5,"
               "equalizer=f=3200:t=q:w=1.0:g=3.5,equalizer=f=8000:t=q:w=0.9:g=1.5,"
               "acompressor=threshold=0.09:ratio=3.2:attack=6:release=110:makeup=3,"
               "alimiter=limit=0.9")


def read_audio(path, filters=None, channels=1):
    args = ["-i", path]
    if filters: args += ["-af", filters]
    args += ["-ac", channels, "-ar", SR, "-f", "f32le", "pipe:1"]
    r = run(args, capture=True)
    a = np.frombuffer(r.stdout, dtype="<f4").astype(np.float32)
    return a.reshape(-1, channels) if channels > 1 else a


async def _tts(text, voice, out):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate="-4%").save(str(out))


PRE_CHAIN = "adeclip,highpass=f=80,lowpass=f=15000"
POST_CHAIN = VOICE_CHAIN.split("afftdn=nr=14:nf=-48,", 1)[1]            # EQ, compressor, limiter (no old denoiser)
NOISE_CUT = float(os.environ.get("TK_DENOISE", "1.0"))                  # 0 = off, 1 = normal, 1.5 = stronger


def denoise(a, strength=None):
    """Spectral noise removal: learns the room noise from the quietest parts of the take, then removes it
    from the whole take; the pauses between words are pushed down much further than the speech."""
    strength = NOISE_CUT if strength is None else strength
    if strength <= 0 or len(a) < SR or not _SCIPY_OK: return a
    from scipy.signal import stft, istft
    nper, hop = 2048, 512
    f, t, Z = stft(a, SR, nperseg=nper, noverlap=nper - hop, boundary="zeros")
    mag = np.abs(Z)
    en = mag.sum(axis=0)
    quiet = en <= np.percentile(en, 15)
    noise = np.median(mag[:, quiet], axis=1, keepdims=True) * 1.25 + 1e-9
    snr = mag / noise
    gain = np.clip(1 - (1.6 * strength) / np.maximum(snr, 1e-3), 10 ** (-24 / 20), 1.0)
    gain = np.apply_along_axis(lambda x: np.convolve(x, np.ones(3) / 3, "same"), 0, gain)     # smooth over frequency
    sm = gain.copy()
    for k in range(1, sm.shape[1]):                                                           # fast attack, slower release
        sm[:, k] = np.maximum(gain[:, k], sm[:, k - 1] * 0.82)
    for k in range(sm.shape[1] - 2, -1, -1):
        sm[:, k] = np.maximum(sm[:, k], sm[:, k + 1] * 0.6)
    # extra expander in the gaps: frames whose total energy is near the noise floor are lowered further
    gate = np.clip((en / (np.median(en[quiet]) + 1e-9) - 1.5) / 4.0, 0.12, 1.0)
    gate = np.convolve(gate, np.ones(5) / 5, "same")
    out = istft(Z * sm * gate[None, :] ** strength, SR, nperseg=nper, noverlap=nper - hop)[1][: len(a)]
    return out.astype(np.float32)


PAUSE_MAX = float(os.environ.get("TK_PAUSE_MAX", "1.1"))              # seconds; longer pauses inside a take are shortened to 0.8 s


def trim_pauses(a, maxp=None):
    maxp = PAUSE_MAX if maxp is None else maxp
    hop = 480; v = voiced_mask(a, hop); n = len(v)
    idx = np.flatnonzero(v)
    if idx.size == 0: return a
    keep = np.ones(len(a), bool); j = idx[0]; end = idx[-1]
    while j < end:
        if not v[j]:
            k = j
            while k < end and not v[k]: k += 1
            if (k - j) * hop / SR > maxp:
                cut0 = j * hop + int(0.40 * SR); cut1 = k * hop - int(0.40 * SR)
                if cut1 > cut0: keep[cut0:cut1] = False
            j = k
        else: j += 1
    if keep.all(): return a
    return a[keep]


def clean_voice(src, work):
    a = read_audio(src, PRE_CHAIN)
    a = denoise(a)
    tmp = Path(work) / "_dn.wav"; write_wav(tmp, a)
    b = read_audio(tmp, "silenceremove=start_periods=1:start_threshold=-55dB:start_silence=0.12:detection=peak,"
                        "areverse,silenceremove=start_periods=1:start_threshold=-55dB:start_silence=0.18:detection=peak,areverse," + POST_CHAIN)
    return trim_pauses(b)


def scene_voice(ep, i, sc, work, rec_dir):
    """Cleaned, levelled voice of one scene as float32 mono at 48 kHz."""
    mine = rec_dir / f"{i:02d}.wav"
    if mine.exists(): src, who = mine, "your voice"
    elif TEST:
        n = int(max(3, len((sc.get("narration_roman") or "x").split()) / 2.4) * SR)
        return np.zeros(n, np.float32), "test-silence"
    else:
        src = work / f"{i:02d}_ai.mp3"; who = "AI voice"
        if not src.exists():
            text = sc.get("narration_ur") or sc.get("narration_hi") or ""
            for attempt in range(3):
                try: asyncio.run(_tts(text, AI_VOICE, src)); break
                except Exception as e:
                    if attempt == 2: raise RuntimeError(f"AI voice failed (internet?): {e}")
    a = clean_voice(src, work)
    if a.size < SR // 2: raise RuntimeError(f"scene {i}: recording is empty or too quiet ({src})")
    voiced = a[np.abs(a) > 0.01]
    rms = np.sqrt(np.mean(voiced ** 2)) + 1e-9 if voiced.size else 0.05
    a = a * (10 ** (-19 / 20) / rms)                                   # same loudness in every scene
    a = np.tanh(a * 0.85) / 0.85 if np.max(np.abs(a)) > 0.95 else a   # soft limit
    return a.astype(np.float32), who


def voiced_mask(a, hop=480):
    """10 ms frames that contain speech (short gaps inside words are bridged)."""
    n = len(a) // hop
    env = np.sqrt(np.mean(a[:n * hop].reshape(n, hop) ** 2, axis=1))
    v = env > 10 ** (-46 / 20)
    k = 18                                                              # bridge gaps up to 180 ms
    out = v.copy(); gap = 0
    for j in range(n):
        if v[j]:
            if 0 < gap <= k: out[j - gap:j] = True
            gap = 0
        else: gap += 1
    return out


# ----------------------------------------------------------------------------- subtitles
def split_sentences(text):
    return [s.strip() for s in re.findall(r"[^\u06d4\u061f!?]+[\u06d4\u061f!?]?", text or "") if s.strip(" \u06d4")]


def chunk_words(sent, maxw=9):
    """Cut a long sentence into subtitle pieces at commas first, then into equal word groups."""
    parts = [x.strip() for x in re.split(r"(?<=[\u060c:\u061b,])\s+", sent) if x.strip()]
    merged = []
    for x in parts:
        if merged and (len(x.split()) < 3 or len(merged[-1].split()) < 3) and len(merged[-1].split()) + len(x.split()) <= maxw:
            merged[-1] += " " + x
        else: merged.append(x)
    out = []
    for x in merged:
        ws = x.split()
        if len(ws) <= maxw: out.append(x); continue
        n = math.ceil(len(ws) / maxw); size = math.ceil(len(ws) / n)
        out += [" ".join(ws[k:k + size]) for k in range(0, len(ws), size)]
    return out or [sent]


def chunk_chars(sent, limit=84):
    out, cur = [], ""
    for w in sent.split():
        if cur and len(cur) + 1 + len(w) > limit: out.append(cur); cur = w
        else: cur = (cur + " " + w).strip()
    if cur: out.append(cur)
    return out


def make_cues(sc, mask, hop=0.01):
    """Returns [(start, end, ur, en)] timed on the real speech (pauses are skipped)."""
    ur_s = split_sentences(sc.get("narration_ur", ""))
    en_s = sc.get("subtitle_en") or []
    if isinstance(en_s, str): en_s = [en_s]
    times = np.arange(len(mask) + 1) * hop
    cum = np.concatenate([[0], np.cumsum(mask) * hop]); total = cum[-1]
    if total <= 0 or not ur_s: return [], []
    chunks = []                                                         # (sentence index, text)
    for j, s in enumerate(ur_s):
        for c in chunk_words(s): chunks.append((j, c))
    w = np.array([max(len(c.replace(" ", "")), 1) for _, c in chunks], float); w = np.cumsum(w) / w.sum() * total
    starts = np.concatenate([[0], w[:-1]])
    def t_start(v): return times[min(np.searchsorted(cum, v, "right"), len(times) - 1)]
    def t_end(v): return times[min(np.searchsorted(cum, v, "left"), len(times) - 1)]
    cues = [[t_start(s), t_end(e), c, j] for s, e, (j, c) in zip(starts, w, chunks)]
    out = []
    if en_s and len(en_s) == len(ur_s):                                  # English follows the Urdu sentence it translates
        for j, e in enumerate(en_s):
            mine = [c for c in cues if c[3] == j]
            if not mine: continue
            a, b = mine[0][0], mine[-1][1]; parts = chunk_chars(e); tot = sum(len(p) for p in parts); t = a
            for p in parts:
                d = (b - a) * len(p) / tot; out.append((t, t + d, "", p)); t += d
    elif en_s:
        a0, b0 = cues[0][0], cues[-1][1]; tot = sum(len(s) for s in en_s); t = a0
        for e in en_s:
            for p in chunk_chars(e):
                d = (b0 - a0) * len(p) / tot; out.append((t, t + d, "", p)); t += d
    return [(c[0], c[1], c[2], "") for c in cues], out


def srt_time(t):
    ms = int(round(max(t, 0) * 1000)); return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(path, cues):
    path.write_text("".join(f"{k}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n\n" for k, (a, b, t) in enumerate(cues, 1)), encoding="utf-8")


# ----------------------------------------------------------------------------- music
def load_music(name, channels=2):
    for ext in (".wav", ".mp3", ".m4a"):
        p = MUSIC / f"{name}{ext}"
        if p.exists(): return read_audio(p, None, channels)
    return None


def smooth(x, n):
    if n <= 1: return x
    k = np.ones(n) / n; pad = np.pad(x, (n // 2, n - n // 2 - 1), mode="edge")
    return np.convolve(pad, k, mode="valid")


# ---------- emotional voice colour (warmth + saturation + mood room) ----------
VOICE_FX = float(os.environ.get("TK_VOICEFX", "1.0"))
REVERB = float(os.environ.get("TK_REVERB", "0.0"))             # echo / room: 0 = none (default), 0.3 = a little, 1 = strong          # 0 = off, 1 = normal, 1.5 = stronger
_FXP = {  # low-boost, presence dB, parallel-compression mix, reverb length(s), decay(s), wet
    "calm":  (0.10, 2.0, 0.10, 0.6, 0.25, 0.20),
    "tense": (0.18, 2.5, 0.15, 0.9, 0.40, 0.30),
    "epic":  (0.20, 2.5, 0.15, 1.2, 0.55, 0.40),
}


def _ir(n, tau, seed):
    from scipy.signal import butter, sosfilt
    rng = np.random.default_rng(seed)
    t = np.arange(n) / SR
    x = rng.standard_normal(n) * np.exp(-t / tau)
    x = sosfilt(butter(2, 3500 / (SR / 2), output="sos"), x)        # soft, dark tail (no sizzle over consonants)
    x[: int(0.04 * SR)] = 0                                         # 40 ms pre-delay keeps words clean
    return (x / (np.sqrt(np.sum(x ** 2)) + 1e-9)).astype(np.float32)


def _env(x, ms):
    from scipy.signal import butter, sosfilt
    return sosfilt(butter(1, (1000 / ms) / (SR / 2), output="sos"), np.abs(x))


def emotive(a, mood="calm", amount=None):
    """mono voice -> stereo voice: clearer, warmer, more intense; the room only blooms in the pauses."""
    amount = VOICE_FX if amount is None else amount
    if amount <= 0 or not _SCIPY_OK: return np.stack([a, a], 1)
    from scipy.signal import butter, sosfilt, fftconvolve
    low, pres, pc, rlen, tau, wet = _FXP.get(mood, _FXP["calm"])
    x = a.astype(np.float64)
    x = x + low * amount * sosfilt(butter(2, 200 / (SR / 2), output="sos"), x)          # chest / warmth
    mud = sosfilt(butter(2, [250 / (SR / 2), 450 / (SR / 2)], btype="band", output="sos"), x)
    x = x - 0.35 * mud                                                                  # remove boxiness
    air = sosfilt(butter(2, 6500 / (SR / 2), btype="high", output="sos"), x)
    x = x + 0.08 * amount * air                                                         # air / crispness
    pk = sosfilt(butter(2, [2200 / (SR / 2), 4200 / (SR / 2)], btype="band", output="sos"), x)
    x = x + (10 ** (pres * amount / 20) - 1) * pk                                       # consonant clarity
    e = _env(x, 60) + 0.01                                                              # parallel compression = intensity
    loud = x * np.clip((0.12 / e) ** 0.7, 0.4, 2.5)
    x = x * (1 - pc * amount) + loud * pc * amount * 0.6
    x = x / max(1.0, np.max(np.abs(x)) / 0.95)
    n = int(rlen * SR)
    out = np.zeros((len(x) + n, 2))
    send = sosfilt(butter(2, 350 / (SR / 2), btype="high", output="sos"), x)
    gate = 1 - 0.92 * np.clip(_env(x, 140) / 0.05, 0, 1)                                # reverb ducked while speaking
    gate = np.concatenate([gate, np.full(n, gate[-1] if len(gate) else 1)])
    for ch in (0, 1):
        out[: len(x), ch] += x
        if REVERB <= 0: continue
        r = fftconvolve(send, _ir(n, tau, 11 + ch))[: len(out)]
        r = r * np.interp(np.arange(len(r)), np.arange(len(gate)), gate) * wet * amount * 4.0 * REVERB
        out[: len(r), ch] += r
    return out.astype(np.float32)


def build_master(timeline, total_samples, voices, hits, risers):
    """timeline: list of (start_sample, end_sample, mood). Returns stereo float32 (n, 2)."""
    voice = np.zeros(total_samples, np.float32)
    voice2 = np.zeros((total_samples, 2), np.float32)
    for off, a in voices:
        m = next((mm for s_, e_, mm in timeline if s_ <= off + 1 < e_ + 1), "calm")
        st = emotive(a, m)[: max(0, total_samples - off)]
        voice2[off:off + len(st)] += st
        voice[off:off + len(a)] += a[:max(0, total_samples - off)]
    # music beds, one tiled track per mood, faded in/out with 1.5 s smoothing
    music = np.zeros((total_samples, 2), np.float32)
    grid = 100                                                          # envelope resolution (Hz)
    moods = sorted({m for _, _, m in timeline})
    for m in moods:
        bed = load_music("bed_" + m)
        if bed is None: bed = load_music("bed_calm")
        if bed is None: continue
        reps = int(math.ceil(total_samples / len(bed))) + 1
        tile = np.tile(bed, (reps, 1))[:total_samples]
        env = np.zeros(total_samples // (SR // grid) + 2)
        for s, e, mm in timeline:
            if mm == m: env[s // (SR // grid):e // (SR // grid)] = 1
        env = smooth(env, int(1.6 * grid))
        music += tile * np.interp(np.arange(total_samples), np.arange(len(env)) * (SR // grid), env)[:, None].astype(np.float32)
    # duck the music while the voice speaks
    hop = SR // 50
    n = total_samples // hop + 1
    vp = np.pad(np.abs(voice), (0, n * hop - total_samples)).reshape(n, hop).max(axis=1)
    speaking = (vp > 10 ** (-42 / 20)).astype(float)
    env_d = np.ones(n); g = 1.0
    for k in range(n):                                                  # attack 80 ms, release 600 ms
        target = 0.45 if speaking[k] else 1.0
        coef = 1 - math.exp(-0.02 / (0.08 if target < g else 0.9)); g += (target - g) * coef; env_d[k] = g
    duck = np.interp(np.arange(total_samples), np.arange(n) * hop, env_d).astype(np.float32)
    music *= duck[:, None]
    mix = music * 0.8 * MUSIC_GAIN
    mix += voice2
    for off, a in hits + risers:
        end = min(off + len(a), total_samples)
        if off < total_samples: mix[off:end] += a[:end - off] * 0.9
    peak = np.max(np.abs(mix)) + 1e-9
    return (mix / peak * 0.95).astype(np.float32) if peak > 0.95 else mix


def write_wav(path, a):
    pcm = (np.clip(a, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1 if a.ndim == 1 else a.shape[1]); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


# ----------------------------------------------------------------------------- thumbnail
def thumb_card(data, ep, out):
    """1280x720 thumbnail: dark picture, big Urdu title + English title with outline. Uses data['thumb_ur'], data['thumb_text']."""
    TW, TH = 1280, 720
    base = None; fallback = None
    for pat in ("01[a-f].*", "02[a-f].*", "03[a-f].*", "04[a-f].*"):         # first sharp, wide picture of the opening scenes
        for p in sorted((IMGS / ep).glob(pat)):
            if p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"): continue
            try: im = Image.open(p).convert("RGB")
            except Exception: continue
            fallback = fallback or im
            if im.width >= 1600 and 1.3 <= im.width / im.height <= 2.1: base = im; break
        if base: break
    base = base or fallback
    if base is None:
        tmp = IMGS / ep / "_thumb_bg.jpg"; card_bg(tmp, seed=11); base = Image.open(tmp).convert("RGB").resize((TW, TH))
    r = max(TW / base.width, TH / base.height)
    base = base.resize((int(base.width * r) + 1, int(base.height * r) + 1)); l, t = (base.width - TW) // 2, (base.height - TH) // 2
    base = base.crop((l, t, l + TW, t + TH))
    base = Image.blend(base, Image.new("RGB", base.size, (0, 0, 0)), 0.55).convert("RGBA")
    ov = Image.new("RGBA", (TW, TH), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    d.rectangle([0, 0, 18, TH], fill=(225, 170, 60, 255))
    ur, en = data.get("thumb_ur", ""), (data.get("thumb_text") or "").upper()
    if ur:
        usz = 210
        while usz > 90 and tlen(d, ur, urdu(usz), True) > TW - 150: usz -= 10      # long Urdu titles shrink to fit
        draw_c(d, ur, urdu(usz), TW / 2, 110 + (210 - usz) // 3, (255, 255, 255, 255), True, stroke=6)
    if en:
        f = latin(92); lines = wrap(d, en, f, TW - 160)[:2]; y = 430 if ur else 250
        for ln in lines:
            draw_c(d, ln, f, TW / 2, y, (255, 214, 80, 255), False, stroke=7); y += 110
    sub = data.get("thumb_sub", "")
    if sub: draw_c(d, sub, latin(44), TW / 2, TH - 90, (255, 255, 255, 235), False, stroke=3)
    Image.alpha_composite(base, ov).convert("RGB").save(out, quality=94)


# ----------------------------------------------------------------------------- the episode
def chapter_of(sc):
    c = sc.get("chapter")
    if not c: return None
    if isinstance(c, str): c = {"en": c}
    return c


def render_episode(ep, data, work, out_video, out_dir, rec_dir=None, only=None, log=print):
    """Builds the finished video. only=[scene numbers] makes a short sample. Returns a small report dict."""
    from music_synth import ensure_music
    rec_dir = rec_dir or (RECS / ep)
    work.mkdir(parents=True, exist_ok=True)
    scenes = data["scenes"]
    idx = list(range(1, len(scenes) + 1)) if not only else list(only)
    ensure_music(MUSIC)
    if os.environ.get("TK_WATERMARK", "1") != "0":
        try: WM_PNG[0] = make_watermark(work / "watermark.png")
        except Exception as e: print(f"  (watermark skipped: {e})"); WM_PNG[0] = None

    # 1. pictures
    got, miss = fetch_pictures(ep, scenes)

    # 2. voices and durations
    log("  cleaning your voice ...")
    voices_raw = {}
    for i in idx:
        voices_raw[i] = scene_voice(ep, i, scenes[i - 1], work, rec_dir)

    # 3. build every scene
    segs, timeline, voice_items, hit_items, riser_items = [], [], [], [], []
    cues_ur_all, cues_en_all = [], []
    marks = [(0.0, "Intro")]
    hit = load_music("hit"); riser = load_music("riser")
    FILL_ON = os.environ.get("TK_FILLS", "1") != "0"
    fills = {k: load_music(k) for k in ("fill_a", "fill_b", "fill_c", "fill_tense", "fill_epic", "stinger")}
    fill_n = 0
    mood = "calm"; shot_no = 0
    tot_frames = 0
    for n, i in enumerate(idx, 1):
        sc = scenes[i - 1]; a, who = voices_raw[i]
        ch = chapter_of(sc); card_fr = int(round(CARD * FPS)) if ch else 0
        body_fr = int(math.ceil((len(a) / SR + GAP) * FPS))
        mood = sc.get("mood", mood)
        log(f"  scene {n}/{len(idx)} ({who}, {len(a) / SR:.0f}s{', chapter' if ch else ''}) ...")
        sdir = work / f"s{i:02d}"; sdir.mkdir(exist_ok=True)
        # card
        if ch:
            cbg = sdir / "card_bg.jpg"; card_bg(cbg, seed=i); c2 = sdir / "card2x.jpg"
            Image.open(cbg).resize((W * 2, H * 2), Image.LANCZOS).save(c2, quality=92)
            cbase = sdir / "card_base.mp4"; shot_clip(c2, card_fr, 0, cbase)
            num = ch.get("n"); lab = f"CHAPTER {num}" if num else "CHAPTER"
            pa = sdir / "card_a.png"; pb = sdir / "card_b.png"
            card_text(pa, [(lab, 54, (225, 170, 60, 255), False)], H // 2)
            lines = [(lab, 46, (225, 170, 60, 255), False)]
            if ch.get("ur"): lines.append((ch["ur"], 110, (255, 255, 255, 255), True))
            if ch.get("en"): lines.append((ch["en"], 62, (255, 232, 170, 255), False))
            card_text(pb, lines, H // 2)
            card = sdir / "card.mp4"
            compose([cbase], [card_fr], [(str(pa), 0.2, 1.4, True), (str(pb), 1.4, CARD, True)], card)
        # shots
        shots = norm_shots(i, sc); ns = max(1, int(round(body_fr / FPS / 6.5)))
        if len(shots) < ns:                                             # not enough shots listed: repeat the last picture with another move
            while len(shots) < ns: shots.append(dict(shots[-1], stem=shots[-1]["stem"], w=1.0))
        ws = np.array([s.get("w", 1.0) for s in shots], float)
        vis = np.maximum(np.round(ws / ws.sum() * body_fr).astype(int), 2 * XF); vis[-1] += body_fr - vis.sum()
        clips = []
        for k, s in enumerate(shots):
            fr = int(vis[k] + (XF if k < len(shots) - 1 else 0)); shot_no += 1
            vid = find_vid(ep, s["stem"])
            if vid:
                clip = sdir / f"shot{k}.mp4"; video_clip(vid, fr, clip); clips.append(clip); continue
            pic = find_pic(ep, s["stem"]); c2 = sdir / f"shot{k}_2x.jpg"
            if pic: cover2x(pic, c2)
            else:
                bgp = sdir / f"shot{k}_bg.jpg"; card_bg(bgp, seed=shot_no, warm=(shot_no % 2 == 0))
                base = Image.open(bgp).convert("RGBA"); txt = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                tp = sdir / f"shot{k}_t.png"
                cd = s.get("card") if isinstance(s.get("card"), dict) else {}
                lines = []
                if cd.get("ur"): lines.append((cd["ur"], 120, (255, 255, 255, 255), True))
                if cd.get("en") or s.get("search"): lines.append((cd.get("en") or "", 64, (255, 214, 120, 255), False))
                if lines: card_text(tp, [l for l in lines if l[0]], H // 2); base = Image.alpha_composite(base, Image.open(tp))
                base.convert("RGB").resize((W * 2, H * 2), Image.LANCZOS).save(c2, quality=92)
            clip = sdir / f"shot{k}.mp4"; shot_clip(c2, fr, shot_no, clip); clips.append(clip)
        # subtitles + key panel
        mask = voiced_mask(a)
        cues_ur, cues_en = make_cues(sc, mask) if sc.get("narration_ur") else ([], [])
        ov = []
        key = sc.get("key") or {}
        if not key and sc.get("text_on_screen"):
            parts = [p.strip() for p in sc["text_on_screen"].split("|")]
            key = {"en": parts[0], "ur": parts[-1] if len(parts) > 1 and has_rtl(parts[-1]) else ""}
        if key.get("en") or key.get("ur"):
            kp = sdir / "key.png"; key_png(key.get("en", ""), key.get("ur", ""), kp); ov.append((str(kp), 0.5, 5.0, True))
        show_en = "en" in BURN
        en_at = lambda t: next((e for (a1, b1, _, e) in cues_en if a1 - 0.01 <= t < b1), "")
        if "ur" in BURN or show_en:
            for k, (a1, b1, u, _) in enumerate(cues_ur):
                sp = sdir / f"sub{k}.png"; sub_png(u if "ur" in BURN else "", en_at((a1 + b1) / 2) if show_en else "", sp, show_en)
                ov.append((str(sp), a1, max(b1, a1 + 0.5), False))
        body = sdir / "body.mp4"; compose(clips, [int(v) for v in vis], ov, body, ep_seed=i)
        # bookkeeping
        start_s = (tot_frames) / FPS
        if ch: marks.append((start_s, ch.get("en") or ch.get("ur") or f"Chapter {ch.get('n', '')}"))
        if card_fr: segs.append(sdir / "card.mp4")
        segs.append(body)
        voice_start = start_s + card_fr / FPS
        voice_items.append((int(round(voice_start * SR)), a))
        if ch and riser is not None and hit is not None:
            r_off = int(round((start_s + 1.4) * SR)) - len(riser)
            riser_items.append((max(r_off, 0), riser)); hit_items.append((int(round((start_s + 1.4) * SR)), hit))
        elif sc.get("sfx") == "hit" and hit is not None:
            hit_items.append((int(round(voice_start * SR)), hit * 0.8))
        if FILL_ON:
            if not ch and (key.get("en") or key.get("ur")) and fills.get("stinger") is not None:      # date / name panel
                hit_items.append((int(round((voice_start + 0.4) * SR)), fills["stinger"] * 0.55))
            nxt = scenes[idx[n] - 1] if n < len(idx) else None
            if nxt is not None and not chapter_of(nxt):                                                  # guitar in the pause
                fk = {"tense": "fill_tense", "epic": "fill_epic"}.get(mood) or ("fill_a", "fill_b", "fill_c")[fill_n % 3]
                fill_n += 1
                if fills.get(fk) is not None:
                    hit_items.append((int(round((voice_start + len(a) / SR - 0.15) * SR)), fills[fk] * 0.5))
        tot_frames += card_fr + body_fr
        timeline.append((int(round(start_s * SR)), int(round(tot_frames / FPS * SR)), mood))
        for (a1, b1, u, _) in cues_ur: cues_ur_all.append((voice_start + a1, voice_start + b1, u))
        for (a1, b1, _, e) in cues_en: cues_en_all.append((voice_start + a1, voice_start + b1, e))

    # 4. join video, mix sound, final file
    log("  joining scenes ...")
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in segs), encoding="utf-8")
    joined = work / "joined.mp4"
    run(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])
    total_samples = int(round(tot_frames / FPS * SR))
    log("  mixing voice + music + drums ...")
    master = build_master(timeline, total_samples, voice_items, hit_items, riser_items)
    mw = work / "master.wav"; write_wav(mw, master)
    out_video.parent.mkdir(parents=True, exist_ok=True)
    run(["-i", joined, "-i", mw, "-map", "0:v", "-map", "1:a", "-af", "loudnorm=I=-15:TP=-1.5:LRA=9",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest", out_video])
    stem = out_video.stem
    if cues_ur_all: write_srt(out_dir / f"{ep}_subtitles_Urdu.srt", cues_ur_all)
    if cues_en_all: write_srt(out_dir / f"{ep}_subtitles_English.srt", cues_en_all)
    def mmss(t): t = int(t); return f"{t // 60}:{t % 60:02d}"
    (out_dir / f"{ep}_chapters.txt").write_text("\n".join(f"{mmss(t)} {name}" for t, name in marks) + "\n", encoding="utf-8")
    cr = IMGS / ep / "credits.txt"
    if cr.exists() and cr.read_text(encoding="utf-8").strip():
        (out_dir / f"{ep}_picture_credits.txt").write_text(
            "Picture credits (Wikimedia Commons) - paste into the video description:\n\n" + cr.read_text(encoding="utf-8"), encoding="utf-8")
    return {"seconds": tot_frames / FPS, "downloaded": got, "missing_pictures": miss}


if __name__ == "__main__":
    print("v2.py is used by RENDER.bat. To test the picture search:  python factory\\v2.py search \"Pashtun jirga\"")
    if len(sys.argv) > 2 and sys.argv[1] == "search":
        print(commons_search(" ".join(sys.argv[2:]), set()))
