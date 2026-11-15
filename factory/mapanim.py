"""Animated map shot: places light up one by one and a golden line travels from the first place to the others.

In an episode:  {"map": {"places": [["Badakhshan", 36.7, 70.8], ["Egypt", 26.8, 30.8]], "title": "The blue road"}, "at": 3}
  places : [name, latitude, longitude]   (the first one is where the line starts)
  routes : optional [[0, 1], [1, 2]] = which place goes to which (default: from the first place to every other)
  title  : optional small heading
Only land, sea, lakes and big rivers are drawn - no modern borders (they did not exist then, and nobody can argue about them).
Map shapes: Natural Earth (public domain), factory/world_map.json.
"""
import json, math, shutil
from pathlib import Path
from PIL import Image, ImageDraw

_W = [None]
SEA, LAND, EDGE, RIVER = (16, 26, 42), (70, 76, 64), (118, 122, 98), (52, 86, 120)
GOLD, WHITE = (245, 196, 86), (255, 255, 255)
BORDER = (168, 170, 150)


def _world():
    if _W[0] is None:
        _W[0] = json.loads((Path(__file__).resolve().parent / "world_map.json").read_text(encoding="utf-8"))
    return _W[0]


def _view(places, W, H):
    lats = [p[1] for p in places]; lons = [p[2] for p in places]
    lat0 = (min(lats) + max(lats)) / 2; lon0 = (min(lons) + max(lons)) / 2
    k = math.cos(math.radians(lat0))                       # shrink east-west so shapes look right at this latitude
    span_x = max((max(lons) - min(lons)) * k * 1.7, 16.0); span_y = max((max(lats) - min(lats)) * 1.9, 9.0)
    s = min(W / span_x, H / span_y)                        # pixels per degree
    def xy(lat, lon): return (W / 2 + (lon - lon0) * k * s, H / 2 - (lat - lat0) * s)
    box = (lon0 - W / 2 / s / k - 1, lon0 + W / 2 / s / k + 1, lat0 - H / 2 / s - 1, lat0 + H / 2 / s + 1)
    return xy, box


def _base(places, W, H, SS=2):
    xy, (x0, x1, y0, y1) = _view(places, W * SS, H * SS)
    im = Image.new("RGB", (W * SS, H * SS), SEA); d = ImageDraw.Draw(im)
    def seen(r):
        xs = [p[0] for p in r]; ys = [p[1] for p in r]
        return max(xs) >= x0 and min(xs) <= x1 and max(ys) >= y0 and min(ys) <= y1
    w = _world()
    for r in w["land"]:
        if seen(r): d.polygon([xy(la, lo) for lo, la in r], fill=LAND, outline=EDGE)
    for r in w["rivers"]:
        if seen(r): d.line([xy(la, lo) for lo, la in r], fill=RIVER, width=2 * SS)
    for r in w.get("borders", []):                          # today's country borders, thin and light (disputed lines are not drawn)
        if seen(r): d.line([xy(la, lo) for lo, la in r], fill=BORDER, width=2 * SS)
    for r in w["lakes"]:
        if seen(r): d.polygon([xy(la, lo) for lo, la in r], fill=SEA, outline=RIVER)
    im = im.resize((W, H), Image.LANCZOS)
    xy1, _ = _view(places, W, H)
    return im, xy1


def _arc(a, b, n=60):
    """Gently curved line from a to b."""
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2; dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1; bend = min(L * 0.18, 140)
    cx, cy = mx + dy / L * bend * (-1 if dx > 0 else 1), my - abs(dx) / L * bend
    return [((1 - t) ** 2 * a[0] + 2 * (1 - t) * t * cx + t * t * b[0], (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * cy + t * t * b[1])
            for t in (i / n for i in range(n + 1))]


def _ease(t): t = max(0.0, min(1.0, t)); return t * t * (3 - 2 * t)


def map_frames(spec, frames, folder, W=1920, H=1080, fps=30):
    import v2
    places = spec["places"]
    routes = spec.get("routes")
    if routes is None: routes = [[0, j] for j in range(1, len(places))]
    if routes in ("none", []): routes = []                  # "routes": "none" = only show the places, one after another, no lines
    base, xy = _base(places, W, H)
    pts = [xy(p[1], p[2]) for p in places]
    arcs = [_arc(pts[a], pts[b]) if i % 2 == 0 else [(x, 2 * (pts[a][1] + (pts[b][1] - pts[a][1]) * n / 60) - y) for n, (x, y) in enumerate(_arc(pts[a], pts[b]))]
            for i, (a, b) in enumerate(routes)]              # every second line bends the other way, so lines do not lie on each other
    f_lab, f_title, f_sub = v2.latin(46), v2.latin(40), v2.latin(32)
    T = frames / fps
    t_in = min(0.8, T * 0.12)                               # first place appears
    t_run = max(min(T - t_in - 1.2, 2.2 * max(len(arcs), 1) + 1.0), 0.6)   # all lines finish, then the map rests
    seg = t_run / max(len(arcs), 1)
    shown_at = {routes[0][0] if routes else 0: 0.0}
    for i, (a, b) in enumerate(routes):
        shown_at.setdefault(a, t_in + i * seg); shown_at.setdefault(b, t_in + (i + 1) * seg)
    if not routes: shown_at = {j: min(j * 0.8, max(T - 1.5, 0) * j / max(len(places) - 1, 1)) for j in range(len(places))}
    for j in range(len(places)): shown_at.setdefault(j, 0.0)
    # label places: try right, left, below-right, below-left, far above, far below - the first spot that covers no other label or dot
    meas = ImageDraw.Draw(Image.new("RGB", (8, 8))); boxes = []; lab_pos = {}
    for j, (x, y) in enumerate(pts):
        sub = str(places[j][3]) if len(places[j]) > 3 and places[j][3] else ""
        tw = max(meas.textlength(str(places[j][0]), font=f_lab), meas.textlength(sub, font=f_sub) if sub else 0); th = 92 if sub else 54
        cands = [(x + 24, y - 62), (x - 24 - tw, y - 62), (x + 24, y + 14), (x - 24 - tw, y + 14), (x - tw / 2, y - 62 - th), (x - tw / 2, y + 40)]
        def bad(c):
            bx = (c[0] - 6, c[1] - 6, c[0] + tw + 6, c[1] + th + 6)
            if bx[0] < 20 or bx[2] > W - 20 or bx[1] < 20 or bx[3] > H - 20: return True
            if any(bx[0] < b[2] and b[0] < bx[2] and bx[1] < b[3] and b[1] < bx[3] for b in boxes): return True
            return any(i != j and bx[0] < px < bx[2] and bx[1] < py < bx[3] for i, (px, py) in enumerate(pts))
        c = next((c for c in cands if not bad(c)), cands[0])
        lab_pos[j] = c; boxes.append((c[0], c[1], c[0] + tw, c[1] + th))
    folder.mkdir(parents=True, exist_ok=True)
    for f in range(frames):
        t = f / fps
        im = base.copy().convert("RGBA"); ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        for i, arc in enumerate(arcs):
            p = _ease((t - t_in - i * seg) / (seg * 0.92))
            if p <= 0: continue
            n = max(2, int(round(p * (len(arc) - 1))) + 1); part = arc[:n]
            d.line(part, fill=(0, 0, 0, 150), width=12, joint="curve")
            d.line(part, fill=GOLD + (255,), width=6, joint="curve")
            if p < 1:
                hx, hy = part[-1]; d.ellipse([hx - 11, hy - 11, hx + 11, hy + 11], fill=WHITE + (255,))
        for j, (x, y) in enumerate(pts):
            a = _ease((t - shown_at[j]) / 0.45)
            if a <= 0: continue
            pulse = 1 + 0.25 * math.sin((t - shown_at[j]) * 3.2)
            R = 26 * pulse; d.ellipse([x - R, y - R, x + R, y + R], outline=GOLD + (int(150 * a),), width=4)
            r = 11 * a; d.ellipse([x - r, y - r, x + r, y + r], fill=GOLD + (255,), outline=(0, 0, 0, 255), width=2)
            name = str(places[j][0])
            tw = max(d.textlength(name, font=f_lab), d.textlength(str(places[j][3]), font=f_sub) if len(places[j]) > 3 and places[j][3] else 0)
            lx, ly = lab_pos[j]
            d.text((lx, ly), name, font=f_lab, fill=WHITE + (int(255 * a),), stroke_width=4, stroke_fill=(0, 0, 0, int(230 * a)))
            if len(places[j]) > 3 and places[j][3]:                 # today's country, smaller, under the place name
                d.text((lx, ly + 54), str(places[j][3]), font=f_sub, fill=(255, 226, 150, int(255 * a)), stroke_width=3, stroke_fill=(0, 0, 0, int(230 * a)))
        if spec.get("title"):
            d.text((70, 56), str(spec["title"]), font=f_title, fill=GOLD + (255,), stroke_width=3, stroke_fill=(0, 0, 0, 230))
        Image.alpha_composite(im, ov).convert("RGB").save(folder / f"f{f:05d}.jpg", quality=90)


def map_clip(spec, frames, out, folder):
    import v2
    map_frames(spec, frames, folder, v2.W, v2.H, v2.FPS)
    v2.run(["-framerate", v2.FPS, "-i", folder / "f%05d.jpg", "-vf", f"{v2.GRADE},format=yuv420p", "-frames:v", frames,
            "-c:v", "libx264", "-preset", v2.PRESET, "-crf", v2.CRF, "-pix_fmt", "yuv420p", "-r", v2.FPS, out])
    shutil.rmtree(folder, ignore_errors=True)
