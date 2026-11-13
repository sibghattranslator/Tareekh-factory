"""Tareekh Ki Kahani - DETAILS (YouTube API, no browser clicking, fast).
You upload the video files in YouTube Studio by hand (any way, the title may be just the file name).
DETAILS.bat then finds each video on the channel and fills in: title, description + chapters, tags, category, language,
'not made for kids', 'not AI/altered', thumbnail, Urdu + English subtitles and the publish schedule.
Videos it already finished are remembered (meta_done.json in each episode folder), so running it again is safe.
Needs a Google 'OAuth client' file (client_secret.json) - the same one as for the Chestha channel works."""
import os, sys, json, re, time, shutil, traceback, datetime as dt
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import yt_upload as Y                                   # reuses: upload.txt reader, settings, schedule slots

ROOT, READY = Y.ROOT, Y.READY
CHANNEL_ID = Y.CHANNEL_ID
SECRET_F, TOKEN_F = HERE / "client_secret.json", HERE / "yt_token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/youtube.force-ssl"]
CATEGORY = "27"                                          # Education


class Stop(Exception): pass


def log(m): print("  " + m, flush=True)


def norm(s): return re.sub(r"[\W_]+", "", (s or "").casefold())


# ----------------------------------------------------------------------------- Google sign-in
def find_secret():
    """client_secret.json: here, or copied from a sibling project folder (Chestha / Badrango) on the same drive."""
    if SECRET_F.exists(): return SECRET_F
    skip = {"$recycle.bin", "system volume information", "program files", "moviecache", "recovery", "tareekh ki kahani"}
    for sib in sorted(ROOT.parent.iterdir()) if ROOT.parent.exists() else []:
        if not sib.is_dir() or sib.name.lower() in skip: continue
        base = len(sib.parts)
        for dp, dn, fn in os.walk(sib):
            if len(Path(dp).parts) - base >= 3: dn[:] = []; continue
            dn[:] = [d for d in dn if d not in (".git", "node_modules", "images", "recordings", "Ready to Upload", "music")]
            for f in fn:
                if f.lower().startswith("client_secret") and f.lower().endswith(".json"):
                    p = Path(dp) / f
                    try:
                        if "installed" in json.loads(p.read_text(encoding="utf-8")):
                            shutil.copy(p, SECRET_F); log(f"Google sign-in file copied from {p}"); return SECRET_F
                    except Exception: pass
    return None


def get_service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = None
    if TOKEN_F.exists():
        try: creds = Credentials.from_authorized_user_file(str(TOKEN_F), SCOPES)
        except Exception: creds = None
    if creds and not creds.valid and creds.refresh_token:
        try: creds.refresh(Request())
        except Exception: creds = None                   # app in 'Testing' mode: sign-in expires every 7 days
    if not creds or not creds.valid:
        sec = find_secret()
        if not sec:
            sys.exit("\n  The Google sign-in file (client_secret.json) was not found.\n"
                     "  Copy the file client_secret....json from your Chestha Exams Winner folder into:\n"
                     f"     {HERE}\n  and rename it to client_secret.json. Then run DETAILS.bat again.")
        print("\n  A browser window opens: sign in with sibghattranslator@gmail.com and CHOOSE the channel 'Tareekh Ki Kahani'.\n")
        creds = InstalledAppFlow.from_client_secrets_file(str(sec), SCOPES).run_local_server(port=0, prompt="consent")
    TOKEN_F.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def call(req):
    """Runs an API request; stops everything if today's Google quota is used up."""
    from googleapiclient.errors import HttpError
    try: return req.execute()
    except HttpError as e:
        if e.resp.status == 403 and b"quotaExceeded" in (e.content or b""):
            raise Stop("Google's daily limit is used up. Run DETAILS.bat again tomorrow - finished videos are remembered.")
        raise


# ----------------------------------------------------------------------------- what is on the channel / what we know
def channel_videos(yt):
    ch = call(yt.channels().list(part="id,snippet,contentDetails", mine=True))["items"]
    if not ch: sys.exit("  This Google account has no YouTube channel.")
    ch = ch[0]
    if ch["id"] != CHANNEL_ID:
        TOKEN_F.unlink(missing_ok=True)
        sys.exit(f"\n  You signed in to the channel '{ch['snippet']['title']}', not 'Tareekh Ki Kahani'. Nothing was changed.\n"
                 "  Run DETAILS.bat again and choose the channel 'Tareekh Ki Kahani' in the sign-in window.")
    ids, tok = [], None
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    while len(ids) < 400:
        r = call(yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=50, pageToken=tok))
        ids += [i["contentDetails"]["videoId"] for i in r["items"]]
        tok = r.get("nextPageToken")
        if not tok: break
    vids = []
    for k in range(0, len(ids), 50):
        vids += call(yt.videos().list(part="snippet,status,contentDetails", id=",".join(ids[k:k + 50])))["items"]
    return vids


def build_targets(skip):
    """Every long video and Short of every episode in 'Ready to Upload' with the text that belongs to it."""
    out = []
    for d in sorted(READY.glob("tk[0-9][0-9][0-9]")):
        if d.name in skip or not (d / "upload.txt").exists(): continue
        longs = list(d.glob("*.mp4"))
        if not longs: continue
        ep = d.name
        meta = Y.parse_upload(d, ep)
        out.append(dict(ep=ep, dir=d, kind="long", name=longs[0].stem, norm=norm(longs[0].stem), index=0, meta=meta))
        shorts = sorted((d / "Shorts").glob("*.mp4")) if (d / "Shorts").exists() else []
        for i, f in enumerate(shorts):
            sm = dict(meta); sm["title"] = f.stem[:100]
            sm["desc"] = f"{re.sub(r'#Shorts', '', f.stem).strip(' -')} - full video on the channel.\n\n#Shorts #TareekhKiKahani"
            out.append(dict(ep=ep, dir=d, kind="short", name=f.stem, norm=norm(f.stem), index=i, meta=sm))
    return out


def match(video_title, targets):
    n = norm(video_title)
    if not n: return None
    for t in targets:
        if n == t["norm"]: return t
    for t in targets:                                    # YouTube may shorten a long file name
        if len(n) >= 25 and (t["norm"].startswith(n) or n.startswith(t["norm"])): return t
    return None


def fit_bytes(text, limit=4900):
    while len(text.encode("utf-8")) > limit: text = text.rsplit("\n", 1)[0]
    return text


# ----------------------------------------------------------------------------- the work on one video
def utc_iso(local_naive):
    return local_naive.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def set_details(yt, v, t, when):
    """title, description, tags, language, category, kids/AI flags, and the schedule (only if still an unscheduled private video)."""
    from googleapiclient.errors import HttpError
    m = t["meta"]; st = dict(v["status"]); vid = v["id"]
    can_schedule = st.get("privacyStatus") == "private" and not st.get("publishAt")
    status = {"privacyStatus": st["privacyStatus"], "embeddable": st.get("embeddable", True),
              "license": st.get("license", "youtube"), "publicStatsViewable": st.get("publicStatsViewable", True),
              "selfDeclaredMadeForKids": False}
    if can_schedule: status["privacyStatus"] = "private"; status["publishAt"] = utc_iso(when)
    elif st.get("publishAt"): status["publishAt"] = st["publishAt"]
    snippet = {"title": m["title"], "description": fit_bytes(m.get("desc") if t["kind"] == "short" else m["desc"]),
               "tags": m["tags"], "categoryId": CATEGORY, "defaultLanguage": "ur", "defaultAudioLanguage": "ur"}
    body = {"id": vid, "snippet": snippet, "status": dict(status, containsSyntheticMedia=False)}   # real voice + real pictures: NOT AI
    try:
        call(yt.videos().update(part="snippet,status", body=body))
    except HttpError as e:
        if e.resp.status != 400: raise
        body["status"] = status                          # this API version does not know the AI flag: set it once by hand
        call(yt.videos().update(part="snippet,status", body=body))
        log("  (AI/altered flag could not be set by the API - check 'Altered content: No' in Studio once)")
    return can_schedule


def set_thumb(yt, vid, path):
    from googleapiclient.http import MediaFileUpload
    call(yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(path), mimetype="image/jpeg")))


def add_subs(yt, vid, lang, name, path):
    from googleapiclient.http import MediaFileUpload
    have = {c["snippet"]["language"] for c in call(yt.captions().list(part="snippet", videoId=vid)).get("items", [])}
    if lang in have: return
    call(yt.captions().insert(part="snippet", body={"snippet": {"videoId": vid, "language": lang, "name": name, "isDraft": False}},
                              media_body=MediaFileUpload(str(path), mimetype="application/octet-stream")))


def work_video(yt, v, t, when, done):
    vid = v["id"]; rec = done.setdefault(vid, {}); d = t["dir"]; ep = t["ep"]
    label = f"{ep} {'long video' if t['kind'] == 'long' else 'Short'}: {t['name'][:55]}"
    print(f"\n  {label}\n      https://youtu.be/{vid}")
    steps = [("meta", lambda: set_details(yt, v, t, when))]
    if t["kind"] == "long":
        th, ur, en = d / f"{ep}_thumbnail.jpg", d / f"{ep}_subtitles_Urdu.srt", d / f"{ep}_subtitles_English.srt"
        if th.exists(): steps.append(("thumb", lambda: set_thumb(yt, vid, th)))
        if ur.exists(): steps.append(("ur", lambda: add_subs(yt, vid, "ur", "Urdu", ur)))
        if en.exists(): steps.append(("en", lambda: add_subs(yt, vid, "en", "English", en)))
    names = {"meta": "title, description, tags, flags", "thumb": "thumbnail", "ur": "Urdu subtitles", "en": "English subtitles"}
    for key, fn in steps:
        if rec.get(key): print(f"      [done before] {names[key]}"); continue
        try:
            r = fn(); rec[key] = True
            extra = f", scheduled {when:%Y-%m-%d %H:%M}" if key == "meta" and r else ""
            print(f"      [OK] {names[key]}{extra}")
        except Stop: raise
        except Exception as e:
            print(f"      [FAILED] {names[key]}: {str(e)[:200]}")
        (d / "meta_done.json").write_text(json.dumps(done), encoding="utf-8")
    (d / "meta_done.json").write_text(json.dumps(done), encoding="utf-8")


# ----------------------------------------------------------------------------- main
def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true", help="only show which videos were found and when they would go out")
    a = ap.parse_args()
    st = Y.load_settings(); gap = int(st["gap_minutes"])
    targets = build_targets(Y.skipped_episodes())
    if not targets: sys.exit("  No finished episodes found in 'Ready to Upload'.")
    print("\n  Signing in to Google / reading your channel ...")
    yt = get_service(); vids = channel_videos(yt)
    found, unmatched = [], []
    for v in vids:
        t = match(v["snippet"]["title"], targets)
        if t: found.append((v, t))
        elif v["status"]["privacyStatus"] == "private" and not v["status"].get("publishAt"): unmatched.append(v["snippet"]["title"])
    if not found:
        print("  No video on the channel matches your episodes yet. Upload the video files in YouTube Studio first")
        print("  (keep the file name as the title). Private videos that were not recognised:")
        for u in unmatched[:15]: print("     -", u)
        return
    seen = {}; dup = []
    for v, t in found:                                   # the same file uploaded twice: only the newest one is used
        k = (t["ep"], t["kind"], t["index"])
        if k in seen:
            old = seen[k]
            keep, drop = (v, old[0]) if v["snippet"]["publishedAt"] > old[0]["snippet"]["publishedAt"] else (old[0], v)
            seen[k] = (keep, t); dup.append(drop)
        else: seen[k] = (v, t)
    found = sorted(seen.values(), key=lambda x: (x[1]["ep"], x[1]["kind"] != "long", x[1]["index"]))
    pend = [(ep, READY / ep, True, []) for ep in sorted({t["ep"] for _, t in found})]
    plan, state = Y.make_plan(pend, st)
    slot = {ep: (lt, sh) for ep, _d, _l, _s, lt, sh in plan}
    for v, t in found:
        lt, sh = slot[t["ep"]]; t["when"] = lt if t["kind"] == "long" else sh + dt.timedelta(minutes=gap * t["index"])
    if a.plan:
        for v, t in found:
            print(f"  {t['ep']} {t['kind']:5} -> {t['when']:%Y-%m-%d %H:%M}   {v['snippet']['title'][:60]}")
        return
    Y.STATE_F.write_text(json.dumps(state))
    try:
        for v, t in found:
            done_f = t["dir"] / "meta_done.json"
            done = json.loads(done_f.read_text(encoding="utf-8")) if done_f.exists() else {}
            work_video(yt, v, t, t["when"], done)
    except Stop as s:
        print("\n  STOPPED: " + str(s)); return
    if dup:
        print("\n  The same video was uploaded more than once. Only the NEWEST copy was filled in. Delete these extra copies in Studio:")
        for v in dup: print(f"     https://studio.youtube.com/video/{v['id']}/edit   {v['snippet']['title'][:60]}")
    if unmatched:
        print("\n  Private videos on your channel that match no episode (left untouched):")
        for u in unmatched[:15]: print("     -", u)
    print("\n  DONE. Open YouTube Studio > Content to check the dates.")


if __name__ == "__main__":
    try: main()
    except SystemExit: raise
    except Exception: traceback.print_exc()
