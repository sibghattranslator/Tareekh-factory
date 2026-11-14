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
    tags = block("TAGS (15)", ["\nPINNED COMMENT", "\nSUBTITLES", "\nSHORTS"]).strip()
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


def attach_file(page, selector, path):
    """Put a file into a file input. Big files (long videos, 270-500 MB) cannot go through Playwright over the
    Chrome debugging port (it stops at 50 MB) - so for those Chrome itself is told the file's path directly."""
    path = str(path)
    if os.path.getsize(path) < 40 * 1024 * 1024:
        page.locator(selector).first.set_input_files(path, timeout=120000); return
    cdp = page.context.new_cdp_session(page)
    r = cdp.send("Runtime.evaluate", {"expression": "document.querySelector(%s)" % json.dumps(selector)})
    oid = r.get("result", {}).get("objectId")
    if not oid: raise RuntimeError(f"file box {selector} not found on the page")
    cdp.send("DOM.setFileInputFiles", {"files": [path], "objectId": oid})


def wait_dialog_ready(page, timeout=10800):
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
    """Sets the schedule time (tested on live Studio: the time box is the one input inside ytcp-datetime-picker)."""
    label = dt.datetime.strptime(hhmm, "%H:%M").strftime("%I:%M %p").lstrip("0")
    page.evaluate("""(v) => { const i = document.querySelector('ytcp-datetime-picker input'); i.focus(); i.select();
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(i, v);
        i.dispatchEvent(new Event('input', {bubbles: true, composed: true}));
        i.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true, composed: true}));
        i.dispatchEvent(new Event('change', {bubbles: true, composed: true})); i.blur(); }""", label)
    time.sleep(1.2)
    return page.locator("ytcp-datetime-picker input").first.input_value().strip().upper() == label.upper()


def pick_date(page, d):
    """Sets the schedule date. The calendar's text box only accepts REAL key presses (not script events)."""
    want = f"{MONTHS[d.month - 1]} {d.day}, {d.year}"
    def shown():
        return page.locator("#datepicker-trigger .dropdown-trigger-text").first.inner_text().strip()
    if shown() == want: return True
    page.evaluate("document.querySelector('#datepicker-trigger').click()"); time.sleep(1)
    box = page.locator("ytcp-date-picker input").first
    box.click(); box.press("Control+A"); box.type(want, delay=40); box.press("Enter"); time.sleep(1)
    page.evaluate("document.activeElement && document.activeElement.blur()"); time.sleep(0.5)
    return shown() == want


def get_video_id(page):
    txt = page.locator("ytcp-uploads-dialog").inner_text()
    m = re.search(r"youtu\.be/([\w-]{11})", txt) or re.search(r"shorts/([\w-]{11})", txt)
    if m: return m.group(1)
    for a in page.locator("ytcp-uploads-dialog a").all():
        h = a.get_attribute("href") or ""
        m = re.search(r"(?:youtu\.be/|shorts/|v=)([\w-]{11})", h)
        if m: return m.group(1)
    return None


def schedule_in_dialog(page, when, vid=None):
    """Upload dialog is open on any step: go to Visibility, schedule, confirm. Tested on live Studio."""
    for _ in range(3):                                    # Next x3 -> Visibility
        page.locator("#next-button").click(); time.sleep(1.5)
    page.evaluate("(document.querySelector('#second-container-expand-button') || document.querySelector('#visibility-title')).click()")
    time.sleep(1.5)                                       # the 'Schedule' part with date + time opens
    if not pick_date(page, when):
        log(f"(!) could not set the date {when:%Y-%m-%d} - scheduling with the date YouTube shows; change it later in Studio)")
    if not pick_time(page, when.strftime("%H:%M")):
        log(f"(!) could not set the time {when:%H:%M} - scheduling with the time YouTube shows; change it later in Studio)")
    time.sleep(0.5)
    page.evaluate("document.querySelector('#done-button').click()")          # button says 'Schedule'
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


def finish_draft(page, vid, when):
    """A video that reached YouTube earlier but was never scheduled (private draft): open it and schedule it.
    Returns False if it was already scheduled (nothing to do)."""
    page.goto(f"https://studio.youtube.com/video/{vid}/edit", wait_until="domcontentloaded"); time.sleep(6)
    if not page.get_by_text("Edit draft", exact=True).count(): return False
    page.get_by_text("Edit draft", exact=True).first.click()
    page.wait_for_selector("ytcp-uploads-dialog #next-button", timeout=60000); time.sleep(2)
    schedule_in_dialog(page, when, vid); return True


def upload_one(page, f, meta, when, thumb=None, is_short=False, st=None):
    """st (dict) is filled while working: st["attached"]=True once the file is in YouTube (a private draft now exists),
    st["vid"]=its id. The caller uses it so that a failure later NEVER causes the same file to be uploaded again."""
    st = st if st is not None else {}
    page.goto(UPLOAD_URL, wait_until="domcontentloaded"); time.sleep(4)
    attach_file(page, "input[type=file]", f)
    page.wait_for_selector("#textbox", timeout=180000); st["attached"] = True; time.sleep(3)
    set_box(page, 0, meta["title"]); time.sleep(0.5)
    set_box(page, 1, meta["desc"]); time.sleep(0.5)
    if thumb and thumb.exists():
        try:
            attach_file(page, "#file-loader", thumb); time.sleep(2)
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
    st["vid"] = vid
    wait_dialog_ready(page)
    vid = schedule_in_dialog(page, when, vid)
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


# ----------------------------------------------------------------------------- settings + schedule (automatic)
SETTINGS_F = ROOT / "factory" / "upload_settings.txt"
STATE_F = ROOT / "factory" / "schedule_state.json"          # remembers which day each episode was given (not in git)
DEFAULTS = {"long_time": "19:00", "shorts_time": "13:00", "gap_minutes": "120", "days_between_episodes": "1", "first_day_offset": "0"}


def load_settings():
    st = dict(DEFAULTS)
    if SETTINGS_F.exists():
        for ln in SETTINGS_F.read_text(encoding="utf-8", errors="replace").replace("\r", "").splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k, v = ln.split("=", 1); st[k.strip()] = v.strip()
    for k in ("long_time", "shorts_time"):
        hh, mm = st[k].split(":")
        if int(mm) % 15: sys.exit(f"upload_settings.txt: {k} minutes must be 00, 15, 30 or 45")
    return st


SKIP_F = ROOT / "factory" / "upload_skip.txt"              # episodes already live on YouTube (uploaded by hand) - never upload again


def skipped_episodes():
    if not SKIP_F.exists(): return set()
    lines = SKIP_F.read_text(encoding="utf-8", errors="replace").replace("\r", "").splitlines()
    return {ln.split("#")[0].strip().lower() for ln in lines if ln.split("#")[0].strip()}


def episode_version(ep):
    """rerender_v of an episode that is marked "reupload" (the new video replaces the live one), else None."""
    try:
        d = json.loads((ROOT / "episodes" / f"{ep}.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    return d.get("rerender_v", 1) if d.get("reupload") else None


def load_done(ep_dir, ep):
    """What is already uploaded for this episode. A new version of a 'reupload' episode starts from zero once."""
    f = ep_dir / "uploaded.json"
    done = json.loads(f.read_text()) if f.exists() else {}
    rv = episode_version(ep)
    if rv is not None:
        if done.get("rv") != rv: done = {}
        done["rv"] = rv
    return done


def pending_episodes(only=None):
    """Episodes in 'Ready to Upload' that still have something to upload: long video and/or Shorts."""
    out = []; skip = skipped_episodes()
    for d in sorted(READY.glob("tk[0-9][0-9][0-9]")):
        if only and d.name != only: continue
        if d.name in skip and not only: continue
        longs = [x for x in d.glob("*.mp4")]
        if not longs: continue
        done = load_done(d, d.name)
        shorts = sorted((d / "Shorts").glob("*.mp4")) if (d / "Shorts").exists() else []
        left_long = "long" not in done
        left_shorts = [f for f in shorts if f.name not in done]
        has_draft = any(str(v).startswith("draft:") for v in done.values())
        if left_long or left_shorts or has_draft: out.append((d.name, d, left_long, left_shorts))
    return out


def make_plan(pend, st):
    state = json.loads(STATE_F.read_text()) if STATE_F.exists() else {}
    days = state.get("days", {})
    day = dt.date.today() + dt.timedelta(days=int(st["first_day_offset"]))
    if days:
        day = max(day, max(dt.date.fromisoformat(v) for v in days.values()) + dt.timedelta(days=int(st["days_between_episodes"])))
    plan = []
    for ep, d, left_long, left_shorts in pend:
        if ep in days and dt.date.fromisoformat(days[ep]) >= dt.date.today():
            my = dt.date.fromisoformat(days[ep])                         # same slot as an earlier (partly failed) run
        else:
            my = day; days[ep] = my.isoformat(); day = my + dt.timedelta(days=int(st["days_between_episodes"]))
        lt = dt.datetime.combine(my, dt.datetime.strptime(st["long_time"], "%H:%M").time())
        sh = dt.datetime.combine(my, dt.datetime.strptime(st["shorts_time"], "%H:%M").time())
        plan.append((ep, d, left_long, left_shorts, lt, sh))
    state["days"] = days
    return plan, state


def preflight(ep, d):
    """Prints what is ready for one episode. Returns False if the episode cannot be uploaded."""
    up = d / "upload.txt"
    items = [("video", any(d.glob("*.mp4"))), ("upload.txt (title, description, tags)", up.exists()),
             ("thumbnail", (d / f"{ep}_thumbnail.jpg").exists()),
             ("Urdu subtitles", (d / f"{ep}_subtitles_Urdu.srt").exists()),
             ("English subtitles", (d / f"{ep}_subtitles_English.srt").exists()),
             ("chapters", (d / f"{ep}_chapters.txt").exists())]
    for name, ok in items: print(f"      [{'OK' if ok else 'MISSING'}] {name}")
    if not up.exists() or not any(d.glob("*.mp4")): return False
    meta = parse_upload(d, ep)
    print(f"      title ({len(meta['title'])} chars): {meta['title']}")
    print(f"      tags: {len(meta['tags'])}   description: {len(meta['desc'])} chars")
    return bool(meta["title"])


DRAFTS = []          # files that reached YouTube but could not be scheduled (they wait there as private drafts)


def upload_episode(page, ep, ep_dir, long_at, shorts_at, gap):
    meta = parse_upload(ep_dir, ep)
    done_f = ep_dir / "uploaded.json"
    done = load_done(ep_dir, ep)
    longs = [x for x in ep_dir.glob("*.mp4")]
    short_files = sorted((ep_dir / "Shorts").glob("*.mp4")) if (ep_dir / "Shorts").exists() else []
    subs = {"ur": ep_dir / f"{ep}_subtitles_Urdu.srt", "en": ep_dir / f"{ep}_subtitles_English.srt"}
    for key, val in list(done.items()):                  # drafts left by an earlier run: schedule them now
        if not str(val).startswith("draft:"): continue
        dvid = val.split(":", 1)[1]
        if dvid == "unknown": DRAFTS.append(f"{ep}  {key} (id unknown)"); continue
        if key == "long": when = long_at
        else:
            names = [x.name for x in short_files]; when = shorts_at + dt.timedelta(minutes=gap * (names.index(key) if key in names else 0))
        log(f"FINISH DRAFT: {key}  ->  {when:%Y-%m-%d %H:%M}  (https://youtu.be/{dvid})")
        try:
            finish_draft(page, dvid, when)
            if key == "long": upload_subs(page, dvid, {k: v for k, v in subs.items() if v.exists()})
            done[key] = dvid; done_f.write_text(json.dumps(done))
        except Exception:
            traceback.print_exc(); shot(page, f"{ep}_draft_{dvid}_fail"); DRAFTS.append(f"{ep}  {key}: https://youtu.be/{dvid}")
    if longs and "long" not in done:
        f = longs[0]; log(f"LONG: {f.name}  ->  {long_at:%Y-%m-%d %H:%M}")
        st = {}
        try:
            vid = upload_one(page, f, meta, long_at, thumb=ep_dir / f"{ep}_thumbnail.jpg", st=st)
            if vid:
                subs = {"ur": ep_dir / f"{ep}_subtitles_Urdu.srt", "en": ep_dir / f"{ep}_subtitles_English.srt"}
                upload_subs(page, vid, {k: v for k, v in subs.items() if v.exists()})
            done["long"] = vid or "unknown"; done_f.write_text(json.dumps(done))
        except Exception:
            traceback.print_exc(); shot(page, f"{ep}_long_fail")
            if st.get("attached"):                       # the file is already in YouTube as a private draft: never upload it again
                done["long"] = "draft:" + (st.get("vid") or "unknown"); done_f.write_text(json.dumps(done))
                DRAFTS.append(f"{ep}  long video: {f.name}")
    tag_line = "#Shorts #TareekhKiKahani"
    for i, f in enumerate(sorted((ep_dir / "Shorts").glob("*.mp4")) if (ep_dir / "Shorts").exists() else []):
        if f.name in done: continue
        title = f.stem
        sm = dict(meta); sm["title"] = title[:100]
        sm["desc"] = f"{re.sub(r'#Shorts', '', title).strip(' -')} - full video on the channel.\n\n{tag_line}"
        when = shorts_at + dt.timedelta(minutes=gap * i)
        log(f"SHORT: {f.name}  ->  {when:%Y-%m-%d %H:%M}")
        st = {}
        try:
            vid = upload_one(page, f, sm, when, is_short=True, st=st)
            done[f.name] = vid or "unknown"; done_f.write_text(json.dumps(done))
        except Exception:
            traceback.print_exc(); shot(page, f"{ep}_short{i}_fail")
            if st.get("attached"):
                done[f.name] = "draft:" + (st.get("vid") or "unknown"); done_f.write_text(json.dumps(done))
                DRAFTS.append(f"{ep}  Short: {f.name}")
    (ep_dir / f"{ep}_pinned_comment.txt").write_text(meta["pinned"] + "\n\n" + meta["credits"], encoding="utf-8")
    log(f"{ep}: pinned comment + picture credits saved in {ep_dir / (ep + '_pinned_comment.txt')} (paste once the video is public)")


# ----------------------------------------------------------------------------- main
def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("ep", nargs="?", help="one episode, e.g. tk004 (default: every episode that still has something to upload)")
    ap.add_argument("--plan", action="store_true", help="only show what would be uploaded and when")
    ap.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    ap.add_argument("--long-at", help='override: "YYYY-MM-DD HH:MM"')
    ap.add_argument("--shorts-start", help="override: first Short, same format")
    ap.add_argument("--gap", type=int, help="minutes between Shorts")
    a = ap.parse_args()
    st = load_settings(); gap = a.gap or int(st["gap_minutes"])
    pend = pending_episodes(a.ep.lower() if a.ep else None)
    print("\n  CHECKING WHAT IS LEFT TO UPLOAD ...")
    if not pend:
        print("  Nothing left: every finished video and Short in 'Ready to Upload' is already uploaded."); return
    plan, state = make_plan(pend, st)
    ok_plan = []
    for ep, d, left_long, left_shorts, lt, sh in plan:
        if a.long_at: lt = parse_when(a.long_at)
        if a.shorts_start: sh = parse_when(a.shorts_start)
        print(f"\n  {ep}: {'long video' if left_long else ''}{' + ' if left_long and left_shorts else ''}{str(len(left_shorts)) + ' Short(s)' if left_shorts else ''}")
        print(f"      schedule: Shorts {sh:%Y-%m-%d %H:%M} (every {gap} min), long video {lt:%Y-%m-%d %H:%M}")
        if preflight(ep, d): ok_plan.append((ep, d, lt, sh))
        else: print(f"      -> {ep} skipped (something essential is missing, see above)")
    if a.plan or not ok_plan: return
    if not a.yes and os.environ.get("TK_UPLOAD_YES") != "1":
        input("\n  Press ENTER to start uploading (Ctrl+C to stop) ... ")
    STATE_F.write_text(json.dumps(state))
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = br.contexts[0]; page = ctx.new_page(); page.set_default_timeout(30000)
        page.on("dialog", lambda d: d.accept())               # 'Leave site?' prompts must not freeze the next upload
        page.goto("https://studio.youtube.com", wait_until="domcontentloaded"); time.sleep(4)
        while "accounts.google" in page.url or "ServiceLogin" in page.url:
            input("  Sign in to Google in the Chrome window, then press ENTER here ...")
            page.goto("https://studio.youtube.com", wait_until="domcontentloaded"); time.sleep(4)
        for ep, d, lt, sh in ok_plan:
            print(f"\n  ===== {ep} =====")
            upload_episode(page, ep, d, lt, sh, gap)
        if DRAFTS:
            print("\n  !!! THESE ARE IN YOUTUBE AS PRIVATE DRAFTS (uploaded, but scheduling failed). They will NOT be uploaded again.")
            print("      Open YouTube Studio > Content, find them, and set Visibility > Schedule by hand:")
            for x in DRAFTS: print("        - " + x)
        left = pending_episodes(a.ep.lower() if a.ep else None)
        print("\n  DONE. " + ("Still not uploaded (run UPLOAD.bat again to retry): " + ", ".join(e for e, *_ in left) if left else "Everything is uploaded and scheduled."))
        page.close()


if __name__ == "__main__":
    main()
