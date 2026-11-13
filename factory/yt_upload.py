"""Tareekh Ki Kahani - AUTO UPLOADER (no API, no credit cost).
UPLOAD.bat opens a separate Chrome (profile in factory\\yt_chrome, sign in to Google once) and this script drives
YouTube Studio exactly like a person: upload, title, description + chapters, tags, thumbnail, Urdu + English
subtitles, schedule. Videos already uploaded are remembered (uploaded.json inside each episode folder)."""
import os, json, re, sys, time, traceback, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
READY = ROOT / "Ready to Upload"
DEBUG = ROOT / "yt_debug"
CHANNEL_ID = "UCH8-mvkGTGLKKYIV4q1rX_Q"
if (ROOT / "factory" / "channel.txt").exists():
    CHANNEL_ID = (ROOT / "factory" / "channel.txt").read_text().strip() or CHANNEL_ID
UPLOAD_URL = f"https://studio.youtube.com/channel/{CHANNEL_ID}/videos/upload?d=ud"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def log(m): print("  " + m, flush=True)


# ----------------------------------------------------------------------------- read the episode's upload.txt
def parse_upload(ep_dir, ep):
    t = (ep_dir / "upload.txt").read_text(encoding="utf-8", errors="replace").replace("\r", "")
    def block(start, stops):
        i = t.find(start)
        if i < 0: return ""
        j = len(t)
        for s in stops:
            k = t.find(s, i + len(start))
            if k >= 0: j = min(j, k)
        return t[i + len(start):j].strip()
    title = block("TITLE (best, already used as the file name)", ["OTHER TITLE"]).splitlines()[0].strip()
    desc = block("DESCRIPTION", ["\nTAGS"])
    desc = re.sub(r"^[^\n]*\n-{5,}\n", "", desc, count=1).strip()          # drop "(paste...)" + dashed line
    tags = block("TAGS (15)", ["\nPINNED COMMENT", "\nSUBTITLES"]).strip()
    pinned = block("PINNED COMMENT", ["\nSUBTITLES", "\nFACT-CHECK"]).strip()
    chap = ep_dir / f"{ep}_chapters.txt"
    if chap.exists():
        ctext = chap.read_text(encoding="utf-8", errors="replace").replace("\r", "").strip()
        desc = re.sub(r"CHAPTERS\n\(paste[^\n]*\)", "CHAPTERS\n" + ctext, desc)
    desc = re.sub(r"\nPictures: Wikimedia Commons[^\n]*", "\nPictures: Wikipedia / Wikimedia Commons (credits in the pinned comment).", desc)
    desc = desc.replace("<", "").replace(">", "")
    if len(desc) > 4900: desc = desc[:4900].rsplit("\n", 1)[0]
    cred = ep_dir / f"{ep}_picture_credits.txt"
    credits = cred.read_text(encoding="utf-8", errors="replace").strip() if cred.exists() else ""
    return dict(title=title[:100], desc=desc, tags=[x.strip() for x in tags.split(",") if x.strip()][:15],
                pinned=pinned, credits=credits)


def parse_when(s):
    """'2026-11-14 07:45' -> datetime"""
    return dt.datetime.strptime(s.strip(), "%Y-%m-%d %H:%M")


# ----------------------------------------------------------------------------- Studio helpers
def shot(page, name):
    try:
        DEBUG.mkdir(exist_ok=True); page.screenshot(path=str(DEBUG / f"{name}.png"))
    except Exception: pass


def set_box(page, index, text):
    """Fill a Studio rich-text box (0 = title, 1 = description)."""
    page.evaluate("""([i, t]) => { const b = document.querySelectorAll('#textbox')[i]; b.focus();
        const s = window.getSelection(), r = document.createRange(); r.selectNodeContents(b); s.removeAllRanges(); s.addRange(r);
        document.execCommand('insertText', false, t); }""", [index, text])


def wait_dialog_ready(page, timeout=900):
    """Wait until the upload itself is finished (footer no longer says 'Uploading')."""
    t0 = time.time(); last = ""
    while time.time() - t0 < timeout:
        try:
            txt = page.locator("ytcp-uploads-dialog").inner_text(timeout=5000)
        except Exception:
            txt = ""
        m = re.search(r"Uploading (\d+)%", txt)
        if m and m.group(1) != last:
            last = m.group(1); print(f"\r  uploading {last}% ", end="", flush=True)
        if txt and "Uploading" not in txt and ("Upload complete" in txt or "Processing" in txt or "Checking" in txt or "Checks complete" in txt):
            print(); return
        time.sleep(3)
    raise RuntimeError("upload did not finish in time")


DATE_RE = re.compile(r"^[A-Z][a-z]{2} \d{1,2}, \d{4}$")
TIME_RE = re.compile(r"^\d{1,2}:\d{2} [AP]M$")


def pick_time(page, hhmm):
    label = dt.datetime.strptime(hhmm, "%H:%M").strftime("%I:%M %p").lstrip("0")
    page.get_by_text(TIME_RE).first.click(); time.sleep(0.6)
    opt = page.get_by_text(label, exact=True).last
    opt.scroll_into_view_if_needed(); opt.click(); time.sleep(0.4)


def pick_date(page, d):
    want = f"{MONTHS[d.month - 1]} {d.day}, {d.year}"
    cur = page.get_by_text(DATE_RE).first
    if cur.inner_text().strip() == want: return
    cur.click(); time.sleep(0.8)
    try:
        box = page.locator("ytcp-date-picker input, tp-yt-paper-dialog input, input[type=text]").last
        box.fill(want); box.press("Enter")
    except Exception as e:
        log(f"(date not set, YouTube default kept: {e})")
    time.sleep(0.6)


def get_video_id(page):
    txt = page.locator("ytcp-uploads-dialog").inner_text()
    m = re.search(r"youtu\.be/([\w-]{11})", txt) or re.search(r"shorts/([\w-]{11})", txt)
    if m: return m.group(1)
    for a in page.locator("ytcp-uploads-dialog a").all():
        h = a.get_attribute("href") or ""
        m = re.search(r"(?:youtu\.be/|shorts/|v=)([\w-]{11})", h)
        if m: return m.group(1)
    return None


def upload_one(page, f, meta, when, thumb=None, is_short=False):
    page.goto(UPLOAD_URL, wait_until="domcontentloaded"); time.sleep(4)
    page.locator("input[type=file]").first.set_input_files(str(f))
    page.wait_for_selector("#textbox", timeout=60000); time.sleep(3)
    set_box(page, 0, meta["title"]); time.sleep(0.5)
    set_box(page, 1, meta["desc"]); time.sleep(0.5)
    if thumb and thumb.exists():
        try:
            page.locator("#file-loader").first.set_input_files(str(thumb)); time.sleep(2)
        except Exception as e: log(f"(thumbnail skipped: {e})")
    try:                                                  # not made for kids
        page.locator('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]').click()
    except Exception: pass
    try:
        page.get_by_text("Show more", exact=True).first.click(); time.sleep(1)
        ai = os.environ.get("TK_AI_VOICE") == "1"          # default NO: real voice, real pictures, synthesised music
        page.locator('tp-yt-paper-radio-button[name="VIDEO_HAS_ALTERED_CONTENT_%s"]' % ("YES" if ai else "NO")).click()
    except Exception as e: log(f"(AI disclosure not set: {e})")
    try:                                                  # tags
        page.locator("#tags-container #clear-button").click(); time.sleep(0.4)
        page.locator("#tags-container input").click()
        page.keyboard.type(", ".join(meta["tags"]) + ",", delay=2); page.keyboard.press("Enter"); time.sleep(0.5)
    except Exception as e: log(f"(tags skipped: {e})")
    try:                                                  # video language Urdu
        page.locator("#audience, ytcp-form-language-input, #language-container").first.scroll_into_view_if_needed()
    except Exception: pass
    try:
        page.get_by_text("Video language", exact=True).first.scroll_into_view_if_needed()
        page.locator("ytcp-form-select:has-text('Video language') #trigger, ytcp-form-language-input #trigger, #language-container #trigger").first.click()
        time.sleep(0.6); page.get_by_text("Urdu", exact=True).last.click()
    except Exception as e: log(f"(language not set: {e})")
    vid = None
    try: vid = get_video_id(page)
    except Exception: pass
    wait_dialog_ready(page)
    for _ in range(3):                                    # Next x3 -> Visibility
        page.locator("#next-button").click(); time.sleep(1.5)
    page.get_by_text("Schedule", exact=True).first.click(); time.sleep(1)
    pick_date(page, when); pick_time(page, when.strftime("%H:%M"))
    time.sleep(0.5)
    try: page.locator("#done-button").click()
    except Exception: page.get_by_role("button", name="Schedule").last.click()
    time.sleep(4)
    for _ in range(3):                                    # 'We are still checking' notice
        b = page.get_by_role("button", name="Got it")
        if b.count():
            try: b.first.click(); time.sleep(2)
            except Exception: pass
    if not vid:
        try: vid = get_video_id(page)
        except Exception: pass
    time.sleep(3)
    try: page.get_by_role("button", name="Close").first.click(timeout=4000)
    except Exception: pass
    return vid


def upload_subs(page, vid, files):
    """files: dict {'ur': Path, 'en': Path}. Urdu = original language, English = (United States)."""
    page.goto(f"https://studio.youtube.com/video/{vid}/translations", wait_until="domcontentloaded"); time.sleep(5)
    if files.get("ur"):
        try:
            page.get_by_role("button", name="Upload manual").click(); time.sleep(1)
            with page.expect_file_chooser() as fc:
                page.get_by_role("button", name="Continue").click()
            fc.value.set_files(str(files["ur"])); time.sleep(5); log("Urdu subtitles uploaded")
        except Exception as e: log(f"(Urdu subtitles failed: {e})"); shot(page, f"{vid}_sub_ur")
    if files.get("en"):
        try:
            page.get_by_role("button", name="Add language").click(); time.sleep(1)
            page.get_by_text("English (United States)", exact=True).last.click(); time.sleep(3)
            page.get_by_text("Manual subtitles").locator("xpath=../..").get_by_role("button", name="Add").click(); time.sleep(5)
            page.get_by_text("Upload file", exact=True).click(); time.sleep(1)
            with page.expect_file_chooser() as fc:
                page.get_by_role("button", name="Continue").click()
            fc.value.set_files(str(files["en"])); time.sleep(5)
            page.get_by_role("button", name="Publish").last.click(); time.sleep(4); log("English subtitles uploaded")
        except Exception as e: log(f"(English subtitles failed: {e})"); shot(page, f"{vid}_sub_en")


# ----------------------------------------------------------------------------- main
def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("ep", help="episode id, e.g. tk004")
    ap.add_argument("--long-at", required=True, help='"YYYY-MM-DD HH:MM" (minutes 00/15/30/45)')
    ap.add_argument("--shorts-start", required=True, help='first Short, same format')
    ap.add_argument("--gap", type=int, default=60, help="minutes between Shorts")
    a = ap.parse_args()
    ep = a.ep.lower(); ep_dir = READY / ep
    if not ep_dir.exists(): sys.exit(f"Folder not found: {ep_dir}")
    meta = parse_upload(ep_dir, ep)
    done_f = ep_dir / "uploaded.json"
    done = json.loads(done_f.read_text()) if done_f.exists() else {}
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = br.contexts[0]; page = ctx.new_page(); page.set_default_timeout(30000)
        page.goto("https://studio.youtube.com", wait_until="domcontentloaded"); time.sleep(4)
        while "accounts.google" in page.url or "ServiceLogin" in page.url:
            input("  Sign in to Google in the Chrome window, then press ENTER here ...")
            page.goto("https://studio.youtube.com", wait_until="domcontentloaded"); time.sleep(4)
        # ---- long video
        longs = [x for x in ep_dir.glob("*.mp4")]
        if longs and "long" not in done:
            f = longs[0]; log(f"LONG: {f.name}")
            try:
                vid = upload_one(page, f, meta, parse_when(a.long_at), thumb=ep_dir / f"{ep}_thumbnail.jpg")
                if vid:
                    subs = {"ur": ep_dir / f"{ep}_subtitles_Urdu.srt", "en": ep_dir / f"{ep}_subtitles_English.srt"}
                    upload_subs(page, vid, {k: v for k, v in subs.items() if v.exists()})
                done["long"] = vid or "unknown"; done_f.write_text(json.dumps(done))
            except Exception:
                traceback.print_exc(); shot(page, f"{ep}_long_fail")
        # ---- shorts
        tag_line = "#Shorts #TareekhKiKahani"
        t0 = parse_when(a.shorts_start)
        for i, f in enumerate(sorted((ep_dir / "Shorts").glob("*.mp4"))):
            if f.name in done: continue
            title = f.stem
            sm = dict(meta); sm["title"] = title[:100]
            sm["desc"] = f"{re.sub(r'#Shorts', '', title).strip(' -')} - full video on the channel.\n\n{tag_line}"
            sm["tags"] = meta["tags"]
            log(f"SHORT: {f.name}")
            try:
                vid = upload_one(page, f, sm, t0 + dt.timedelta(minutes=a.gap * i), is_short=True)
                done[f.name] = vid or "unknown"; done_f.write_text(json.dumps(done))
            except Exception:
                traceback.print_exc(); shot(page, f"{ep}_short{i}_fail")
        # ---- pinned comment text for you to paste
        (ep_dir / f"{ep}_pinned_comment.txt").write_text(
            meta["pinned"] + "\n\n" + meta["credits"], encoding="utf-8")
        print("\n  DONE. Uploaded items are remembered; run again to retry any that failed.")
        print(f"  Pinned comment + picture credits: {ep_dir / (ep + '_pinned_comment.txt')} (paste once the video is public).")
        page.close()


if __name__ == "__main__":
    main()
